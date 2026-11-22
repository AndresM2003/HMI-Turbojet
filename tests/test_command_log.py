import unittest

from core.command_log import describe_command, format_event


class CommandLogTests(unittest.TestCase):
    def test_describes_commands_like_a_serial_monitor(self):
        self.assertEqual(describe_command("fuel_servo", 50), "FUEL SERVO: 50 %")
        self.assertEqual(describe_command("oil_pump", "on"), "OIL PUMP: ON")
        self.assertEqual(describe_command("control_mode", "manual"), "CONTROL MODE: MANUAL")
        self.assertEqual(describe_command("stop"), "STOP")

    def test_events_have_level_and_text(self):
        self.assertEqual(format_event("SENT", "fuel_servo", 50), ("info", "FUEL SERVO: 50 %   SENT"))
        self.assertEqual(format_event("ACK", "oil_pump", "on"), ("ok", "OIL PUMP: ON   ACK ✓"))
        level, text = format_event("REJECTED", "spark_pulse", None, "oil pump is off")
        self.assertEqual(level, "error")
        self.assertTrue(text.endswith("REJECTED — oil pump is off"))
        self.assertEqual(format_event("NO_ACK", "stop")[0], "warn")


if __name__ == "__main__":
    unittest.main()
