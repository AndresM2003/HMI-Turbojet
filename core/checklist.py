"""Motor de listas de verificación (arranque / apagado) basado solo en telemetría.

No depende de Qt. El HMI es de solo lectura: este módulo evalúa lo que reporta el
ESP32 y no envía ningún comando.
"""

import time
from dataclasses import dataclass
from typing import Callable

from core.limits import OperatingLimits

TEMP_KEYS = ("t1_c", "t2_c", "t3_c", "t4_c", "t5_c")
LINK_STALE_S = 3.0


@dataclass(frozen=True)
class Snapshot:
    sensors: dict
    alarms: list
    estop_released: bool | None
    link_age_s: float | None


@dataclass(frozen=True)
class Evaluation:
    passed: bool | None  # None = no evaluable automáticamente (límite sin configurar)
    detail: str


@dataclass(frozen=True)
class CheckSpec:
    key: str
    label: str
    description: str
    evaluate: Callable[[Snapshot, OperatingLimits], Evaluation]
    timeout_s: float | None = None  # None = falla inmediata; número = espera hasta el timeout


@dataclass(frozen=True)
class CheckStatus:
    state: str  # OK | WAIT | FAULT | MANUAL
    detail: str
    manual: bool = False


def _fmt(value, unit=""):
    return "—" if value is None else f"{value:,.1f} {unit}".strip()


def _link_live(snap, lim):
    ok = snap.link_age_s is not None and snap.link_age_s <= LINK_STALE_S
    age = "no frames" if snap.link_age_s is None else f"last frame {snap.link_age_s:.1f}s ago"
    return Evaluation(ok, age)


def _estop_released(snap, lim):
    state = {True: "RELEASED", False: "PRESSED", None: "UNKNOWN"}[snap.estop_released]
    return Evaluation(snap.estop_released is True, state)


def _thermocouples(snap, lim):
    missing = [k[:2].upper() for k in TEMP_KEYS if snap.sensors.get(k) is None]
    return Evaluation(not missing, "all valid" if not missing else "no data: " + ", ".join(missing))


def _reporting(keys, names):
    def evaluate(snap, lim):
        missing = [n for k, n in zip(keys, names) if snap.sensors.get(k) is None]
        return Evaluation(not missing, "reporting" if not missing else "no data: " + ", ".join(missing))
    return evaluate


def _no_critical(snap, lim):
    critical = [a for a in snap.alarms if a["severity"] == "critical"]
    warnings = [a for a in snap.alarms if a["severity"] == "warning"]
    if critical:
        return Evaluation(False, f"{len(critical)} critical: {critical[0]['code']}")
    return Evaluation(True, f"{len(warnings)} warning(s)" if warnings else "none")


def _gas_max(snap):
    values = [snap.sensors.get(k) for k in ("mq6_1_ppm", "mq6_2_ppm")]
    values = [v for v in values if v is not None]
    return max(values) if values else None


def _gas_below_limit(snap, lim):
    peak = _gas_max(snap)
    if lim.gas_ppm_max is None or peak is None:
        return Evaluation(None if peak is not None else False, f"max {_fmt(peak, 'ppm')} — limit not set")
    return Evaluation(peak <= lim.gas_ppm_max, f"max {_fmt(peak, 'ppm')} / limit {lim.gas_ppm_max:g}")


def _threshold(key, name, unit, limit_attr, above=True):
    def evaluate(snap, lim):
        value, limit = snap.sensors.get(key), getattr(lim, limit_attr)
        if value is None:
            return Evaluation(False, f"{name}: no data")
        if limit is None:
            return Evaluation(None, f"{name} {_fmt(value, unit)} — limit not set")
        ok = value >= limit if above else value <= limit
        return Evaluation(ok, f"{name} {_fmt(value, unit)} {'≥' if above else '≤'} {limit:g}")
    return evaluate


def _delta_t(snap, lim, above=True):
    t2, t3 = snap.sensors.get("t2_c"), snap.sensors.get("t3_c")
    if t2 is None or t3 is None:
        return Evaluation(False, "T2/T3: no data")
    delta, limit = t3 - t2, lim.combustion_delta_c
    if limit is None:
        return Evaluation(None, f"ΔT {_fmt(delta, '°C')} — limit not set")
    ok = delta >= limit if above else delta < limit
    return Evaluation(ok, f"ΔT {_fmt(delta, '°C')} {'≥' if above else '<'} {limit:g}")


