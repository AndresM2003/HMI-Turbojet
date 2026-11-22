import json
import unittest

import serial
from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer

import com.serial_reader as serial_reader
from core.telemetry_protocol import SENSOR_FIELDS


def telemetry_line(sequence=1):
    message = {"version": 1, "type": "telemetry", "sequence": sequence,
               "sensors": {field: 1.0 for field in SENSOR_FIELDS}, "alarms": []}
    return (json.dumps(message) + "\n").encode()


class SerialReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def run_reader(self, lines):
        """Conecta el lector a un puerto loop:// y le hace llegar `lines` como si las enviara la ESP32."""
        original = serial_reader.serial.Serial
        created = []

        def factory():
            port = serial.serial_for_url("loop://", do_not_open=True)
            created.append(port)
            return port

        serial_reader.serial.Serial = factory
        try:
            reader = serial_reader.SerialTelemetryReader("loop://", 115200)
            frames, errors, acks = [], [], []
            reader.telemetry_received.connect(frames.append)
            reader.protocol_error.connect(errors.append)
            reader.command_ack.connect(acks.append)
            loop = QEventLoop()
            reader.connection_changed.connect(lambda ok, message: ok and QTimer.singleShot(50, loop.quit))
            reader.start()
            loop.exec()
            self.assertFalse(created[0].dtr)   # abrir el puerto no debe reiniciar la ESP32
            self.assertFalse(created[0].rts)
            for line in lines:
                self.assertTrue(reader.send_frame(line))
            QTimer.singleShot(500, loop.quit)
            loop.exec()
            reader.requestInterruption()
            self.assertTrue(reader.wait(3000))
            return reader, frames, errors, acks
        finally:
            serial_reader.serial.Serial = original

    def test_receives_telemetry_acks_and_ignores_log_lines(self):
        reader, frames, errors, acks = self.run_reader([
            b"ets Jun  8 2016 00:22:57\n",
            b"I (312) boot: debug text\n",
            telemetry_line(1),
            b'{"version":1,"type":"command_ack","id":4,"ok":true,"message":"done"}\n',
            telemetry_line(2),
        ])
        self.assertEqual([f["sequence"] for f in frames], [1, 2])
        self.assertEqual(acks, [{"id": 4, "ok": True, "message": "done"}])
        self.assertEqual(errors, [])
        self.assertEqual(reader.ignored_lines, 2)

    def test_reports_invalid_json_frames_but_keeps_running(self):
        _, frames, errors, _ = self.run_reader([
            b'{"version":1,"type":"telemetry","sequence":1,"sensors":{"t1_c":nan},"alarms":[]}\n',
            telemetry_line(2),
        ])
        self.assertEqual(len(errors), 1)
        self.assertEqual([f["sequence"] for f in frames], [2])

    def test_send_frame_fails_when_not_connected(self):
        self.assertFalse(serial_reader.SerialTelemetryReader("COM_X").send_frame(b"x\n"))


if __name__ == "__main__":
    unittest.main()
