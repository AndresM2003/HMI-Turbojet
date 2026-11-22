"""Telemetría simulada SOLO para revisar el aspecto del HMI sin hardware.

Genera mensajes con el mismo formato del protocolo v1; el HMI los valida con
parse_telemetry_frame igual que a los reales. Nunca se registran en el CSV.
"""

import math

_CYCLE_S = 90.0


def _ramp(t: float) -> float:
    """0 → 1 en 25 s, se mantiene hasta 60 s y vuelve a 0 a los 90 s."""
    phase = t % _CYCLE_S
    if phase < 25:
        return phase / 25
    if phase < 60:
        return 1.0
    return max(0.0, 1.0 - (phase - 60) / 30)


def demo_message(sequence: int, t: float) -> dict:
    r = _ramp(t)
    wobble = math.sin(t * 1.7)
    sensors = {
        "t1_c": 30 + 120 * r + 2 * wobble,
        "t2_c": 30 + 118 * r + 2 * math.sin(t * 1.3),
        "t3_c": 35 + 700 * r + 6 * wobble,
        "t4_c": 33 + 670 * r + 5 * math.sin(t * 1.1),
        "t5_c": 40 + 35 * r + 0.5 * wobble,
        "maf_g_s": 0.3 + 17 * r + 0.4 * wobble,
        "rpm": 35000 * r + 300 * r * wobble,
        "mq6_1_ppm": 8 + 3 * math.sin(t / 5),
        "mq6_2_ppm": 9 + 2 * math.sin(t / 7),
    }
    alarms = []
    if sensors["t3_c"] > 600:
        alarms.append({"code": "T3_HIGH", "severity": "warning", "message": "Combustor outlet temperature high"})
    if 50 <= t % _CYCLE_S < 58:
        alarms.append({"code": "GAS_1_HIGH", "severity": "critical", "message": "Gas 1 above limit"})
    return {
        "version": 1,
        "type": "telemetry",
        "sequence": sequence,
        "sensors": sensors,
        "alarms": alarms,
        "status": {"estop_released": True},
    }