def _cooled(snap, lim):
    t3, t4, limit = snap.sensors.get("t3_c"), snap.sensors.get("t4_c"), lim.cooldown_temp_c
    if t3 is None or t4 is None:
        return Evaluation(False, "T3/T4: no data")
    if limit is None:
        return Evaluation(None, f"T3 {_fmt(t3)} · T4 {_fmt(t4)} — limit not set")
    return Evaluation(max(t3, t4) <= limit, f"T3 {_fmt(t3)} · T4 {_fmt(t4)} / limit {limit:g}")


LINK = CheckSpec("link", "Telemetry link live", "Valid frames arriving from the ESP32", _link_live)

STARTUP_PRECHECKS = (
    LINK,
    CheckSpec("estop", "Physical E-STOP released", "Reported by the ESP32", _estop_released),
    CheckSpec("thermocouples", "Thermocouples T1–T5 valid", "No open thermocouple", _thermocouples, 10.0),
    CheckSpec("maf_rpm", "MAF and RPM reporting", "Both sensors send data",
              _reporting(("maf_g_s", "rpm"), ("MAF", "RPM")), 10.0),
    CheckSpec("gas_reporting", "Gas sensors MQ6 ×2 reporting", "Both sensors send data",
              _reporting(("mq6_1_ppm", "mq6_2_ppm"), ("GAS 1", "GAS 2")), 10.0),
    CheckSpec("gas_limit", "Gas below limit", "Max MQ6 reading under the configured limit", _gas_below_limit),
    CheckSpec("no_critical", "No critical alarms (ESP32)", "Alarm state comes from the ESP32", _no_critical),
)

STARTUP_IGNITION = (
    CheckSpec("airflow", "Airflow established", "MAF at or above the minimum",
              _threshold("maf_g_s", "MAF", "g/s", "maf_min_g_s"), 60.0),
    CheckSpec("combustion", "Combustion detected", "T3 − T2 at or above the minimum",
              lambda s, l: _delta_t(s, l, True), 90.0),
    CheckSpec("spinning", "Turbine spinning", "RPM at or above the minimum",
              _threshold("rpm", "RPM", "rpm", "rpm_min"), 90.0),
)

SHUTDOWN_CHECKS = (
    LINK,
    CheckSpec("flame_out", "Combustion stopped", "T3 − T2 below the combustion limit",
              lambda s, l: _delta_t(s, l, False), 120.0),
    CheckSpec("gas_limit", "Gas below limit", "Max MQ6 reading under the configured limit", _gas_below_limit),
    CheckSpec("cooled", "Cooled: T3 and T4 below limit", "Wait for the chamber to cool", _cooled, 900.0),
    CheckSpec("rpm_stopped", "Turbine stopped", "RPM at or below the stopped limit",
              _threshold("rpm", "RPM", "rpm", "rpm_stopped_max", above=False), 900.0),
)


class ChecklistEngine:
    """Evalúa una lista de chequeos en vivo. Los estados se recalculan en cada update()."""

    def __init__(self, specs, limits: OperatingLimits, clock=time.monotonic):
        self.specs = tuple(specs)
        self.limits = limits
        self._clock = clock
        self._started_at: float | None = None
        self._confirmed: set[str] = set()
        self.statuses: dict[str, CheckStatus] = {}

    def start(self):
        self._started_at = self._clock()
        self._confirmed.clear()

    @property
    def started(self) -> bool:
        return self._started_at is not None

    def confirm_manual(self, key: str):
        if self.statuses.get(key) and self.statuses[key].state == "MANUAL":
            self._confirmed.add(key)

    def update(self, snapshot: Snapshot) -> dict[str, CheckStatus]:
        elapsed = 0.0 if self._started_at is None else self._clock() - self._started_at
        for spec in self.specs:
            result = spec.evaluate(snapshot, self.limits)
            if result.passed is True:
                status = CheckStatus("OK", result.detail)
            elif result.passed is None:
                status = (CheckStatus("OK", result.detail, manual=True)
                          if spec.key in self._confirmed else CheckStatus("MANUAL", result.detail))
            elif spec.timeout_s is not None and elapsed <= spec.timeout_s:
                status = CheckStatus("WAIT", f"{result.detail} ({elapsed:.0f}/{spec.timeout_s:.0f}s)")
            else:
                status = CheckStatus("FAULT", result.detail)
            self.statuses[spec.key] = status
        return self.statuses

    @property
    def all_ok(self) -> bool:
        return bool(self.statuses) and all(s.state == "OK" for s in self.statuses.values())

    @property
    def passed_count(self) -> int:
        return sum(1 for s in self.statuses.values() if s.state == "OK")
