import json
import math
from typing import Any


MAX_FRAME_BYTES = 4096
SENSOR_FIELDS = (
    "t1_c",
    "t2_c",
    "t3_c",
    "t4_c",
    "t5_c",
    "maf_g_s",
    "rpm",
    "mq6_1_ppm",
    "mq6_2_ppm",
)


class TelemetryProtocolError(ValueError):
    pass


def parse_telemetry_frame(frame: bytes) -> dict[str, Any]:
    if len(frame) > MAX_FRAME_BYTES:
        raise TelemetryProtocolError("Frame exceeds the 4096-byte limit")
    if not frame.endswith(b"\n"):
        raise TelemetryProtocolError("Frame is not newline-terminated")

    try:
        message = json.loads(frame.decode("utf-8").strip())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TelemetryProtocolError(f"Invalid JSON frame: {error}") from error

    if not isinstance(message, dict):
        raise TelemetryProtocolError("Frame must be a JSON object")
    version = message.get("version")
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version != 1
        or message.get("type") != "telemetry"
    ):
        raise TelemetryProtocolError("Unsupported frame version or type")

    sequence = message.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise TelemetryProtocolError("sequence must be a non-negative integer")

    sensors = message.get("sensors")
    if not isinstance(sensors, dict):
        raise TelemetryProtocolError("sensors must be an object")

    parsed_sensors: dict[str, float | None] = {}
    for field in SENSOR_FIELDS:
        if field not in sensors:
            raise TelemetryProtocolError(f"missing required sensor: {field}")
        value = sensors.get(field)
        if value is None:
            parsed_sensors[field] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TelemetryProtocolError(f"{field} must be a number or null")
        if not math.isfinite(value):
            raise TelemetryProtocolError(f"{field} must be finite")
        parsed_sensors[field] = float(value)

    if "alarms" not in message:
        raise TelemetryProtocolError("missing required alarms list")
    alarms = message["alarms"]
    if not isinstance(alarms, list):
        raise TelemetryProtocolError("alarms must be a list")
    parsed_alarms = []
    seen_alarm_codes = set()
    for alarm in alarms:
        if not isinstance(alarm, dict):
            raise TelemetryProtocolError("each alarm must be an object")
        code = alarm.get("code")
        severity = alarm.get("severity")
        text = alarm.get("message")
        if not all(isinstance(value, str) and value for value in (code, severity, text)):
            raise TelemetryProtocolError(
                "each alarm needs non-empty code, severity, and message strings"
            )
        if severity not in ("info", "warning", "critical"):
            raise TelemetryProtocolError(f"unsupported alarm severity: {severity}")
        if code in seen_alarm_codes:
            raise TelemetryProtocolError(f"duplicate alarm code: {code}")
        seen_alarm_codes.add(code)
        parsed_alarms.append(
            {"code": code, "severity": severity, "message": text}
        )

    status = message.get("status", {})
    if not isinstance(status, dict):
        raise TelemetryProtocolError("status must be an object")
    estop_released = status.get("estop_released")
    if estop_released is not None and not isinstance(estop_released, bool):
        raise TelemetryProtocolError("status.estop_released must be boolean or null")

    return {
        "sequence": sequence,
        "sensors": parsed_sensors,
        "alarms": parsed_alarms,
        "status": {"estop_released": estop_released},
    }
