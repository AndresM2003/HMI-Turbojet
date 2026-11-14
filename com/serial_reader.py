from PyQt6.QtCore import QThread, pyqtSignal
import serial

from core.telemetry_protocol import MAX_FRAME_BYTES, TelemetryProtocolError, parse_telemetry_frame


class SerialTelemetryReader(QThread):
    telemetry_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool, str)
    protocol_error = pyqtSignal(str)

    def __init__(self, port: str, baudrate: int = 115200, parent=None):
        super().__init__(parent)
        self.port = port
        self.baudrate = baudrate

    def run(self):
        try:
            with serial.Serial(self.port, self.baudrate, timeout=1) as connection:
                self.connection_changed.emit(
                    True, f"Connected to {self.port} at {self.baudrate} baud"
                )
                while not self.isInterruptionRequested():
                    frame = connection.readline(MAX_FRAME_BYTES + 1)
                    if not frame:
                        continue
                    try:
                        telemetry = parse_telemetry_frame(frame)
                    except TelemetryProtocolError as error:
                        self.protocol_error.emit(str(error))
                        if len(frame) > MAX_FRAME_BYTES and not frame.endswith(b"\n"):
                            break
                        continue
                    self.telemetry_received.emit(telemetry)
        except serial.SerialException as error:
            self.protocol_error.emit(f"Serial connection error: {error}")
        finally:
            self.connection_changed.emit(False, "Disconnected")
