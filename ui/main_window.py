import time
from datetime import datetime

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports

from com.serial_reader import SerialTelemetryReader
from core.data_logger import DataLogger


_TEMP_FIELDS = ("t1_c", "t2_c", "t3_c", "t4_c", "t5_c")
_TEMP_LABELS = {
    "t1_c": "T1 — Compressor outlet",
    "t2_c": "T2 — Combustor inlet",
    "t3_c": "T3 — Combustor outlet",
    "t4_c": "T4 — Turbine inlet",
    "t5_c": "T5 — Oil",
}
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Turbojet HMI — Read-only telemetry")
        self.resize(1180, 760)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #E5E7E8; color: #20282D; }
            QFrame, QTabWidget::pane {
                background: #F4F5F5; border: 1px solid #B9C0C3;
            }
            QLabel { background: transparent; }
            QPushButton, QComboBox {
                background: #E1E4E5; border: 1px solid #929B9F;
                padding: 6px 10px; color: #20282D;
            }
            QPushButton:disabled { color: #727A7D; }
            QTabBar::tab {
                background: #D8DCDE; padding: 9px 16px;
                border: 1px solid #B9C0C3;
            }
            QTabBar::tab:selected { background: #F4F5F5; font-weight: bold; }
            QListWidget { background: #F4F5F5; border: 1px solid #B9C0C3; }
        """)

        self.reader: SerialTelemetryReader | None = None
        self.logger = DataLogger()
        self._session_started_at: float | None = None
        self._last_frame_at: float | None = None
        self._connected_at: float | None = None
        self._last_sequence: int | None = None
        self._sample_count = 0
        self._last_connection_error = ""
        self._logger_error = ""
        self._active_alarms: dict[str, dict] = {}

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_connection_bar())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_tab(), "OVERVIEW")
        self.tabs.addTab(self._build_temperatures_tab(), "TEMPERATURES")
        self.tabs.addTab(self._build_safety_tab(), "FUEL & SAFETY")
        self.tabs.addTab(self._build_trends_tab(), "TRENDS")
        self.tabs.addTab(self._build_alarms_tab(), "ALARMS")
        layout.addWidget(self.tabs, 1)

        self.status_label = QLabel("No serial connection — no simulated data")
        self.status_label.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Sunken)
        layout.addWidget(self.status_label)

        self._refresh_ports()
        self._stale_timer = QTimer(self)
        self._stale_timer.timeout.connect(self._update_freshness)
        self._stale_timer.start(500)

    def _build_header(self) -> QWidget:
        header = QFrame()
        row = QHBoxLayout(header)
        title = QLabel("TURBOJET HMI  /  TELEMETRY")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        row.addWidget(title)
        row.addStretch()
        read_only = QLabel("READ-ONLY  •  NO ACTUATOR COMMANDS")
        read_only.setStyleSheet("font-weight: bold; color: #46545A;")
        row.addWidget(read_only)
        self.com_label = QLabel("DISCONNECTED")
        self.com_label.setStyleSheet("font-weight: bold; padding-left: 18px;")
        row.addWidget(self.com_label)
        return header

    def _build_connection_bar(self) -> QWidget:
        bar = QFrame()
        row = QHBoxLayout(bar)
        row.addWidget(QLabel("SERIAL PORT"))
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(180)
        row.addWidget(self.port_combo)

        refresh_button = QPushButton("Refresh ports")
        refresh_button.clicked.connect(self._refresh_ports)
        row.addWidget(refresh_button)

        row.addWidget(QLabel("BAUD"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["115200", "57600", "38400", "19200", "9600"])
        row.addWidget(self.baud_combo)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._toggle_connection)
        row.addWidget(self.connect_button)
        row.addStretch()
        return bar

    def _build_overview_tab(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setSpacing(10)

        self.overview_values: dict[str, QLabel] = {}
        for index, (key, title, unit) in enumerate((
            ("rpm", "SHAFT SPEED", "RPM"),
            ("maf_g_s", "AIR FLOW", "g/s"),
            ("delta_t", "CHAMBER ΔT (T3−T2)", "°C"),
            ("gas_max", "MAX GAS READING", "ppm"),
        )):
            card = QFrame()
            card_layout = QVBoxLayout(card)
            name = QLabel(title)
            name.setStyleSheet("font-weight: bold; color: #46545A;")
            value = QLabel("—")
            value.setStyleSheet("font-size: 28px; font-weight: bold;")
            units = QLabel(unit)
            card_layout.addWidget(name)
            card_layout.addWidget(value)
            card_layout.addWidget(units)
            layout.addWidget(card, index // 2, index % 2)
            self.overview_values[key] = value

        self.estop_overview = QLabel("Physical E-STOP: UNKNOWN")
        self.estop_overview.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.estop_overview, 2, 0, 1, 2)
        layout.setRowStretch(3, 1)
        return page

    def _build_temperatures_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.temperature_values: dict[str, QLabel] = {}
        for key in _TEMP_FIELDS:
            value = QLabel("— °C")
            value.setStyleSheet("font-size: 20px;")
            self.temperature_values[key] = value
            form.addRow(_TEMP_LABELS[key], value)
        layout.addLayout(form)

        self.derived_label = QLabel("Derived values require valid sensor readings.")
        layout.addWidget(self.derived_label)
        layout.addStretch()
        return page

    def _build_safety_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.safety_values: dict[str, QLabel] = {}
        form = QFormLayout()
        for key, title in (
            ("mq6_1_ppm", "MQ6 — near tank"),
            ("mq6_2_ppm", "MQ6 — near engine"),
        ):
            value = QLabel("— ppm")
            value.setStyleSheet("font-size: 20px;")
            self.safety_values[key] = value
            form.addRow(title, value)
        self.estop_safety = QLabel("Physical E-STOP input: UNKNOWN")
        form.addRow("Reported hardware input", self.estop_safety)
        layout.addLayout(form)
        note = QLabel(
            "Alarm states shown here are reported by the ESP32. "
            "This HMI does not evaluate safety thresholds or send control commands."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return page

    def _build_trends_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.temperature_plot = pg.PlotWidget()
        self.temperature_plot.setBackground("#F4F5F5")
        self.temperature_plot.showGrid(x=True, y=True, alpha=0.25)
        self.temperature_plot.setLabel("bottom", "Samples received")
        self.temperature_plot.setLabel("left", "Temperature", units="°C")
        self.temperature_plot.addLegend()
        colors = ("#525E64", "#2878A5", "#B45F36", "#7A5988", "#3B8062")
        self._temperature_curves = {
            key: self.temperature_plot.plot(
                pen=pg.mkPen(color, width=2), name=_TEMP_LABELS[key]
            )
            for key, color in zip(_TEMP_FIELDS, colors)
        }
        self._sample_index: list[int] = []
        self._temperature_history = {key: [] for key in _TEMP_FIELDS}
        layout.addWidget(self.temperature_plot)
        return page

    def _build_alarms_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("ACTIVE ALARMS — reported by ESP32"))
        self.active_alarm_list = QListWidget()
        layout.addWidget(self.active_alarm_list, 1)
        layout.addWidget(QLabel("ALARM HISTORY"))
        self.alarm_history_list = QListWidget()
        layout.addWidget(self.alarm_history_list, 1)
        return page

    def _refresh_ports(self):
        current = self.port_combo.currentText() if hasattr(self, "port_combo") else ""
        ports = list(list_ports.comports())
        self.port_combo.clear()
        for port in ports:
            self.port_combo.addItem(port.device, port.device)
        if current:
            index = self.port_combo.findText(current)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
            else:
                self.port_combo.setEditText(current)
        if not ports:
            self.status_label.setText(
                "No serial ports detected. Select a port manually or connect the ESP32."
            )

    def _toggle_connection(self):
        if self.reader is not None and self.reader.isRunning():
            self.reader.requestInterruption()
            self.connect_button.setEnabled(False)
            self.status_label.setText("Waiting for serial reader to disconnect...")
            return

        port = self.port_combo.currentText().strip()
        if not port:
            QMessageBox.warning(self, "Serial port required", "Select or enter a serial port.")
            return
        try:
            baudrate = int(self.baud_combo.currentText())
        except ValueError:
            QMessageBox.warning(self, "Invalid baud rate", "Select a valid baud rate.")
            return

        self._last_frame_at = None
        self._last_sequence = None
        self._last_connection_error = ""
        self._logger_error = ""
        self.reader = SerialTelemetryReader(port, baudrate, self)
        self.reader.telemetry_received.connect(self._on_telemetry)
        self.reader.connection_changed.connect(self._on_connection_changed)
        self.reader.protocol_error.connect(self._on_protocol_error)
        self.reader.finished.connect(self._on_reader_finished)
        self.connect_button.setEnabled(False)
        self.connect_button.setText("Connecting...")
        self.status_label.setText(f"Opening {port}...")
        self.reader.start()

    def _on_connection_changed(self, connected: bool, message: str):
        if connected:
            self._last_connection_error = ""
            self.com_label.setText("CONNECTED")
            self.connect_button.setText("Disconnect")
            self.connect_button.setEnabled(True)
            self.status_label.setText(message)
            self._connected_at = time.monotonic()
            self._session_started_at = time.monotonic()
            try:
                self.logger.start()
                self.status_label.setText(f"{message} — logging to {self.logger.filepath}")
            except OSError as error:
                self._logger_error = str(error)
                self.status_label.setText(f"{message} — logger error: {error}")
        else:
            self.com_label.setText("DISCONNECTED")
            self.connect_button.setText("Connect")
            self.connect_button.setEnabled(True)
            detail = f": {self._last_connection_error}" if self._last_connection_error else ""
            self.status_label.setText(f"{message}{detail}")
            self._connected_at = None
            self._session_started_at = None
            try:
                self.logger.stop()
            except OSError as error:
                self._logger_error = str(error)
                self.status_label.setText(f"Logger error while closing session: {error}")

    def _on_reader_finished(self):
        if self.reader is not None:
            self.reader.deleteLater()
            self.reader = None
        self.connect_button.setEnabled(True)
        self.connect_button.setText("Connect")
        self.com_label.setText("DISCONNECTED")

    def _on_protocol_error(self, message: str):
        self._last_connection_error = message
        self.status_label.setText(f"Serial/protocol error: {message}")

    def _on_telemetry(self, telemetry: dict):
        sequence = telemetry["sequence"]
        if self._last_sequence == sequence:
            self.status_label.setText(
                f"DUPLICATE TELEMETRY FRAME — sequence {sequence}"
            )
            return
        sequence_gap = (
            self._last_sequence is not None
            and sequence > self._last_sequence + 1
        )
        sequence_reset = (
            self._last_sequence is not None
            and sequence < self._last_sequence
        )
        self._last_sequence = sequence
        now = time.monotonic()
        self._last_frame_at = now
        sensors = telemetry["sensors"]
        valid = lambda key: sensors[key] is not None

        for key in _TEMP_FIELDS:
            self.temperature_values[key].setText(
                self._format(sensors[key], "°C", 1)
            )
        for key in self.safety_values:
            self.safety_values[key].setText(self._format(sensors[key], "ppm", 1))

        self.overview_values["rpm"].setText(self._format(sensors["rpm"], "", 0))
        self.overview_values["maf_g_s"].setText(self._format(sensors["maf_g_s"], "", 2))
        if valid("t2_c") and valid("t3_c"):
            delta_t = sensors["t3_c"] - sensors["t2_c"]
            self.overview_values["delta_t"].setText(f"{delta_t:+.1f}")
            chamber_to_turbine = (
                f"{sensors['t3_c'] - sensors['t4_c']:.1f}"
                if valid("t4_c") else "—"
            )
            self.derived_label.setText(
                f"Chamber ΔT (T3−T2): {delta_t:+.1f} °C    "
                f"Chamber-to-turbine ΔT (T3−T4): {chamber_to_turbine} °C"
            )
        else:
            self.overview_values["delta_t"].setText("—")
            self.derived_label.setText("Derived temperatures unavailable.")

        gas_values = [sensors[key] for key in ("mq6_1_ppm", "mq6_2_ppm")]
        gas_values = [value for value in gas_values if value is not None]
        self.overview_values["gas_max"].setText(
            f"{max(gas_values):.1f}" if gas_values else "—"
        )

        released = telemetry["status"]["estop_released"]
        estop_text = {
            True: "RELEASED",
            False: "PRESSED",
            None: "UNKNOWN",
        }[released]
        self.estop_overview.setText(f"Physical E-STOP: {estop_text}")
        self.estop_safety.setText(estop_text)

        self._update_trends(sensors)
        self._update_alarms(telemetry["alarms"])
        if self.logger.is_active and self._session_started_at is not None:
            try:
                self.logger.log(now - self._session_started_at, telemetry)
            except OSError as error:
                self._logger_error = str(error)

        status = f"Receiving telemetry — sequence {sequence}"
        if sequence_gap:
            status += " — sequence gap detected"
        elif sequence_reset:
            status += " — ESP32 sequence counter restarted"
        status += f" — {datetime.now().strftime('%H:%M:%S')} — read-only"
        if self.logger.is_active:
            status += " — logger active"
        if self._logger_error:
            status += f" — logger error: {self._logger_error}"
        self.status_label.setText(status)

    @staticmethod
    def _format(value: float | None, unit: str, decimals: int) -> str:
        if value is None:
            return f"NO DATA {unit}".strip()
        return f"{value:.{decimals}f} {unit}".strip()

    def _update_trends(self, sensors: dict):
        index = self._sample_count
        self._sample_count += 1
        self._sample_index.append(index)
        for key in _TEMP_FIELDS:
            value = sensors[key]
            self._temperature_history[key].append(
                float("nan") if value is None else value
            )
        if len(self._sample_index) > 1200:
            del self._sample_index[:-1200]
            for key in _TEMP_FIELDS:
                del self._temperature_history[key][:-1200]
        for key in _TEMP_FIELDS:
            self._temperature_curves[key].setData(
                self._sample_index, self._temperature_history[key]
            )

    def _update_alarms(self, alarms: list[dict]):
        current = {alarm["code"]: alarm for alarm in alarms}
        for code, alarm in current.items():
            if code not in self._active_alarms or self._active_alarms[code] != alarm:
                self._add_alarm_history(alarm, "ACTIVE")
        for code, alarm in self._active_alarms.items():
            if code not in current:
                self._add_alarm_history(alarm, "CLEARED")
        self._active_alarms = current

        self.active_alarm_list.clear()
        if not current:
            self.active_alarm_list.addItem("No active alarms reported.")
        for alarm in current.values():
            item = QListWidgetItem(
                f"[{alarm['severity'].upper()}] {alarm['code']} — {alarm['message']}"
            )
            if alarm["severity"] == "critical":
                item.setForeground(Qt.GlobalColor.darkRed)
            elif alarm["severity"] == "warning":
                item.setForeground(Qt.GlobalColor.darkYellow)
            self.active_alarm_list.addItem(item)

    def _add_alarm_history(self, alarm: dict, state: str):
        self.alarm_history_list.insertItem(
            0,
            f"{datetime.now().strftime('%H:%M:%S')}  {state}  "
            f"[{alarm['severity'].upper()}] {alarm['code']} — {alarm['message']}",
        )
        if self.alarm_history_list.count() > 500:
            self.alarm_history_list.takeItem(self.alarm_history_list.count() - 1)

    def _update_freshness(self):
        if self.reader is None or not self.reader.isRunning():
            return
        if self._last_frame_at is None:
            if self._connected_at is not None:
                age = time.monotonic() - self._connected_at
                if age > 3:
                    self.status_label.setText(
                        f"NO VALID TELEMETRY — connected for {age:.1f}s"
                    )
            return
        age = time.monotonic() - self._last_frame_at
        if age > 3:
            self.status_label.setText(
                f"STALE TELEMETRY — last valid frame {age:.1f}s ago; no control commands sent"
            )

    def closeEvent(self, event):
        if self.reader is not None and self.reader.isRunning():
            self.reader.requestInterruption()
            if not self.reader.wait(1500):
                event.ignore()
                self.status_label.setText("Waiting for serial connection to close...")
                return
        try:
            self.logger.stop()
        except OSError as error:
            QMessageBox.warning(self, "Logger error", str(error))
        event.accept()
