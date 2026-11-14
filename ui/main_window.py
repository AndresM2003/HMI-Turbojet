# ui/main_window.py

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGridLayout, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QFrame, QMessageBox, QPushButton
)
from PyQt6.QtCore import Qt, QTimer
from datetime import datetime

from ui.panels import EngineDataPanel, ConfigurablePlotPanel
from ui.control_panel import ControlPanel
from ui.commands_panel import CommandsPanel
from ui.systems_panel import SystemsPanel
from core.engine_state import EngineState, EngineStatus
from widgets.rpm_gauge import RPMGauge
from widgets.alerts_panel import AlertsPanel, Alert
from widgets.brayton_plot import BraytonPlot


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Turbojet HMI")
        self.resize(1280, 780)
        self.setStyleSheet("background-color: #F1F5F9; color: #1F2937;")

        self.engine = EngineState()

        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(6)
        central.setLayout(root_layout)

        root_layout.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_overview_page())
        self.stack.addWidget(self._build_systems_page())
        root_layout.addWidget(self.stack, stretch=1)

        root_layout.addWidget(self._build_statusbar())

        # ==========================
        # REGISTRO DE ALERTAS
        # — se registran pero no se muestran hasta que se activen
        # ==========================
        self.alerts_panel.register_alert(Alert(name="egt_high",      message="HIGH EGT WARNING",  level="warning"))
        self.alerts_panel.register_alert(Alert(name="fuel_low",      message="LOW FUEL LEVEL",     level="critical"))
        self.alerts_panel.register_alert(Alert(name="rpm_over",      message="RPM OVERLIMIT",      level="critical"))
        self.alerts_panel.register_alert(Alert(name="pressure_low",  message="LOW PRESSURE",       level="warning"))
        self.alerts_panel.register_alert(Alert(name="pressure_high", message="HIGH PRESSURE",      level="critical"))

        # ==========================
        # SEÑALES
        # ==========================
        self.control_panel.stop_requested.connect(self.on_stop)
        self.control_panel.emergency_requested.connect(self.on_emergency)
        self.commands_panel.reset_alarms_btn.clicked.connect(
            self.alerts_panel.reset_alarms
        )

        # ==========================
        # TIMERS
        # ==========================
        self._clock_timer = QTimer()
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        self._run_seconds = 0
        self._run_timer   = QTimer()
        self._run_timer.timeout.connect(self._update_runtime)

        self._set_state(EngineStatus.RUNNING, "RUNNING")
        self.set_com_status(True)
        self._run_timer.start(1000)

    # =====================================================
    # HEADER
    # =====================================================
    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setFixedHeight(48)
        header.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border-bottom: 1px solid #CBD5E1;
            }
        """)

        layout = QHBoxLayout()
        layout.setContentsMargins(16, 0, 16, 0)
        header.setLayout(layout)

        title = QLabel("TURBOJET <span style='font-weight:normal;'>CONTROL SYSTEM</span>")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2937;")
        layout.addWidget(title)

        layout.addSpacing(24)

        self.btn_overview = self._make_nav_btn("OVERVIEW", active=True)
        self.btn_systems  = self._make_nav_btn("SYSTEMS",  active=False)
        self.btn_overview.clicked.connect(lambda: self._switch_page(0))
        self.btn_systems.clicked.connect(lambda:  self._switch_page(1))

        layout.addWidget(self.btn_overview)
        layout.addWidget(self.btn_systems)

        layout.addStretch()

        com_label = QLabel("COM STATUS:")
        com_label.setStyleSheet("font-size: 12px; color: #475569;")
        layout.addWidget(com_label)

        self.com_status_label = QLabel("DISCONNECTED")
        self.com_status_label.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #e74c3c;"
        )
        layout.addWidget(self.com_status_label)

        layout.addSpacing(24)

        self.clock_label = QLabel("")
        self.clock_label.setStyleSheet("font-size: 12px; color: #475569;")
        layout.addWidget(self.clock_label)

        return header

    def _make_nav_btn(self, text: str, active: bool) -> QPushButton:
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #475569; font-size: 12px; font-weight: bold;
                padding: 6px 16px; border: none;
                border-bottom: 2px solid transparent;
            }
            QPushButton:checked {
                color: #2563EB; border-bottom: 2px solid #2563EB;
            }
            QPushButton:hover:!checked { color: #475569; }
        """)
        return btn

    def _switch_page(self, index: int):
        self.stack.setCurrentIndex(index)
        self.btn_overview.setChecked(index == 0)
        self.btn_systems.setChecked(index == 1)

    # =====================================================
    # OVERVIEW PAGE
    # =====================================================
    def _build_overview_page(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)
        page.setLayout(layout)

        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 3)
        layout.setColumnStretch(2, 2)
        layout.setRowStretch(0, 3)
        layout.setRowStretch(1, 2)

        # --- Columna izquierda ---
        self.data_panel    = EngineDataPanel()
        self.control_panel = ControlPanel()

        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_widget.setLayout(left_layout)
        left_layout.addWidget(self.data_panel, stretch=1)
        left_layout.addWidget(self.control_panel, stretch=1)
        layout.addWidget(left_widget, 0, 0, 2, 1)

        # --- Centro superior: gauge ---
        self.rpm_gauge = RPMGauge()
        self.rpm_gauge.setMinimumSize(300, 300)
        layout.addWidget(self.rpm_gauge, 0, 1)

        # --- Centro inferior: gráfica Brayton (fija) ---
        self.brayton_plot = BraytonPlot()
        layout.addWidget(self.brayton_plot, 1, 1)

        # --- Derecha superior: alerts + commands ---
        right_top = QWidget()
        right_top_layout = QVBoxLayout()
        right_top_layout.setSpacing(8)
        right_top_layout.setContentsMargins(0, 0, 0, 0)
        right_top.setLayout(right_top_layout)

        self.alerts_panel   = AlertsPanel()
        self.commands_panel = CommandsPanel()

        right_top_layout.addWidget(self.alerts_panel,   stretch=1)
        right_top_layout.addWidget(self.commands_panel, stretch=1)
        layout.addWidget(right_top, 0, 2)

        # --- Derecha inferior: gráfica configurable ---
        self.fuel_plot_panel = ConfigurablePlotPanel(
            default_signals=["fuel_flow", "pressure"]
        )
        layout.addWidget(self.fuel_plot_panel, 1, 2)

        return page

    # =====================================================
    # SYSTEMS PAGE
    # =====================================================
    def _build_systems_page(self) -> QWidget:
        self.systems_panel = SystemsPanel()
        return self.systems_panel

    # =====================================================
    # STATUS BAR
    # =====================================================
    def _build_statusbar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(36)
        bar.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border-top: 1px solid #CBD5E1;
            }
        """)

        layout = QHBoxLayout()
        layout.setContentsMargins(16, 0, 16, 0)
        bar.setLayout(layout)

        datalogger_label = QLabel(
            "🟢  DATA LOGGER: <span style='color:#2ecc71;'>ACTIVE</span>"
        )
        datalogger_label.setTextFormat(Qt.TextFormat.RichText)
        datalogger_label.setStyleSheet("font-size: 11px; color: #475569;")
        layout.addWidget(datalogger_label)

        layout.addSpacing(32)

        temp_label = QLabel(
            f"🔴  TEMP LIMIT: <span style='color:#1F2937;'>"
            f"{EngineState().limits.egt_warning:.0f} °C</span>"
        )
        temp_label.setTextFormat(Qt.TextFormat.RichText)
        temp_label.setStyleSheet("font-size: 11px; color: #475569;")
        layout.addWidget(temp_label)

        layout.addSpacing(32)

        self.runtime_label = QLabel(
            "⏱  RUN TIME: <span style='color:#1F2937;'>00:00:00</span>"
        )
        self.runtime_label.setTextFormat(Qt.TextFormat.RichText)
        self.runtime_label.setStyleSheet("font-size: 11px; color: #475569;")
        layout.addWidget(self.runtime_label)

        layout.addStretch()

        return bar

    # =====================================================
    # CLOCK / RUNTIME
    # =====================================================
    def _update_clock(self):
        self.clock_label.setText(datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))

    def _update_runtime(self):
        self._run_seconds += 1
        h = self._run_seconds // 3600
        m = (self._run_seconds % 3600) // 60
        s = self._run_seconds % 60
        self.runtime_label.setText(
            f"⏱  RUN TIME: <span style='color:#1F2937;'>{h:02d}:{m:02d}:{s:02d}</span>"
        )

    # =====================================================
    # COM STATUS
    # =====================================================
    def set_com_status(self, connected: bool):
        self.engine.connected = connected
        if connected:
            self.com_status_label.setText("CONNECTED")
            self.com_status_label.setStyleSheet(
                "font-size: 12px; font-weight: bold; color: #2ecc71;"
            )
        else:
            self.com_status_label.setText("DISCONNECTED")
            self.com_status_label.setStyleSheet(
                "font-size: 12px; font-weight: bold; color: #e74c3c;"
            )

    # =====================================================
    # UI UPDATE
    # =====================================================
    def update_ui(self, data: dict, t: float):
        self.engine.update(data)

        if self.engine.is_active:
            engine_dict = self.engine.to_dict()

            self.data_panel.update_data(engine_dict)
            self.fuel_plot_panel.update_plot(t, engine_dict)
            self.rpm_gauge.set_value(self.engine.rpm)
            self.systems_panel.update_data(data)
            self.brayton_plot.update_cycle(data)

            for name, active in self.engine.check_alerts().items():
                self.alerts_panel.update_alert(name, active)

        else:
            self.data_panel.clear()
            self.fuel_plot_panel.freeze()
            self.rpm_gauge.set_value(0)
            self.systems_panel.clear()
            self.brayton_plot.clear()
            for name in self.engine.check_alerts():
                self.alerts_panel.update_alert(name, False)

    # =====================================================
    # CONTROL CALLBACKS
    # =====================================================
    def _set_state(self, status: EngineStatus, state_str: str):
        self.engine.set_status(status)
        self.control_panel.set_engine_state(state_str)
        self.commands_panel.set_engine_state(state_str)

    def on_stop(self):
        self._set_state(EngineStatus.STOPPING, "STOPPING")
        self._run_timer.stop()
        QTimer.singleShot(3000, self._on_engine_idle)

    def _on_engine_idle(self):
        if self.engine.status == EngineStatus.STOPPING:
            self._set_state(EngineStatus.IDLE, "IDLE")
            self.set_com_status(False)

    def on_emergency(self):
        self._set_state(EngineStatus.EMERGENCY, "EMERGENCY")
        self._run_timer.stop()
        self.set_com_status(False)

        QMessageBox.critical(
            self,
            "EMERGENCY SHUTDOWN",
            "Emergency shutdown activated.\nResolve the fault before restarting.",
        )
        self._set_state(EngineStatus.IDLE, "IDLE")
        self.control_panel.emergency_btn.setText("EMERGENCY SHUTDOWN")
        self.control_panel.emergency_btn.setEnabled(True)