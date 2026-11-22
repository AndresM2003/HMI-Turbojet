import time
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)
from serial.tools import list_ports

from com.serial_reader import SerialTelemetryReader
from core.checklist import STARTUP_IGNITION, STARTUP_PRECHECKS, ChecklistEngine, Snapshot
from core.data_logger import DataLogger
from core.limits import LIMITS
from ui.checklist_widgets import ChecklistPanel, FlowPanel, LiveValues, card
from ui.command_center import CommandCenter
from ui.control_panel import ControlPanel
from ui.theme import WINDOW_STYLE

_FLOW = [
    ("link", "Telemetry link"), ("estop", "Physical E-STOP released"),
    ("thermocouples", "Thermocouples T1–T5"), ("maf_rpm", "MAF and RPM"),
    ("gas_reporting", "Gas sensors reporting"), ("gas_limit", "Gas below limit"),
    ("no_critical", "No critical alarms"), ("authorize", "OPERATOR AUTHORIZES IGNITION"),
    ("airflow", "Airflow established"), ("combustion", "Combustion detected"),
    ("spinning", "Turbine spinning"), ("ready", "ENGINE RUNNING → MAIN VIEW"),
]


class StartupWindow(QWidget):
    """Arranque: conexión serial → verificaciones previas → autorización → monitoreo de ignición.

    El HMI es de solo lectura: no envía comandos al motor. La ignición se hace desde el
    controlador; aquí se verifica y se registra desde el inicio (data logging).
    """

    session_ready = pyqtSignal(object, object, float)  # reader, logger, started_at
    preview_requested = pyqtSignal(bool)  # True = con datos simulados

    def __init__(self, limits=LIMITS, commands: CommandCenter | None = None):
        super().__init__()
        self.commands = commands or CommandCenter()
        self.setWindowTitle("Turbojet Control System — Startup")
        self.resize(1320, 800)
        self.setMinimumSize(1180, 720)
        self.setStyleSheet(WINDOW_STYLE)

        self.reader: SerialTelemetryReader | None = None
        self.logger = DataLogger()
        self.pre_engine = ChecklistEngine(STARTUP_PRECHECKS, limits)
        self.ign_engine = ChecklistEngine(STARTUP_IGNITION, limits)
        self._phase = "connect"  # connect | prechecks | ignition
        self._telemetry: dict | None = None
        self._last_frame_at: float | None = None
        self._started_at: float | None = None
        self._handed_off = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_connect_page())
        self.stack.addWidget(self._build_sequence_page())
        root.addWidget(self.stack, 1)
        self.footer = QLabel("Select the serial port and connect")
        self.footer.setFixedHeight(28)
        self.footer.setContentsMargins(12, 0, 12, 0)
        self.footer.setStyleSheet("background: #D4E3EE; color: #34505F; font-size: 10px;")
        root.addWidget(self.footer)

        self._refresh_ports()
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick)
        self._clock.start(500)
        self._tick()

    # ---------- construcción ----------
    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setFixedHeight(54)
        header.setStyleSheet("background: #D4E3EE; border-bottom: 3px solid #1F6FA8;")
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 0, 14, 0)
        title = QLabel("TURBOJET CONTROL SYSTEM")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #14202A;")
        self.phase_label = QLabel("STARTUP — CONNECT")
        self.phase_label.setStyleSheet("font-size: 10px; font-weight: bold; color: #1F6FA8;")
        self.phase_label.setMinimumWidth(360)
        self.clock_label = QLabel()
        self.clock_label.setStyleSheet("font-size: 9px; color: #4A565D;")
        row.addWidget(title)
        row.addSpacing(30)
        row.addWidget(self.phase_label)
        row.addStretch()
        row.addWidget(self.clock_label)
        return header

    def _build_connect_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.setSpacing(16)
        title = QLabel("STARTUP SEQUENCE")
        title.setStyleSheet("font-size: 30px; font-weight: bold; letter-spacing: 4px; color: #14202A;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)
        warning = QLabel(
            "Before starting, make sure the physical safety checks are done and the area is clear.\n"
            "Commands go to the ESP32 and only count as done when it sends an ACK.\n"
            "Data logging starts when you press BEGIN."
        )
        warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning.setStyleSheet("font-size: 11px; color: #8A5A00; border: 1px solid #C9A24A; padding: 14px;")
        outer.addWidget(warning, alignment=Qt.AlignmentFlag.AlignCenter)

        conn = QHBoxLayout()
        conn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(130)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["115200", "57600", "38400", "19200", "9600"])
        scan = QPushButton("SCAN")
        scan.clicked.connect(self._refresh_ports)
        self.connect_button = QPushButton("CONNECT")
        self.connect_button.setMinimumWidth(110)
        self.connect_button.clicked.connect(self._toggle_connection)
        for widget in (self.port_combo, self.baud_combo, scan, self.connect_button):
            conn.addWidget(widget)
        outer.addLayout(conn)

        self.link_label = QLabel("COM: DISCONNECTED")
        self.link_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.link_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #B3261E;")
        outer.addWidget(self.link_label)
        self.begin_button = QPushButton("▶  BEGIN STARTUP SEQUENCE")
        self.begin_button.setFixedSize(320, 54)
        self.begin_button.setEnabled(False)
        self.begin_button.setStyleSheet("font-size: 13px; font-weight: bold; color: #1F6FA8; border: 2px solid #1F6FA8;")
        self.begin_button.clicked.connect(self._begin)
        outer.addWidget(self.begin_button, alignment=Qt.AlignmentFlag.AlignCenter)

        preview_note = QLabel("Preview (no hardware, no logging, no checks):")
        preview_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_note.setStyleSheet("font-size: 10px; color: #5F6B73;")
        outer.addWidget(preview_note)
        preview_row = QHBoxLayout()
        preview_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for text, simulated in (("OPEN INTERFACE — EMPTY", False), ("OPEN INTERFACE — SIMULATED DATA", True)):
            button = QPushButton(text)
            button.setStyleSheet("font-size: 10px; color: #4A565D;")
            button.clicked.connect(lambda checked=False, sim=simulated: self.preview_requested.emit(sim))
            preview_row.addWidget(button)
        outer.addLayout(preview_row)
        return page

    def _build_sequence_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(12, 10, 12, 10)
        column.setSpacing(8)
        top = QWidget()
        row = QHBoxLayout(top)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        self.pre_panel = ChecklistPanel("A. Pre-checks (automatic)", STARTUP_PRECHECKS)
        self.ign_panel = ChecklistPanel("B. Ignition monitoring (after authorization)", STARTUP_IGNITION)
        self.pre_panel.confirm_requested.connect(lambda key: self._confirm(self.pre_engine, key))
        self.ign_panel.confirm_requested.connect(lambda key: self._confirm(self.ign_engine, key))
        left_layout.addWidget(self.pre_panel)
        left_layout.addWidget(self.ign_panel)
        row.addWidget(left, 5)

        self.flow = FlowPanel("Sequence", _FLOW)
        row.addWidget(self.flow, 3)

        status, layout = card("Status")
        self.status_label = QLabel("PRE-CHECKS RUNNING")
        self.status_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #8A5A00;")
        self.counter_label = QLabel("0 / 0 checks passed")
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
        self.authorize_button = QPushButton("AUTHORIZE IGNITION")
        self.authorize_button.setFixedHeight(40)
        self.authorize_button.clicked.connect(self._authorize)
        self.enter_button = QPushButton("ENTER MAIN VIEW")
        self.enter_button.setFixedHeight(40)
        self.enter_button.clicked.connect(self._enter_main)
        layout.addWidget(self.authorize_button)
        layout.addWidget(self.enter_button)
        row.addWidget(status, 3)
        column.addWidget(top, 1)
        self.control_panel = ControlPanel(self.commands, groups=("control_mode", "oil_pump", "fuel_solenoid", "fuel_servo", "spark_pulse", "emergency_stop"))
        self.control_panel.set_locked("Authorize ignition first")
        column.addWidget(self.control_panel)
        return page

    # ---------- conexión ----------
    def _refresh_ports(self):
        current = self.port_combo.currentText()
        self.port_combo.clear()
        for port in list_ports.comports():
            self.port_combo.addItem(port.device)
        if current:
            self.port_combo.setEditText(current)

    def _toggle_connection(self):
        if self.reader is not None and self.reader.isRunning():
            self.reader.requestInterruption()
            self.connect_button.setEnabled(False)
            return
        port = self.port_combo.currentText().strip()
        if not port:
            QMessageBox.warning(self, "Serial port required", "Select or enter a serial port.")
            return
        self._telemetry = None
        self._last_frame_at = None
        self.reader = SerialTelemetryReader(port, int(self.baud_combo.currentText()))
        self.commands.set_reader(self.reader)
        self.reader.telemetry_received.connect(self._on_telemetry)
        self.reader.connection_changed.connect(self._on_connection_changed)
        self.reader.protocol_error.connect(lambda msg: self.footer.setText(f"SERIAL / PROTOCOL ERROR: {msg}"))
        self.reader.finished.connect(self._on_reader_finished)
        self.connect_button.setEnabled(False)
        self.connect_button.setText("CONNECTING")
        self.reader.start()

    def _on_connection_changed(self, connected: bool, message: str):
        self.link_label.setText("COM: CONNECTED" if connected else "COM: DISCONNECTED")
        self.link_label.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {'#1E7B45' if connected else '#B3261E'};")
        self.connect_button.setText("DISCONNECT" if connected else "CONNECT")
        self.connect_button.setEnabled(True)
        self.footer.setText(message)
        if not connected:
            self.begin_button.setEnabled(False)
            self.commands.reset()

    def _on_reader_finished(self):
        if self.reader is not None and not self._handed_off:
            self.reader.deleteLater()
            self.reader = None
        self.connect_button.setText("CONNECT")
        self.connect_button.setEnabled(True)

    def _on_telemetry(self, telemetry: dict):
        self.commands.update_telemetry(telemetry)
        now = time.monotonic()
        self._telemetry = telemetry
        self._last_frame_at = now
        if self._phase == "connect":
            self.begin_button.setEnabled(True)
            return
        if self.logger.is_active and self._started_at is not None:
            try:
                self.logger.log(now - self._started_at, telemetry)
            except OSError as error:
                self.footer.setText(f"DATA LOGGER ERROR: {error}")
        self._evaluate()

    # ---------- secuencia ----------
    def _begin(self):
        try:
            self.logger.start()
        except OSError as error:
            QMessageBox.critical(self, "Data logger", f"Could not start logging:\n{error}")
            return
        self._started_at = time.monotonic()
        self._phase = "prechecks"
        self.pre_engine.start()
        self.ign_panel.set_pending()
        self.stack.setCurrentIndex(1)
        self.phase_label.setText("STARTUP — PRE-CHECKS")
        self.footer.setText(f"DATA LOGGER: ACTIVE   FILE: {self.logger.filepath}")
        self._evaluate()

    def _confirm(self, engine: ChecklistEngine, key: str):
        engine.confirm_manual(key)
        self._evaluate()

    def _authorize(self):
        answer = QMessageBox.question(
            self, "Authorize ignition",
            "Confirm that the ignition sequence is authorized.\n\n"
            "Fuel and spark commands unlock after this. Run the ignition with the CONTROL strip; the HMI verifies it.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._phase = "ignition"
        self.ign_engine.start()
        self.control_panel.set_locked(None)
        self.phase_label.setText("STARTUP — IGNITION MONITORING")
        self._evaluate()

    def _enter_main(self):
        self._handed_off = True
        self._clock.stop()
        for signal, slot in ((self.reader.telemetry_received, self._on_telemetry),
                             (self.reader.connection_changed, self._on_connection_changed),
                             (self.reader.finished, self._on_reader_finished)):
            signal.disconnect(slot)
        self.session_ready.emit(self.reader, self.logger, self._started_at)
        self.close()

    def _snapshot(self) -> Snapshot:
        telemetry = self._telemetry or {"sensors": {}, "alarms": [], "status": {"estop_released": None}}
        age = None if self._last_frame_at is None else time.monotonic() - self._last_frame_at
        return Snapshot(telemetry["sensors"], telemetry["alarms"], telemetry["status"]["estop_released"], age)

    def _evaluate(self):
        if self._phase == "connect":
            return
        snapshot = self._snapshot()
        pre = self.pre_engine.update(snapshot)
        self.pre_panel.set_statuses(pre)
        states = {key: status.state for key, status in pre.items()}
        total = len(self.pre_engine.specs)
        passed = self.pre_engine.passed_count
        if self._phase == "ignition":
            ign = self.ign_engine.update(snapshot)
            self.ign_panel.set_statuses(ign)
            states.update({key: status.state for key, status in ign.items()})
            total += len(self.ign_engine.specs)
            passed += self.ign_engine.passed_count
        pre_ok = self.pre_engine.all_ok
        ign_ok = self._phase == "ignition" and self.ign_engine.all_ok
        states["authorize"] = "OK" if self._phase == "ignition" else ("WAIT" if pre_ok else "PENDING")
        states["ready"] = "OK" if (pre_ok and ign_ok) else "PENDING"
        self.flow.set_states(states)

        self.progress.setRange(0, total)
        self.progress.setValue(passed)
        self.counter_label.setText(f"{passed} / {total} checks passed")
        self.authorize_button.setEnabled(self._phase == "prechecks" and pre_ok)
        self.enter_button.setEnabled(pre_ok and ign_ok)
        faults = [s for s in list(pre.values()) if s.state == "FAULT"]
        if pre_ok and ign_ok:
            text, color = "READY — ENTER MAIN VIEW", "#1E7B45"
        elif faults:
            text, color = "FAULT — CHECK THE LIST", "#B3261E"
        elif self._phase == "ignition":
            text, color = "MONITORING IGNITION", "#8A5A00"
        elif pre_ok:
            text, color = "PRE-CHECKS PASSED — AUTHORIZE", "#1E7B45"
        else:
            text, color = "PRE-CHECKS RUNNING", "#8A5A00"
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {color};")
        self.live.set_sensors(self._telemetry["sensors"] if self._telemetry else None)
        released = snapshot.estop_released
        self.estop_label.setText(
            "E-STOP (physical): " + {True: "RELEASED", False: "PRESSED", None: "UNKNOWN"}[released])

    def _tick(self):
        self.clock_label.setText(datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))
        self._evaluate()

    # ---------- cierre ----------
    def closeEvent(self, event):
        if not self._handed_off:
            if self.reader is not None and self.reader.isRunning():
                self.reader.requestInterruption()
                self.reader.wait(1500)
            try:
                self.logger.stop()
            except OSError:
                pass
        event.accept()
