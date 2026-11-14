import json
import unittest

from core.telemetry_protocol import (
    MAX_FRAME_BYTES,
    SENSOR_FIELDS,
    TelemetryProtocolError,
    parse_telemetry_frame,
)


def frame_bytes(**overrides):
    sensors = {field: 1.0 for field in SENSOR_FIELDS}
    message = {
        "version": 1,
        "type": "telemetry",
        "sequence": 1,
        "sensors": sensors,
        "alarms": [],
        **overrides,
    }
    return (json.dumps(message) + "\n").encode("utf-8")


class TelemetryProtocolTests(unittest.TestCase):
    def test_parses_valid_frame(self):
        parsed = parse_telemetry_frame(frame_bytes())
        self.assertEqual(parsed["sequence"], 1)
        self.assertEqual(parsed["sensors"]["t5_c"], 1.0)
        self.assertEqual(parsed["alarms"], [])

    def test_accepts_null_for_unavailable_sensor(self):
        sensors = {field: 1.0 for field in SENSOR_FIELDS}
        sensors["t3_c"] = None
        parsed = parse_telemetry_frame(frame_bytes(sensors=sensors))
        self.assertIsNone(parsed["sensors"]["t3_c"])

    def test_rejects_missing_sensor(self):
        sensors = {field: 1.0 for field in SENSOR_FIELDS if field != "rpm"}
        with self.assertRaises(TelemetryProtocolError):
            parse_telemetry_frame(frame_bytes(sensors=sensors))

    def test_rejects_missing_alarms(self):
        message = json.loads(frame_bytes())
        del message["alarms"]
        with self.assertRaises(TelemetryProtocolError):
            parse_telemetry_frame((json.dumps(message) + "\n").encode())

    def test_rejects_boolean_sensor_value(self):
        sensors = {field: 1.0 for field in SENSOR_FIELDS}
        sensors["rpm"] = True
        with self.assertRaises(TelemetryProtocolError):
            parse_telemetry_frame(frame_bytes(sensors=sensors))

    def test_rejects_unsupported_message_type(self):
        with self.assertRaises(TelemetryProtocolError):
            parse_telemetry_frame(frame_bytes(type="command"))

    def test_rejects_non_integer_protocol_version(self):
        with self.assertRaises(TelemetryProtocolError):
            parse_telemetry_frame(frame_bytes(version=1.0))

    def test_rejects_oversized_frame(self):
        with self.assertRaises(TelemetryProtocolError):
            parse_telemetry_frame(b" " * (MAX_FRAME_BYTES + 1) + b"\n")

    def test_rejects_frame_without_newline(self):
        with self.assertRaises(TelemetryProtocolError):
            parse_telemetry_frame(frame_bytes().rstrip(b"\n"))

    def test_rejects_invalid_alarm_severity(self):
        alarms = [{"code": "X", "severity": "urgent", "message": "test"}]
        with self.assertRaises(TelemetryProtocolError):
            parse_telemetry_frame(frame_bytes(alarms=alarms))


if __name__ == "__main__":
    unittest.main()
