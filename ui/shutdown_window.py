import time
from datetime import datetime

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget

from core.checklist import SHUTDOWN_CHECKS, ChecklistEngine, Snapshot
from core.limits import LIMITS
from ui.checklist_widgets import ChecklistPanel, FlowPanel, LiveValues, card
from ui.command_center import CommandCenter
from ui.control_panel import ControlPanel
from ui.theme import WINDOW_STYLE

_FLOW = [
    ("start", "Operator stops the engine (controller)"), ("flame_out", "Combustion stopped"),
    ("gas_limit", "Gas below limit"), ("cooled", "Cooling: T3 and T4 below limit"),
    ("rpm_stopped", "Turbine stopped"), ("done", "SHUTDOWN COMPLETE"),
]


class ShutdownWindow(QWidget):
    """Monitorea el apagado con la telemetría. No envía comandos (HMI de solo lectura)."""

    back_requested = pyqtSignal()
    session_closed = pyqtSignal()

    def __init__(self, reader, limits=LIMITS, commands: CommandCenter | None = None):
        super().__init__()
        self.commands = commands or CommandCenter()
        self.setWindowTitle("Turbojet Control System — Shutdown")
        self.resize(1320, 800)
        self.setMinimumSize(1180, 720)
        self.setStyleSheet(WINDOW_STYLE)
        self.engine = ChecklistEngine(SHUTDOWN_CHECKS, limits)
        self.engine.start()
        self._telemetry: dict | None = None
        self._last_frame_at = time.monotonic()
        self._confirmed = False
        self._force_close = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QFrame()
        header.setFixedHeight(54)
        header.setStyleSheet("background: #D4E3EE; border-bottom: 3px solid #1F6FA8;")
        hrow = QHBoxLayout(header)
        hrow.setContentsMargins(18, 0, 14, 0)
        title = QLabel("TURBOJET CONTROL SYSTEM")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #14202A;")
        phase = QLabel("SHUTDOWN SEQUENCE")
        phase.setStyleSheet("font-size: 10px; font-weight: bold; color: #8A5A00;")
        phase.setMinimumWidth(240)
        self.clock_label = QLabel()
        self.clock_label.setStyleSheet("font-size: 9px; color: #4A565D;")
        hrow.addWidget(title)
        hrow.addSpacing(30)
        hrow.addWidget(phase)
        hrow.addStretch()
        hrow.addWidget(self.clock_label)
        root.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(12, 10, 12, 10)
        body.setSpacing(10)
        self.panel = ChecklistPanel("Shutdown checklist (automatic)", SHUTDOWN_CHECKS)
        self.panel.confirm_requested.connect(self._confirm_manual)
        self.flow = FlowPanel("Sequence", _FLOW)
        body.addWidget(self.panel, 5)
        body.addWidget(self.flow, 3)

        status, layout = card("Status")
        self.status_label = QLabel("COOLING DOWN")
        self.status_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #8A5A00;")
        self.counter_label = QLabel()
        self.counter_label.setStyleSheet("font-size: 10px; color: #55626A;")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.live = LiveValues()
        self.estop_label = QLabel("E-STOP (physical): UNKNOWN")
        self.estop_label.setStyleSheet("font-size: 10px;")
        for widget in (self.status_label, self.counter_label, self.progress, self.live, self.estop_label):
            layout.addWidget(widget)
        layout.addStretch()
        note = QLabel("The software EMERGENCY STOP sends a command to the ESP32 (it must ACK). It does not replace the physical E-STOP.")
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 9px; color: #B3261E;")
        layout.addWidget(note)
        self.confirm_button = QPushButton("CONFIRM SHUTDOWN COMPLETE")
        self.close_session_button = QPushButton("CLOSE SESSION (stop logging)")
        back = QPushButton("BACK TO MAIN VIEW")
        for button in (self.confirm_button, self.close_session_button, back):
            button.setFixedHeight(38)
            layout.addWidget(button)
        self.confirm_button.clicked.connect(self._confirm_done)
        self.close_session_button.clicked.connect(self._close_session)
        back.clicked.connect(self.back_requested)
        body.addWidget(status, 3)
        body_widget = QWidget()
        body_widget.setLayout(body)
        root.addWidget(body_widget, 1)
        self.control_panel = ControlPanel(
            self.commands, groups=("control_mode", "oil_pump", "fuel_solenoid", "fuel_servo", "emergency_stop"))
        control_row = QHBoxLayout()
        control_row.setContentsMargins(12, 0, 12, 10)
        control_row.addWidget(self.control_panel)
        root.addLayout(control_row)

        self._reader = reader
        if reader is not None:
            reader.telemetry_received.connect(self._on_telemetry)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(500)
        self._tick()

    def _on_telemetry(self, telemetry: dict):
        self._telemetry = telemetry
        self._last_frame_at = time.monotonic()
        self._evaluate()

    def _confirm_manual(self, key: str):
        self.engine.confirm_manual(key)
        self._evaluate()

    def _evaluate(self):
        telemetry = self._telemetry or {"sensors": {}, "alarms": [], "status": {"estop_released": None}}
        snapshot = Snapshot(telemetry["sensors"], telemetry["alarms"], telemetry["status"]["estop_released"],
                            time.monotonic() - self._last_frame_at)
        statuses = self.engine.update(snapshot)
        self.panel.set_statuses(statuses)
        states = {key: s.state for key, s in statuses.items()}
        states["start"] = "OK"
        states["done"] = "OK" if self._confirmed else ("WAIT" if self.engine.all_ok else "PENDING")
        self.flow.set_states(states)
        total = len(self.engine.specs)
        self.progress.setRange(0, total)
        self.progress.setValue(self.engine.passed_count)
        self.counter_label.setText(f"{self.engine.passed_count} / {total} checks passed")
        self.confirm_button.setEnabled(self.engine.all_ok and not self._confirmed)
        self.close_session_button.setEnabled(self._confirmed)
        if self._confirmed:
            text, color = "SHUTDOWN COMPLETE", "#1E7B45"
        elif self.engine.all_ok:
            text, color = "ALL CHECKS PASSED — CONFIRM", "#1E7B45"
        elif any(s.state == "FAULT" for s in statuses.values()):
            text, color = "FAULT — CHECK THE LIST", "#B3261E"
        else:
            text, color = "COOLING DOWN", "#8A5A00"
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {color};")
        self.live.set_sensors(self._telemetry["sensors"] if self._telemetry else None)
        released = snapshot.estop_released
        self.estop_label.setText("E-STOP (physical): " + {True: "RELEASED", False: "PRESSED", None: "UNKNOWN"}[released])

    def _tick(self):
        self.clock_label.setText(datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))
        self._evaluate()

    def _confirm_done(self):
        self._confirmed = True
        self._evaluate()

    def _close_session(self):
        answer = QMessageBox.question(
            self, "Close session", "Stop logging, disconnect and return to the startup screen?")
        if answer == QMessageBox.StandardButton.Yes:
            self._force_close = True
            self.session_closed.emit()

    def dismiss(self):
        self._force_close = True
        self._timer.stop()
        if self._reader is not None:
            try:
                self._reader.telemetry_received.disconnect(self._on_telemetry)
            except (TypeError, RuntimeError):
                pass
        self.close()

    def closeEvent(self, event):
        # Cerrar con la X vuelve a la vista principal: así no se abandona el monitoreo sin querer.
        if self._force_close:
            self._timer.stop()
            event.accept()
        else:
            event.ignore()
            self.back_requested.emit()
