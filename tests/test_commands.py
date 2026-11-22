import json
import unittest

from core.commands import CommandProtocolError, build_command_frame, parse_command_ack
from core.interlocks import InterlockContext, check_command, needs_confirmation


def ctx(**over):
    base = dict(connected=True, estop_released=True, critical_alarm=None, acked={})
    base.update(over)
    return InterlockContext(**base)


class CommandProtocolTests(unittest.TestCase):
    def test_builds_frames(self):
        frame = build_command_frame(7, "oil_pump", "on")
        self.assertTrue(frame.endswith(b"\n"))
        self.assertEqual(json.loads(frame), {"version": 1, "type": "command", "id": 7,
                                             "command": "oil_pump", "value": "on"})
        self.assertNotIn("value", json.loads(build_command_frame(1, "stop")))

    def test_rejects_invalid_commands(self):
        for args in ((1, "oil_pump", "maybe"), (1, "fuel_servo", 101), (1, "fuel_servo", -1),
                     (1, "fuel_servo", True), (1, "fuel_servo", float("nan")), (1, "stop", 1),
                     (1, "explode", None), (-1, "stop", None)):
            with self.assertRaises(CommandProtocolError, msg=str(args)):
                build_command_frame(*args)

    def test_parses_ack(self):
        ack = parse_command_ack(b'{"version":1,"type":"command_ack","id":3,"ok":false,"message":"busy"}\n')
        self.assertEqual(ack, {"id": 3, "ok": False, "message": "busy"})

    def test_rejects_bad_acks(self):
        for raw in (b"not json\n", b'{"version":2,"type":"command_ack","id":1,"ok":true}\n',
                    b'{"version":1,"type":"command_ack","id":"1","ok":true}\n',
                    b'{"version":1,"type":"command_ack","id":1,"ok":"yes"}\n',
                    b'{"version":1,"type":"command_ack","id":1,"ok":true,"message":5}\n'):
            with self.assertRaises(CommandProtocolError):
                parse_command_ack(raw)


MANUAL = {"control_mode": "manual"}


class InterlockTests(unittest.TestCase):
    def test_nothing_without_connection(self):
        for command in ("stop", "emergency_stop", "control_mode"):
            self.assertFalse(check_command(command, "manual" if command == "control_mode" else None,
                                           ctx(connected=False))[0])

    def test_manual_commands_are_blocked_in_automatic_mode(self):
        for command, value in (("oil_pump", "on"), ("oil_pump", "off"), ("fuel_solenoid", "close"),
                               ("fuel_solenoid", "open"), ("fuel_servo", 0), ("fuel_servo", 40),
                               ("spark_pulse", None)):
            allowed, reason = check_command(command, value, ctx())
            self.assertFalse(allowed, command)
            self.assertIn("MANUAL CONTROL", reason)

    def test_stop_emergency_and_mode_switch_are_always_available(self):
        bad = ctx(estop_released=False, critical_alarm="GAS_1_HIGH")
        for command, value in (("emergency_stop", None), ("stop", None),
                               ("control_mode", "manual"), ("control_mode", "auto")):
            self.assertTrue(check_command(command, value, bad)[0], command)

    def test_safe_direction_commands_allowed_in_manual_even_with_estop_or_alarm(self):
        bad = ctx(estop_released=False, critical_alarm="GAS_1_HIGH", acked=MANUAL)
        for command, value in (("fuel_solenoid", "close"), ("fuel_servo", 0), ("oil_pump", "on"), ("oil_pump", "off")):
            self.assertTrue(check_command(command, value, bad)[0], command)

    def test_fuel_and_spark_need_estop_released_and_no_critical_alarm(self):
        acked = {"oil_pump": "on", "fuel_solenoid": "open", **MANUAL}
        for command, value in (("fuel_solenoid", "open"), ("fuel_servo", 10), ("spark_pulse", None)):
            self.assertFalse(check_command(command, value, ctx(estop_released=None, acked=acked))[0])
            self.assertFalse(check_command(command, value, ctx(critical_alarm="X", acked=acked))[0])

    def test_sequence_oil_then_solenoid_then_spark(self):
        self.assertFalse(check_command("fuel_solenoid", "open", ctx(acked=MANUAL))[0])
        self.assertTrue(check_command("fuel_solenoid", "open", ctx(acked={"oil_pump": "on", **MANUAL}))[0])
        self.assertFalse(check_command("spark_pulse", None, ctx(acked={"oil_pump": "on", **MANUAL}))[0])
        self.assertTrue(check_command("spark_pulse", None,
                                      ctx(acked={"oil_pump": "on", "fuel_solenoid": "open", **MANUAL}))[0])

    def test_confirmations(self):
        self.assertIsNotNone(needs_confirmation("oil_pump", "off", None))
        self.assertIsNotNone(needs_confirmation("oil_pump", "off", 1200.0))
        self.assertIsNone(needs_confirmation("oil_pump", "off", 0.0))
        self.assertIsNone(needs_confirmation("emergency_stop", None, 5000.0))
        self.assertIsNotNone(needs_confirmation("spark_pulse", None, 0.0))
        self.assertIsNotNone(needs_confirmation("control_mode", "manual", 0.0))
        self.assertIsNone(needs_confirmation("control_mode", "auto", 0.0))

    def test_horn_command_no_longer_exists(self):
        with self.assertRaises(CommandProtocolError):
            build_command_frame(1, "horn", "silence")

    def test_control_mode_frames(self):
        self.assertIn(b'"command":"control_mode"', build_command_frame(2, "control_mode", "manual"))
        with self.assertRaises(CommandProtocolError):
            build_command_frame(2, "control_mode", "semi")


if __name__ == "__main__":
    unittest.main()
