import json
import os
import re
import unittest

from core.commands import build_command_frame, parse_command_ack
from core.telemetry_protocol import parse_telemetry_frame

DOC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "PROTOCOLO_ESP32.md")
EXAMPLE = re.compile(r"<!-- test:(?P<kind>[\w-]+) -->\s*```json\n(?P<body>.*?)\n```", re.S)


class DocumentedExamplesTests(unittest.TestCase):
    """Los ejemplos del documento para el firmware deben ser aceptados por el HMI real."""

    def examples(self, kind):
        with open(DOC, encoding="utf-8") as file:
            found = [m["body"] for m in EXAMPLE.finditer(file.read()) if m["kind"] == kind]
        self.assertTrue(found, f"no examples tagged {kind}")
        return found

    def test_telemetry_examples_are_valid(self):
        for body in self.examples("valid-telemetry"):
            self.assertNotIn("\n", body)
            parse_telemetry_frame((body + "\n").encode())

    def test_command_examples_match_what_the_hmi_sends(self):
        for body in self.examples("valid-command"):
            message = json.loads(body)
            rebuilt = build_command_frame(message["id"], message["command"], message.get("value"))
            self.assertEqual(rebuilt, (body + "\n").encode())

    def test_ack_examples_are_valid(self):
        for body in self.examples("valid-ack"):
            parse_command_ack((body + "\n").encode())


if __name__ == "__main__":
    unittest.main()
