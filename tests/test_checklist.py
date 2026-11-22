import unittest

from core.checklist import (
    STARTUP_IGNITION, STARTUP_PRECHECKS, SHUTDOWN_CHECKS, ChecklistEngine, Snapshot,
)
from core.limits import OperatingLimits


def sensors(**over):
    base = dict(t1_c=30.0, t2_c=30.0, t3_c=35.0, t4_c=35.0, t5_c=40.0,
                maf_g_s=1.0, rpm=0.0, mq6_1_ppm=5.0, mq6_2_ppm=6.0)
    base.update(over)
    return base


def snap(alarms=None, estop=True, age=0.5, **over):
    return Snapshot(sensors(**over), alarms or [], estop, age)


class Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


class ChecklistTests(unittest.TestCase):
    def test_precheck_without_limits_waits_for_manual_confirmation(self):
        engine = ChecklistEngine(STARTUP_PRECHECKS, OperatingLimits())
        engine.start()
        statuses = engine.update(snap())
        self.assertEqual(statuses["gas_limit"].state, "MANUAL")
        self.assertFalse(engine.all_ok)
        engine.confirm_manual("gas_limit")
        engine.update(snap())
        self.assertTrue(engine.all_ok)

    def test_precheck_passes_with_limit_configured(self):
        engine = ChecklistEngine(STARTUP_PRECHECKS, OperatingLimits(gas_ppm_max=50))
        engine.start()
        engine.update(snap())
        self.assertTrue(engine.all_ok)

    def test_estop_pressed_or_unknown_fails(self):
        engine = ChecklistEngine(STARTUP_PRECHECKS, OperatingLimits(gas_ppm_max=50))
        engine.start()
        for estop in (False, None):
            self.assertEqual(engine.update(snap(estop=estop))["estop"].state, "FAULT")

    def test_open_thermocouple_waits_then_faults_after_timeout(self):
        clock = Clock()
        engine = ChecklistEngine(STARTUP_PRECHECKS, OperatingLimits(gas_ppm_max=50), clock)
        engine.start()
        self.assertEqual(engine.update(snap(t3_c=None))["thermocouples"].state, "WAIT")
        clock.t = 11.0
        self.assertEqual(engine.update(snap(t3_c=None))["thermocouples"].state, "FAULT")
        clock.t = 12.0
        self.assertEqual(engine.update(snap())["thermocouples"].state, "OK")

    def test_critical_alarm_blocks_and_warning_does_not(self):
        engine = ChecklistEngine(STARTUP_PRECHECKS, OperatingLimits(gas_ppm_max=50))
        engine.start()
        warn = [{"code": "W", "severity": "warning", "message": "m"}]
        crit = [{"code": "C", "severity": "critical", "message": "m"}]
        self.assertEqual(engine.update(snap(alarms=warn))["no_critical"].state, "OK")
        self.assertEqual(engine.update(snap(alarms=crit))["no_critical"].state, "FAULT")

    def test_stale_link_fails(self):
        engine = ChecklistEngine(STARTUP_PRECHECKS, OperatingLimits(gas_ppm_max=50))
        engine.start()
        self.assertEqual(engine.update(snap(age=5.0))["link"].state, "FAULT")
        self.assertEqual(engine.update(Snapshot(sensors(), [], True, None))["link"].state, "FAULT")

    def test_ignition_checks_use_limits(self):
        lim = OperatingLimits(maf_min_g_s=10, combustion_delta_c=100, rpm_min=5000)
        engine = ChecklistEngine(STARTUP_IGNITION, lim, Clock())
        engine.start()
        self.assertFalse(engine.update(snap(maf_g_s=1.0)) and engine.all_ok)
        engine.update(snap(maf_g_s=12.0, t2_c=150.0, t3_c=400.0, rpm=8000.0))
        self.assertTrue(engine.all_ok)

    def test_shutdown_checks(self):
        lim = OperatingLimits(gas_ppm_max=50, combustion_delta_c=100, cooldown_temp_c=100, rpm_stopped_max=50)
        engine = ChecklistEngine(SHUTDOWN_CHECKS, lim, Clock())
        engine.start()
        engine.update(snap(t3_c=400.0, t4_c=380.0, rpm=3000.0))
        self.assertFalse(engine.all_ok)
        engine.update(snap(t2_c=40.0, t3_c=60.0, t4_c=55.0, rpm=0.0))
        self.assertTrue(engine.all_ok)

    def test_none_sensor_never_counts_as_ok(self):
        lim = OperatingLimits(rpm_stopped_max=50)
        engine = ChecklistEngine(SHUTDOWN_CHECKS, lim, Clock())
        engine.start()
        self.assertNotEqual(engine.update(snap(rpm=None))["rpm_stopped"].state, "OK")


if __name__ == "__main__":
    unittest.main()
