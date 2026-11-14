import time
from datetime import datetime

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports

from com.serial_reader import SerialTelemetryReader
from core.data_logger import DataLogger
from core.telemetry_protocol import SENSOR_FIELDS
from widgets.hmi_visuals import ProcessMimic, RPMGauge


_TEMP_FIELDS = ("t1_c", "t2_c", "t3_c", "t4_c", "t5_c")
_TEMP_LABELS = {
    "t1_c": "T1  Compressor outlet",
    "t2_c": "T2  Combustor inlet",
    "t3_c": "T3  Combustor outlet",
    "t4_c": "T4  Turbine inlet",
    "t5_c": "T5  Oil",
}
_DARK_STYLE = """
    QMainWindow, QWidget { background: #202529; color: #D1D7DA; }
    QFrame#card { background: #292F34; border: 1px solid #485158; }
    QLabel { background: transparent; }
    QPushButton, QComboBox {
        background: #30373C; border: 1px solid #586168; padding: 5px 8px;
        color: #D1D7DA;
    }
    QPushButton:hover { border-color: #70A9CF; }
    QPushButton:disabled { color: #788187; }
    QTabWidget::pane { border: 0; background: #202529; }
    QTabBar { background: #171B1E; }
    QTabBar::tab {
        background: #171B1E; color: #9BA5AA; padding: 12px 17px;
        border: 0; border-right: 1px solid #252B2F;
    }
    QTabBar::tab:selected {
        color: #7DB8DF; background: #252B30;
        border: 1px solid #70A9CF; border-bottom: 2px solid #70A9CF;
    }
    QListWidget { background: #292F34; border: 1px solid #485158; }
    QComboBox QAbstractItemView {
        background: #292F34; color: #D1D7DA; selection-background-color: #455660;
    }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Turbojet Control System")
        self.resize(1360, 800)
        self.setMinimumSize(1160, 680)
        self.setStyleSheet(_DARK_STYLE)

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
        self._histories = {field: [] for field in SENSOR_FIELDS}
        self._sample_index: list[int] = []
        self._trend_curves: dict[str, dict[str, pg.PlotDataItem]] = {}
        self._trend_plots: dict[str, pg.PlotWidget] = {}

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())

        self.alarm_banner = QLabel("NO ACTIVE ALARMS REPORTED")
        self.alarm_banner.setFixedHeight(30)
        self.alarm_banner.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.alarm_banner.setContentsMargins(12, 0, 8, 0)
        self._set_banner("idle", "NO ACTIVE ALARMS REPORTED")
        layout.addWidget(self.alarm_banner)

        self.pages = QStackedWidget()
        for page in (
            self._build_overview_tab(),
            self._build_temperatures_tab(),
            self._build_safety_tab(),
            self._build_trends_tab(),
            self._build_alarms_tab(),
        ):
            self.pages.addWidget(page)
        layout.addWidget(self.pages, 1)

        self.footer = QLabel("DATA LOGGER: WAITING FOR CONNECTION")
        self.footer.setFixedHeight(28)
        self.footer.setContentsMargins(12, 0, 12, 0)
        self.footer.setStyleSheet(
            "background: #171B1E; color: #A3ADB2; font-size: 10px;"
        )
        layout.addWidget(self.footer)

        self._refresh_ports()
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        self._stale_timer = QTimer(self)
        self._stale_timer.timeout.connect(self._update_freshness)
        self._stale_timer.start(500)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setFixedHeight(54)
        header.setStyleSheet("background: #171B1E; border-bottom: 1px solid #3D464C;")
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 0, 14, 0)
        row.setSpacing(5)

        title = QLabel("TURBOJET CONTROL SYSTEM")
        title.setMinimumWidth(198)
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #E1E5E7;")
        row.addWidget(title)

        self.nav_buttons = []
        for index, name in enumerate(
            ("OVERVIEW", "TEMPERATURES", "FUEL & SAFETY", "TRENDS", "ALARMS")
        ):
            button = QPushButton(name)
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setMinimumWidth(77 if index != 2 else 98)
            button.setStyleSheet("""
                QPushButton {
                    background: transparent; color: #9BA5AA; border: 0;
                    border-bottom: 2px solid transparent; padding: 8px 5px;
                    font-size: 9px; font-weight: bold;
                }
                QPushButton:checked {
                    color: #7DB8DF; background: #252B30;
                    border: 1px solid #70A9CF; border-bottom: 2px solid #70A9CF;
                }
                QPushButton:hover:!checked { color: #D1D7DA; }
            """)
            button.clicked.connect(lambda checked, page=index: self._switch_page(page))
            self.nav_buttons.append(button)
            row.addWidget(button)

        row.addSpacing(4)

        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(82)
        self.port_combo.setMaximumWidth(100)
        self.port_combo.lineEdit().setPlaceholderText("COM port")
        row.addWidget(self.port_combo)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["115200", "57600", "38400", "19200", "9600"])
        self.baud_combo.setCurrentText("115200")
        self.baud_combo.setMaximumWidth(78)
        row.addWidget(self.baud_combo)
        refresh_button = QPushButton("SCAN")
        refresh_button.setFixedWidth(40)
        refresh_button.setStyleSheet("font-size: 8px; padding: 5px 3px;")
        refresh_button.setToolTip("Refresh serial ports")
        refresh_button.clicked.connect(self._refresh_ports)
        row.addWidget(refresh_button)
        self.connect_button = QPushButton("CONNECT")
        self.connect_button.setFixedWidth(78)
        self.connect_button.clicked.connect(self._toggle_connection)
        row.addWidget(self.connect_button)

        self.com_label = QLabel("COM: DISCONNECTED")
        self.com_label.setMinimumWidth(115)
        self.com_label.setStyleSheet("font-size: 9px; font-weight: bold;")
        row.addWidget(self.com_label)
        self.clock_label = QLabel()
        self.clock_label.setStyleSheet("color: #A3ADB2; font-size: 9px;")
        row.addWidget(self.clock_label)
        return header

    def _switch_page(self, index: int):
        self.pages.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)

    @staticmethod
    def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        heading = QLabel(title.upper())
        heading.setStyleSheet(
            "font-size: 9px; font-weight: bold; color: #9BA5AA; letter-spacing: 1px;"
        )
        layout.addWidget(heading)
        return frame, layout

    @staticmethod
    def _make_plot(title: str, unit: str | None = None) -> pg.PlotWidget:
        plot = pg.PlotWidget()
        plot.setBackground("#292F34")
        plot.showGrid(x=True, y=True, alpha=0.16)
        plot.setLabel("bottom", "TIME", units="s", **{"color": "#AAB3B8"})
        if unit:
            plot.setLabel("left", title, units=unit, **{"color": "#AAB3B8"})
        else:
            plot.setLabel("left", title, **{"color": "#AAB3B8"})
        for axis_name in ("left", "bottom"):
            axis = plot.getPlotItem().getAxis(axis_name)
            axis.setPen(pg.mkPen("#69747A"))
            axis.setTextPen(pg.mkPen("#AAB3B8"))
        plot.getPlotItem().getAxis("bottom").enableAutoSIPrefix(False)
        plot.getPlotItem().setMenuEnabled(False)
        plot.getPlotItem().hideButtons()
        return plot

    @staticmethod
    def _value_label(size: int = 20) -> QLabel:
        label = QLabel("—")
        label.setStyleSheet(
            f"font-size: {size}px; font-weight: bold; color: #E1E5E7;"
        )
        return label

    def _build_overview_tab(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setSpacing(8)
        grid.setColumnStretch(0, 22)
        grid.setColumnStretch(1, 52)
        grid.setColumnStretch(2, 26)
        grid.setRowStretch(0, 3)
        grid.setRowStretch(1, 2)

        left = QWidget()
        left.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        gauge_card, gauge_layout = self._card("RPM")
        self.rpm_gauge = RPMGauge()
        gauge_layout.addWidget(self.rpm_gauge, 1)
        left_layout.addWidget(gauge_card, 3)

        values_card, values_layout = self._card("Key values")
        self.overview_values = {}
        for key, title, unit in (
            ("maf_g_s", "Air flow (MAF)", "g/s"),
            ("delta_t", "Chamber ΔT (T3−T2)", "°C"),
            ("gas_max", "Gas max (MQ6)", "ppm"),
        ):
            row, value = self._value_row(title, unit, 16)
            values_layout.addLayout(row)
            self.overview_values[key] = value
        left_layout.addWidget(values_card, 2)

        state_card, state_layout = self._card("Read-only status")
        self.overview_estop = QLabel("E-STOP (physical): UNKNOWN")
        self.overview_estop.setStyleSheet("font-size: 11px; color: #B5BEC2;")
        self.overview_link = QLabel("TELEMETRY: NO DATA")
        self.overview_link.setStyleSheet("font-size: 11px; color: #B5BEC2;")
        state_layout.addWidget(self.overview_estop)
        state_layout.addWidget(self.overview_link)
        left_layout.addWidget(state_card, 1)
        grid.addWidget(left, 0, 0, 2, 1)

        process_card, process_layout = self._card("Process")
        self.process_mimic = ProcessMimic()
        process_layout.addWidget(self.process_mimic, 1)
        grid.addWidget(process_card, 0, 1)

        thermal_card, thermal_layout = self._card(
            "Thermal profile — compressor outlet to turbine inlet"
        )
        self.thermal_plot = self._make_plot("TEMPERATURE", "°C")
        self.thermal_plot.setLabel("bottom", "TEMPERATURE POINT")
        self.thermal_plot.setXRange(-0.2, 3.2, padding=0)
        self.thermal_plot.getPlotItem().getAxis("bottom").setTicks([[
            (0, "T1"), (1, "T2"), (2, "T3"), (3, "T4")
        ]])
        self.thermal_curve = self.thermal_plot.plot(
            pen=pg.mkPen("#70A9CF", width=3),
            symbol="o",
            symbolSize=8,
            symbolBrush="#D1D7DA",
            symbolPen=pg.mkPen("#70A9CF", width=2),
        )
        thermal_layout.addWidget(self.thermal_plot, 1)
        self.derived_summary = QLabel(
            "ΔT chamber: —     ΔT chamber → turbine: —     Heat input: not configured"
        )
        self.derived_summary.setStyleSheet("font-size: 10px; color: #B5BEC2;")
        thermal_layout.addWidget(self.derived_summary)
        grid.addWidget(thermal_card, 1, 1)

        right = QWidget()
        right.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        alarms_card, alarms_layout = self._card("Alarms")
        self.overview_alarm_list = QListWidget()
        alarms_layout.addWidget(self.overview_alarm_list, 1)
        right_layout.addWidget(alarms_card, 1)
        trend_card, trend_layout = self._card("Temperature trend")
        self.overview_temp_plot = self._make_plot("TEMPERATURE", "°C")
        self.overview_temp_plot.addLegend(offset=(8, 8))
        self.overview_curves = self._add_temp_curves(self.overview_temp_plot)
        trend_layout.addWidget(self.overview_temp_plot, 1)
        right_layout.addWidget(trend_card, 1)
        grid.addWidget(right, 0, 2, 2, 1)
        return page

    def _build_temperatures_tab(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setSpacing(8)
        grid.setColumnStretch(0, 22)
        grid.setColumnStretch(1, 52)
        grid.setColumnStretch(2, 26)

        temp_card, temp_layout = self._card("Temperatures")
        self.temperature_values: dict[str, QLabel] = {}
        for key in _TEMP_FIELDS:
            row = QHBoxLayout()
            name = QLabel(_TEMP_LABELS[key])
            name.setStyleSheet("font-size: 10px; color: #B4BDC1;")
            value = self._value_label(18)
            unit = QLabel("°C")
            unit.setStyleSheet("font-size: 9px; color: #8F9A9F;")
            row.addWidget(name, 1)
            row.addWidget(value)
            row.addWidget(unit)
            temp_layout.addLayout(row)
            temp_layout.addWidget(self._neutral_bar())
            self.temperature_values[key] = value
        temp_note = QLabel("Limits not configured — values shown without status grading.")
        temp_note.setWordWrap(True)
        temp_note.setStyleSheet("font-size: 9px; color: #9BA5AA;")
        temp_layout.addWidget(temp_note)
        temp_layout.addStretch()
        grid.addWidget(temp_card, 0, 0, 2, 1)

        process_card, process_layout = self._card("Process — temperature points")
        self.temp_process_mimic = ProcessMimic()
        process_layout.addWidget(self.temp_process_mimic, 1)
        grid.addWidget(process_card, 0, 1)

        derived_card, derived_layout = self._card("Derived values")
        derived_row = QHBoxLayout()
        self.temp_derived = QLabel("CHAMBER ΔT (T3−T2)\n—")
        self.temp_derived_turbine = QLabel("CHAMBER → TURBINE (T3−T4)\n—")
        self.heat_estimate = QLabel("HEAT INPUT Q̇\nRequires validated cp")
        for label in (
            self.temp_derived,
            self.temp_derived_turbine,
            self.heat_estimate,
        ):
            label.setStyleSheet(
                "font-size: 12px; font-weight: bold; color: #D4DADD; "
                "padding: 8px;"
            )
            label.setWordWrap(True)
            derived_row.addWidget(label, 1)
        derived_layout.addLayout(derived_row)
        derived_layout.addStretch()
        grid.addWidget(derived_card, 1, 1)

        plots = QWidget()
        plots.setStyleSheet("background: transparent;")
        plots_layout = QVBoxLayout(plots)
        plots_layout.setContentsMargins(0, 0, 0, 0)
        plots_layout.setSpacing(8)
        temp_plot_card, temp_plot_layout = self._card("Temperature vs time")
        self.temperature_plot = self._make_plot("TEMPERATURE", "°C")
        self.temperature_plot.addLegend(offset=(8, 8))
        self.temperature_curves = self._add_temp_curves(self.temperature_plot)
        temp_plot_layout.addWidget(self.temperature_plot, 1)
        plots_layout.addWidget(temp_plot_card, 1)

        rpm_plot_card, rpm_plot_layout = self._card("Temperature vs RPM / air flow")
        self.temperature_rpm_plot = self._make_plot("T3", "°C")
        self.temperature_rpm_plot.setLabel("bottom", "RPM")
        self.temperature_rpm_curve = self.temperature_rpm_plot.plot(
            pen=pg.mkPen("#D29364", width=2), symbol="o", symbolSize=4
        )
        rpm_plot_layout.addWidget(self.temperature_rpm_plot, 1)
        plots_layout.addWidget(rpm_plot_card, 1)
        grid.addWidget(plots, 0, 2, 2, 1)
        return page

    def _build_safety_tab(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setSpacing(8)
        grid.setColumnStretch(0, 29)
        grid.setColumnStretch(1, 43)
        grid.setColumnStretch(2, 28)

        gas_card, gas_layout = self._card("Gas safety (MQ6)")
        self.safety_values: dict[str, QLabel] = {}
        for key, title in (
            ("mq6_1_ppm", "GAS 1 — near tank"),
            ("mq6_2_ppm", "GAS 2 — near engine"),
        ):
            item = QFrame()
            item.setStyleSheet("background: #252B30; border: 1px solid #424B51;")
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(10, 8, 10, 8)
            name = QLabel(title)
            name.setStyleSheet("font-size: 10px; color: #AAB3B8;")
            value = self._value_label(24)
            value.setText("— ppm")
            item_layout.addWidget(name)
            item_layout.addWidget(value)
            item_layout.addWidget(self._neutral_bar())
            item_layout.addWidget(QLabel("Thresholds: not configured in HMI"))
            gas_layout.addWidget(item)
            self.safety_values[key] = value
        gas_note = QLabel(
            "Alarm state is supplied by the ESP32. No thresholds or safety actions are configured here."
        )
        gas_note.setWordWrap(True)
        gas_note.setStyleSheet("font-size: 9px; color: #AAB3B8;")
        gas_layout.addWidget(gas_note)
        gas_layout.addStretch()
        grid.addWidget(gas_card, 0, 0, 2, 1)

        line_card, line_layout = self._card("Fuel line — telemetry labels only")
        line_layout.addStretch()
        pipeline = QHBoxLayout()
        for label in ("C3H8 SOURCE", "GAS 1\nNEAR TANK", "GAS 2\nNEAR ENGINE", "ENGINE"):
            node = QLabel(label)
            node.setAlignment(Qt.AlignmentFlag.AlignCenter)
            node.setMinimumHeight(72)
            node.setStyleSheet(
                "background: #252B30; border: 1px solid #59636A; "
                "color: #CBD2D5; padding: 5px; font-size: 9px;"
            )
            pipeline.addWidget(node, 1)
            if label != "ENGINE":
                arrow = QLabel("→")
                arrow.setStyleSheet("font-size: 18px; color: #869198;")
                pipeline.addWidget(arrow)
        line_layout.addLayout(pipeline)
        line_layout.addStretch()
        disclaimer = QLabel(
            "This diagram identifies monitored locations only. Valve, pump, spark and interlock states are not available in the read-only protocol."
        )
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("font-size: 9px; color: #AAB3B8;")
        line_layout.addWidget(disclaimer)
        grid.addWidget(line_card, 0, 1)

        measures_card, measures_layout = self._card("Reported status")
        self.estop_safety = QLabel("PHYSICAL E-STOP: UNKNOWN")
        self.maf_safety = QLabel("MAF: —")
        for label in (self.estop_safety, self.maf_safety):
            label.setStyleSheet("font-size: 14px; color: #D1D7DA;")
            measures_layout.addWidget(label)
        measures_layout.addStretch()
        grid.addWidget(measures_card, 1, 1)

        alarms_card, alarms_layout = self._card("ESP32 alarms")
        self.safety_alarm_list = QListWidget()
        alarms_layout.addWidget(self.safety_alarm_list, 1)
        grid.addWidget(alarms_card, 0, 2, 2, 1)
        return page

    def _build_trends_tab(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setSpacing(8)
        for index, key in enumerate(("temperature", "rpm", "maf_g_s", "mq6")):
            title, unit = {
                "temperature": ("THERMAL PROFILE", "°C"),
                "rpm": ("SHAFT SPEED", "RPM"),
                "maf_g_s": ("AIR FLOW", "g/s"),
                "mq6": ("GAS SENSORS", "ppm"),
            }[key]
            card, layout = self._card(title)
            plot = self._make_plot(title, unit)
            if key != "temperature":
                plot.setLabel("left", unit, **{"color": "#AAB3B8"})
            if key == "temperature":
                plot.addLegend(offset=(8, 8))
                self._all_temp_plot = plot
                self._all_temp_trend_curves = self._add_temp_curves(plot)
            else:
                plot.addLegend(offset=(8, 8))
                self._trend_curves[key] = {}
                self._trend_plots[key] = plot
                fields = {
                    "rpm": ("rpm",),
                    "maf_g_s": ("maf_g_s",),
                    "mq6": ("mq6_1_ppm", "mq6_2_ppm"),
                }[key]
                colors = ("#70A9CF", "#D29364")
                for field, color in zip(fields, colors):
                    self._trend_curves[key][field] = plot.plot(
                        pen=pg.mkPen(color, width=2),
                        symbol="o",
                        symbolSize=3,
                        symbolBrush=color,
                        name=field.upper(),
                    )
            layout.addWidget(plot, 1)
            grid.addWidget(card, index // 2, index % 2)
        return page

    def _build_alarms_tab(self) -> QWidget:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        active_card, active_layout = self._card("Active alarms — reported by ESP32")
        self.active_alarm_list = QListWidget()
        active_layout.addWidget(self.active_alarm_list, 1)
        history_card, history_layout = self._card("Alarm history")
        self.alarm_history_list = QListWidget()
        history_layout.addWidget(self.alarm_history_list, 1)
        grid.addWidget(active_card, 0, 0)
        grid.addWidget(history_card, 0, 1)
        return page

    @staticmethod
    def _neutral_bar() -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(9)
        bar.setStyleSheet("background: #454E54; border: 0;")
        return bar

    @staticmethod
    def _value_row(title: str, unit: str, size: int):
        row = QHBoxLayout()
        name = QLabel(title)
        name.setStyleSheet("font-size: 10px; color: #AAB3B8;")
        value = MainWindow._value_label(size)
        units = QLabel(unit)
        units.setStyleSheet("font-size: 9px; color: #8F9A9F;")
        row.addWidget(name, 1)
        row.addWidget(value)
        row.addWidget(units)
        return row, value

    @staticmethod
    def _add_temp_curves(plot: pg.PlotWidget):
        curves = {}
        colors = ("#6EADD4", "#A9C6D9", "#D58B5A", "#C6AE76", "#6BA786")
        for key, color in zip(_TEMP_FIELDS, colors):
            curves[key] = plot.plot(
                pen=pg.mkPen(color, width=2), name=key.upper()
            )
        return curves

    def _set_banner(self, state: str, text: str):
        styles = {
            "idle": "background: #30373C; color: #AFB8BC;",
            "warning": "background: #493514; color: #E7B444;",
            "critical": "background: #4B2525; color: #E77C70;",
            "stale": "background: #4A3521; color: #E7B444;",
        }
        self.alarm_banner.setStyleSheet(
            f"font-size: 10px; font-weight: bold; {styles[state]}"
        )
        self.alarm_banner.setText(text)

    def _refresh_ports(self):
        current = self.port_combo.currentText() if hasattr(self, "port_combo") else ""
        self.port_combo.clear()
        ports = list(list_ports.comports())
        for port in ports:
            self.port_combo.addItem(port.device, port.device)
        if current:
            index = self.port_combo.findText(current)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
            else:
                self.port_combo.setEditText(current)

    def _toggle_connection(self):
        if self.reader is not None and self.reader.isRunning():
            self.reader.requestInterruption()
            self.connect_button.setEnabled(False)
            self.connect_button.setText("DISCONNECTING")
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
        self.connect_button.setText("CONNECTING")
        self.footer.setText(f"OPENING SERIAL PORT {port}...")
        self.reader.start()

    def _on_connection_changed(self, connected: bool, message: str):
        if connected:
            self._last_connection_error = ""
            self.com_label.setText("COM: CONNECTED")
            self.com_label.setStyleSheet("font-size: 10px; font-weight: bold; color: #76B893;")
            self.connect_button.setText("DISCONNECT")
            self.connect_button.setEnabled(True)
            self._connected_at = time.monotonic()
            self._session_started_at = self._connected_at
            try:
                self.logger.start()
                self.footer.setText(f"DATA LOGGER: ACTIVE   FILE: {self.logger.filepath}")
            except OSError as error:
                self._logger_error = str(error)
                self.footer.setText(f"DATA LOGGER ERROR: {error}")
        else:
            self.com_label.setText("COM: DISCONNECTED")
            self.com_label.setStyleSheet("font-size: 10px; font-weight: bold; color: #D87970;")
            detail = f" — {self._last_connection_error}" if self._last_connection_error else ""
            self.footer.setText(f"COM: DISCONNECTED{detail}")
            self._connected_at = None
            self._session_started_at = None
            try:
                self.logger.stop()
            except OSError as error:
                self.footer.setText(f"DATA LOGGER CLOSE ERROR: {error}")
            self._set_banner("stale", "TELEMETRY DISCONNECTED — LAST VALUES ARE STALE")
            self.overview_link.setText("TELEMETRY: DISCONNECTED")

    def _on_reader_finished(self):
        if self.reader is not None:
            self.reader.deleteLater()
            self.reader = None
        self.connect_button.setEnabled(True)
        self.connect_button.setText("CONNECT")

    def _on_protocol_error(self, message: str):
        self._last_connection_error = message
        self.footer.setText(f"SERIAL / PROTOCOL ERROR: {message}")

    def _on_telemetry(self, telemetry: dict):
        sequence = telemetry["sequence"]
        if self._last_sequence == sequence:
            self.footer.setText(f"DUPLICATE TELEMETRY FRAME — SEQUENCE {sequence}")
            return
        sequence_gap = self._last_sequence is not None and sequence > self._last_sequence + 1
        sequence_reset = self._last_sequence is not None and sequence < self._last_sequence
        self._last_sequence = sequence

        now = time.monotonic()
        self._last_frame_at = now
        sensors = telemetry["sensors"]
        self.process_mimic.set_sensors(sensors)
        self.temp_process_mimic.set_sensors(sensors)
        self.rpm_gauge.set_value(sensors["rpm"])

        for key, label in self.temperature_values.items():
            label.setText(self._format(sensors[key], 1))
        for key, label in self.safety_values.items():
            label.setText(self._format(sensors[key], 1, "ppm"))

        self.overview_values["maf_g_s"].setText(self._format(sensors["maf_g_s"], 2))
        self.overview_values["gas_max"].setText(
            self._format(
                max(value for value in (sensors["mq6_1_ppm"], sensors["mq6_2_ppm"]) if value is not None)
                if any(sensors[key] is not None for key in ("mq6_1_ppm", "mq6_2_ppm"))
                else None,
                1,
            )
        )
        t2, t3, t4 = sensors["t2_c"], sensors["t3_c"], sensors["t4_c"]
        delta_chamber = t3 - t2 if t2 is not None and t3 is not None else None
        delta_turbine = t3 - t4 if t3 is not None and t4 is not None else None
        self.overview_values["delta_t"].setText(self._format(delta_chamber, 1))
        self.derived_summary.setText(
            f"ΔT chamber (T3−T2): {self._format(delta_chamber, 1, '°C')}     "
            f"ΔT chamber → turbine (T3−T4): {self._format(delta_turbine, 1, '°C')}     "
            "Heat input: requires validated cp"
        )
        self.temp_derived.setText(
            f"ΔT chamber (T3−T2): {self._format(delta_chamber, 1, '°C')}"
        )
        self.temp_derived_turbine.setText(
            f"ΔT chamber → turbine (T3−T4): {self._format(delta_turbine, 1, '°C')}"
        )

        t_values = [sensors[key] for key in ("t1_c", "t2_c", "t3_c", "t4_c")]
        self.thermal_curve.setData(
            [index for index, value in enumerate(t_values) if value is not None],
            [value for value in t_values if value is not None],
        )
        self._update_histories(sensors)
        self._update_alarm_views(telemetry["alarms"])

        released = telemetry["status"]["estop_released"]
        estop = "RELEASED" if released is True else "PRESSED" if released is False else "UNKNOWN"
        self.overview_estop.setText(f"E-STOP (physical): {estop}")
        self.estop_safety.setText(f"PHYSICAL E-STOP: {estop}")
        self.maf_safety.setText(f"MAF: {self._format(sensors['maf_g_s'], 2, 'g/s')}")
        self.overview_link.setText(f"TELEMETRY: LIVE   SEQUENCE {sequence}")

        if self.logger.is_active and self._session_started_at is not None:
            try:
                self.logger.log(now - self._session_started_at, telemetry)
            except OSError as error:
                self._logger_error = str(error)

        if self._active_alarms:
            highest = max(
                self._active_alarms.values(),
                key=lambda alarm: {"info": 0, "warning": 1, "critical": 2}[alarm["severity"]],
            )
            state = {
                "critical": "critical",
                "warning": "warning",
                "info": "idle",
            }[highest["severity"]]
            self._set_banner(
                state,
                f"▲ {len(self._active_alarms)} ACTIVE ALARM"
                f"{'S' if len(self._active_alarms) != 1 else ''} — "
                f"{highest['code']} ({highest['severity'].upper()})",
            )
        else:
            self._set_banner("idle", "NO ACTIVE ALARMS REPORTED BY ESP32")

        elapsed = int(now - self._session_started_at) if self._session_started_at else 0
        run_time = f"{elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}"
        status = f"DATA LOGGER: {'ACTIVE' if self.logger.is_active else 'OFF'}   RUN TIME: {run_time}   E-STOP (physical): {estop}   SAMPLE: {sequence}"
        if sequence_gap:
            status += "   SEQUENCE GAP"
        elif sequence_reset:
            status += "   SEQUENCE RESTARTED"
        if self._logger_error:
            status += f"   LOGGER ERROR: {self._logger_error}"
        self.footer.setText(status)

    @staticmethod
    def _format(value: float | None, decimals: int = 1, unit: str = "") -> str:
        if value is None:
            return f"— {unit}".strip()
        return f"{value:,.{decimals}f} {unit}".strip()

    def _update_histories(self, sensors: dict):
        index = (
            time.monotonic() - self._session_started_at
            if self._session_started_at is not None
            else float(self._sample_count)
        )
        self._sample_count += 1
        self._sample_index.append(index)
        for field in SENSOR_FIELDS:
            value = sensors[field]
            self._histories[field].append(float("nan") if value is None else value)
        if len(self._sample_index) > 1200:
            del self._sample_index[:-1200]
            for history in self._histories.values():
                del history[:-1200]

        for curves in (
            self.overview_curves,
            self.temperature_curves,
            self._all_temp_trend_curves,
        ):
            for field, curve in curves.items():
                curve.setData(self._sample_index, self._histories[field])
        for plot in (
            self.overview_temp_plot,
            self.temperature_plot,
            self._all_temp_plot,
        ):
            plot.setXRange(max(0, index - 60), max(60, index), padding=0)
        self.temperature_rpm_curve.setData(
            self._histories["rpm"], self._histories["t3_c"]
        )
        for plot_key, curves in self._trend_curves.items():
            for field, curve in curves.items():
                curve.setData(self._sample_index, self._histories[field])
            self._trend_plots[plot_key].setXRange(
                max(0, index - 60), max(60, index), padding=0
            )

    def _update_alarm_views(self, alarms: list[dict]):
        current = {alarm["code"]: alarm for alarm in alarms}
        for code, alarm in current.items():
            if code not in self._active_alarms or self._active_alarms[code] != alarm:
                self._add_alarm_history(alarm, "ACTIVE")
        for code, alarm in self._active_alarms.items():
            if code not in current:
                self._add_alarm_history(alarm, "CLEARED")
        self._active_alarms = current

        lists = (
            self.overview_alarm_list,
            self.safety_alarm_list,
            self.active_alarm_list,
        )
        for alarm_list in lists:
            alarm_list.clear()
            if not current:
                alarm_list.addItem("No active alarms reported.")
                continue
            for alarm in current.values():
                item = QListWidgetItem(
                    f"●  {alarm['code']}  —  {alarm['message']}   "
                    f"[{alarm['severity'].upper()}]"
                )
                if alarm["severity"] == "critical":
                    item.setForeground(QColor("#E77C70"))
                elif alarm["severity"] == "warning":
                    item.setForeground(QColor("#E7B444"))
                else:
                    item.setForeground(QColor("#70A9CF"))
                alarm_list.addItem(item)

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
            if self._connected_at is not None and time.monotonic() - self._connected_at > 3:
                self._set_banner("stale", "SERIAL CONNECTED — WAITING FOR VALID TELEMETRY")
            return
        age = time.monotonic() - self._last_frame_at
        if age > 3:
            self._set_banner("stale", f"STALE TELEMETRY — LAST VALID FRAME {age:.1f}s AGO")
            self.overview_link.setText(f"TELEMETRY: STALE ({age:.1f}s)")

    def _update_clock(self):
        self.clock_label.setText(datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))

    def closeEvent(self, event):
        if self.reader is not None and self.reader.isRunning():
            self.reader.requestInterruption()
            if not self.reader.wait(1500):
                event.ignore()
                self.footer.setText("WAITING FOR SERIAL CONNECTION TO CLOSE...")
                return
        try:
            self.logger.stop()
        except OSError as error:
            QMessageBox.warning(self, "Logger error", str(error))
        event.accept()
