import threading

from PyQt6.QtCore import QThread, pyqtSignal
import serial

from core.commands import CommandProtocolError, parse_command_ack
from core.telemetry_protocol import MAX_FRAME_BYTES, TelemetryProtocolError, parse_telemetry_frame


class SerialTelemetryReader(QThread):
    telemetry_received = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool, str)
    protocol_error = pyqtSignal(str)
    command_ack = pyqtSignal(dict)

    def __init__(self, port: str, baudrate: int = 115200, parent=None):
        super().__init__(parent)
        self.port = port
        self.baudrate = baudrate
        self._connection = None
        self._write_lock = threading.Lock()
        self.ignored_lines = 0

    def send_frame(self, data: bytes) -> bool:
        """Escribe una línea de comando en el puerto. Devuelve False si no hay conexión."""
        with self._write_lock:
            connection = self._connection
            if connection is None or not connection.is_open:
                return False
            try:
                connection.write(data)
                connection.flush()
                return True
            except (serial.SerialException, OSError):
                return False

    def _open(self):
        connection = serial.Serial()
        connection.port = self.port
        connection.baudrate = self.baudrate
        connection.timeout = 1
        # Abrir el puerto no debe reiniciar la ESP32 (el auto-reset de muchas placas usa DTR/RTS).
        connection.dtr = False
        connection.rts = False
        connection.open()
        connection.reset_input_buffer()  # descarta datos viejos / una trama cortada a la mitad
        return connection

    def run(self):
        connection = None
        try:
            connection = self._open()
            self._connection = connection
            self.connection_changed.emit(
                True, f"Connected to {self.port} at {self.baudrate} baud"
            )
            while not self.isInterruptionRequested():
                frame = connection.readline(MAX_FRAME_BYTES + 1)
                if not frame:
                    continue
                if not frame.lstrip().startswith(b"{"):
                    self.ignored_lines += 1  # log de depuración / mensajes de arranque de la ESP32
                    continue
                if b'"command_ack"' in frame:
                    try:
                        self.command_ack.emit(parse_command_ack(frame))
                    except CommandProtocolError as error:
                        self.protocol_error.emit(f"Invalid command ack: {error}")
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
            self._connection = None
            if connection is not None:
                try:
                    connection.close()
                except (serial.SerialException, OSError):
                    pass
            self.connection_changed.emit(False, "Disconnected")
