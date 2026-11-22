import json
import unittest

from core.telemetry_protocol import SENSOR_FIELDS
from tools.check_esp32 import analyze


def line(sequence, nulls=(), alarms=()):
    sensors = {field: (None if field in nulls else 1.5) for field in SENSOR_FIELDS}
    message = {"version": 1, "type": "telemetry", "sequence": sequence, "sensors": sensors, "alarms": list(alarms)}
    return (json.dumps(message) + "\n").encode()


class AnalyzeTests(unittest.TestCase):
    def test_clean_stream(self):
        report = analyze((i * 0.25, line(i)) for i in range(20))
        self.assertEqual((report.ok, report.invalid, report.gaps, report.restarts), (20, 0, 0, 0))
        self.assertAlmostEqual(report.rate_hz, 4.0, places=3)

    def test_counts_gaps_restarts_duplicates_and_nulls(self):
        frames = [line(1), line(2), line(5, nulls=("t3_c",)), line(5), line(0)]
        report = analyze((None, f) for f in frames)
        self.assertEqual((report.gaps, report.lost_frames, report.duplicates, report.restarts), (1, 2, 1, 1))
        self.assertEqual(report.null_counts["t3_c"], 1)

    def test_debug_lines_are_ignored_not_errors(self):
        raw = [(None, b"ets Jun  8 2016 00:22:57\n"), (None, b"boot: ESP32-S3\n"), (None, line(1))]
        report = analyze(raw)
        self.assertEqual((report.ignored, report.invalid, report.ok), (2, 0, 1))

    def test_invalid_frames_are_reported(self):
        bad_nan = b'{"version":1,"type":"telemetry","sequence":1,"sensors":{"t1_c":nan},"alarms":[]}\n'
        report = analyze([(None, bad_nan), (None, b'{"version":1,')])
        self.assertEqual(report.invalid, 2)
        self.assertTrue(report.errors)

    def test_last_line_without_newline_is_accepted(self):
        self.assertEqual(analyze([(None, line(1).rstrip(b"\n"))]).ok, 1)

    def test_alarms_collected(self):
        alarm = {"code": "GAS_1_HIGH", "severity": "critical", "message": "Gas 1 above limit"}
        self.assertEqual(analyze([(None, line(1, alarms=[alarm]))]).alarms, {"GAS_1_HIGH": "critical"})


if __name__ == "__main__":
    unittest.main()
