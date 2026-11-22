import json
import unittest

from core.demo_telemetry import demo_message
from core.telemetry_protocol import parse_telemetry_frame


class DemoTelemetryTests(unittest.TestCase):
    def test_demo_frames_are_valid_protocol_frames(self):
        for second in range(0, 200, 3):
            frame = (json.dumps(demo_message(second, float(second))) + "\n").encode()
            parsed = parse_telemetry_frame(frame)
            self.assertEqual(parsed["sequence"], second)

    def test_demo_shows_both_alarm_severities(self):
        severities = {a["severity"] for s in range(0, 90) for a in demo_message(s, float(s))["alarms"]}
        self.assertEqual(severities, {"warning", "critical"})


if __name__ == "__main__":
    unittest.main()
