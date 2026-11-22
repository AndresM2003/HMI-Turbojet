import csv
import os
import time
from dataclasses import dataclass
from datetime import datetime

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.command_log import format_event
from core.commands import CommandProtocolError, build_command_frame
from core.interlocks import MANUAL_COMMANDS, InterlockContext, check_command, needs_confirmation

ACK_TIMEOUT_S = 3.0


@dataclass
class CommandState:
    value: object = None
    status: str = "IDLE"  # SENDING | ACK | REJECTED | NO_ACK | FAILED
    message: str = ""


class CommandCenter(QObject):
    """Envía comandos al ESP32, espera su ACK, aplica enclavamientos y deja un registro.

    Un comando solo cuenta como ejecutado cuando el ESP32 lo confirma (ACK). El registro de
    auditoría va en logs/commands_AAAAMMDD.csv, aparte del CSV de telemetría.
    """

    changed = pyqtSignal()
    log_event = pyqtSignal(str, str)  # (nivel, texto) para el LOG de la pantalla principal

    def __init__(self, logs_dir: str = "logs", parent=None):
        super().__init__(parent)
        self.reader = None
        self.preview = False
        self.states: dict[str, CommandState] = {}
        self.confirmed_mode = "auto"  # último modo confirmado con ACK por el ESP32
        self._pending: dict[int, tuple[str, object, float]] = {}
        self._next_id = 1
        self._telemetry: dict | None = None
        self._logs_dir = logs_dir
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_timeouts)
        self._timer.start(500)

    # ---------- enlace con el lector serial ----------
    def set_reader(self, reader):
        if self.reader is not None:
            try:
                self.reader.command_ack.disconnect(self._on_ack)
            except (TypeError, RuntimeError, AttributeError):
                pass
        self.reader = reader
        if reader is not None:
            reader.command_ack.connect(self._on_ack)
        self.changed.emit()

    def set_preview(self, enabled: bool):
        self.preview = enabled
        self.changed.emit()

    def reset(self):
        self.states.clear()
        self._pending.clear()
        self.confirmed_mode = "auto"
        self.changed.emit()

    def update_telemetry(self, telemetry: dict):
        self._telemetry = telemetry
        self.changed.emit()

    @property
    def manual_mode(self) -> bool:
        return self.confirmed_mode == "manual"

    def note(self, level: str, text: str):
        """Línea informativa en el LOG (p. ej. conexión / desconexión)."""
        self.log_event.emit(level, text)

    @property
    def connected(self) -> bool:
        return self.preview or (self.reader is not None and self.reader.isRunning())

    # ---------- enclavamientos ----------
    def _context(self) -> InterlockContext:
        telemetry = self._telemetry
        estop = telemetry["status"]["estop_released"] if telemetry else None
        critical = None
        if telemetry:
            critical = next((a["code"] for a in telemetry["alarms"] if a["severity"] == "critical"), None)
        acked = {command: state.value for command, state in self.states.items() if state.status == "ACK"}
        acked["control_mode"] = self.confirmed_mode
        return InterlockContext(self.connected, estop, critical, acked)

    def check(self, command: str, value=None) -> tuple[bool, str]:
        return check_command(command, value, self._context())

    def confirmation_text(self, command: str, value=None) -> str | None:
        rpm = self._telemetry["sensors"].get("rpm") if self._telemetry else None
        return needs_confirmation(command, value, rpm)

    # ---------- envío y ACK ----------
    def send(self, command: str, value=None) -> tuple[bool, str]:
        allowed, reason = self.check(command, value)
        if not allowed:
            self._audit("-", command, value, "BLOCKED", reason)
            return False, reason
        command_id = self._next_id
        try:
            frame = build_command_frame(command_id, command, value)
        except CommandProtocolError as error:
            return False, str(error)
        self._next_id += 1
        self.states[command] = CommandState(value, "SENDING")
        self._pending[command_id] = (command, value, time.monotonic())
        self._audit(command_id, command, value, "SENT", "")
        if self.preview:
            QTimer.singleShot(250, lambda: self._on_ack({"id": command_id, "ok": True, "message": "simulated"}))
        elif self.reader is None or not self.reader.send_frame(frame):
            self._pending.pop(command_id, None)
            self.states[command] = CommandState(value, "FAILED", "Serial write failed")
            self._audit(command_id, command, value, "FAILED", "Serial write failed")
            self.changed.emit()
            return False, "Serial write failed"
        self.changed.emit()
        return True, ""

    def _on_ack(self, ack: dict):
        item = self._pending.pop(ack["id"], None)
        if item is None:
            return
        command, value, _ = item
        status = "ACK" if ack["ok"] else "REJECTED"
        self.states[command] = CommandState(value, status, ack.get("message", ""))
        if command == "control_mode" and status == "ACK":
            self.confirmed_mode = value
            if value == "auto":  # el controlador retoma las salidas: lo comandado a mano ya no vale
                for manual in MANUAL_COMMANDS:
                    self.states.pop(manual, None)
        self._audit(ack["id"], command, value, status, ack.get("message", ""))
        self.changed.emit()

    def _check_timeouts(self):
        now = time.monotonic()
        changed = False
        for command_id, (command, value, sent_at) in list(self._pending.items()):
            state = self.states.get(command)
            if now - sent_at > ACK_TIMEOUT_S and state and state.status == "SENDING":
                state.status = "NO_ACK"
                self._audit(command_id, command, value, "NO_ACK", "")
                changed = True
            if now - sent_at > 30:
                self._pending.pop(command_id, None)
        if changed:
            self.changed.emit()

    # ---------- auditoría ----------
    def _audit(self, command_id, command, value, event, message):
        level, text = format_event(event, command, value, message)
        self.log_event.emit(level, text)
        try:
            os.makedirs(self._logs_dir, exist_ok=True)
            path = os.path.join(self._logs_dir, f"commands_{datetime.now():%Y%m%d}.csv")
            is_new = not os.path.exists(path)
            with open(path, "a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                if is_new:
                    writer.writerow(["timestamp", "id", "command", "value", "event", "message", "preview"])
                writer.writerow([datetime.now().isoformat(timespec="milliseconds"), command_id, command,
                                 "" if value is None else value, event, message, int(self.preview)])
        except OSError:
            pass
