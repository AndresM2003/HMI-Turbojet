# ui/startup_window.py

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from dataclasses import dataclass, field
from datetime import datetime


# =====================================================
# Modelo de check
# =====================================================
@dataclass
class StartupCheck:
    key:          str
    label:        str
    description:  str
    sensor_key:   str
    check_fn:     object
    wait_mode:    bool  = False   # True → reintenta hasta timeout
    timeout_s:    float = 30.0    # segundos máximos de espera (solo en wait_mode)
    status:       str   = "pending"
    _elapsed_s:   float = field(default=0.0, repr=False)


# =====================================================
# Secuencia de checks
# =====================================================
STARTUP_CHECKS = [
    # Tipo binario — falla inmediata si no está OK
    StartupCheck("sensors",      "Sensor check",           "Verifying all sensors are responding",
                 "rpm",           lambda v: v >= 0,
                 wait_mode=False),

    # Tipo espera — puede tardar en alcanzar el valor
    StartupCheck("oil_temp",     "Oil temperature",        "Waiting for oil to reach operating temperature (50–90 °C)",
                 "oil_temp",      lambda v: 50 <= v <= 90,
                 wait_mode=True,  timeout_s=60.0),

    # Tipo binario
    StartupCheck("oil_pump",     "Oil pump",               "Verifying oil pump is running",
                 "oil_pressure",  lambda v: v >= 1.5,
                 wait_mode=False),

    # Tipo espera
    StartupCheck("blower",       "Blower",                 "Waiting for blower to reach operating flow (≥ 0.1 kg/s)",
                 "intake_flow",   lambda v: v >= 0.1,
                 wait_mode=True,  timeout_s=20.0),

    # Tipo binario
    StartupCheck("fuel_press",   "Fuel system pressure",   "Verifying fuel pressure in range (1.0–6.0 bar)",
                 "fuel_pressure", lambda v: 1.0 <= v <= 6.0,
                 wait_mode=False),

    StartupCheck("fuel_valve",   "Fuel valve position",    "Verifying fuel valve is open (≥ 10%)",
                 "valve_position",lambda v: v >= 10,
                 wait_mode=False),

    StartupCheck("ignition",     "Ignition system",        "Verifying ignition system is ready",
                 "intake_pressure",lambda v: v >= 0.9,
                 wait_mode=False),

    # Tipo espera
    StartupCheck("comb_chamber", "Combustion chamber",     "Waiting for combustion chamber pressure (≥ 1.0 bar)",
                 "comb_pressure", lambda v: v >= 1.0,
                 wait_mode=True,  timeout_s=30.0),

    # Tipo binario
    StartupCheck("temp_range",   "Temperature in range",   "Verifying temperatures within limits (< 850 °C)",
                 "comb_temp",     lambda v: v < 850,
                 wait_mode=False),

    StartupCheck("press_range",  "Pressure in range",      "Verifying pressures within limits (< 3.2 bar)",
                 "boost_pressure",lambda v: v < 3.2,
                 wait_mode=False),
]


# =====================================================
# Widget de check individual
# =====================================================
class CheckRow(QFrame):
    def __init__(self, check: StartupCheck, parent=None):
        super().__init__(parent)
        self.check = check
        self.setFixedHeight(40)
        self._apply_style("pending")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(10)

        self.icon_lbl = QLabel("○")
        self.icon_lbl.setFixedWidth(20)
        self.icon_lbl.setStyleSheet(
            "font-size: 14px; color: #64748B; border: none; background: transparent;"
        )
        layout.addWidget(self.icon_lbl)

        self.name_lbl = QLabel(check.label)
        self.name_lbl.setStyleSheet(
            "font-size: 11px; color: #475569; border: none; background: transparent;"
        )
        layout.addWidget(self.name_lbl, stretch=1)

        self.desc_lbl = QLabel(check.description)
        self.desc_lbl.setStyleSheet(
            "font-size: 9px; color: #64748B; border: none; background: transparent;"
        )
        layout.addWidget(self.desc_lbl, stretch=2)

        # Valor actual del sensor
        self.value_lbl = QLabel("—")
        self.value_lbl.setFixedWidth(70)
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value_lbl.setStyleSheet(
            "font-size: 10px; color: #475569; font-family: Consolas; "
            "border: none; background: transparent;"
        )
        layout.addWidget(self.value_lbl)

        # Badge de estado
        self.badge = QLabel("PENDING")
        self.badge.setFixedSize(70, 20)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_badge("pending")
        layout.addWidget(self.badge)

    def set_status(self, status: str, value: float = None, elapsed: float = None):
        self.check.status = status
        self._apply_style(status)
        self._apply_badge(status, elapsed)

        icons    = {"pending": "○", "checking": "◌", "waiting": "⏳", "ok": "✓", "fault": "✗"}
        colors   = {"pending": "#64748B", "checking": "#2563EB",
                    "waiting": "#f39c12", "ok": "#2ecc71", "fault": "#e74c3c"}
        name_col = {"pending": "#475569", "checking": "#1F2937",
                    "waiting": "#1F2937",  "ok": "#1F2937", "fault": "#1F2937"}

        self.icon_lbl.setText(icons.get(status, "○"))
        self.icon_lbl.setStyleSheet(
            f"font-size: 14px; color: {colors.get(status, '#64748B')}; "
            "border: none; background: transparent;"
        )
        self.name_lbl.setStyleSheet(
            f"font-size: 11px; color: {name_col.get(status, '#475569')}; "
            "border: none; background: transparent;"
        )

        if value is not None:
            self.value_lbl.setText(f"{value:.2f}")
            self.value_lbl.setStyleSheet(
                f"font-size: 10px; color: {colors.get(status, '#475569')}; "
                "font-family: Consolas; border: none; background: transparent;"
            )

    def _apply_style(self, status: str):
        styles = {
            "pending":  "background-color: #F8FAFC; border: 1px solid #CBD5E1;",
            "checking": "background-color: #EFF6FF; border: 1px solid #2563EB;",
            "waiting":  "background-color: #FFFBEB; border: 1px solid #f39c12;",
            "ok":       "background-color: #F0FDF4; border: 1px solid #BBF7D0;",
            "fault":    "background-color: #FEF2F2; border: 1px solid #FECACA;",
        }
        self.setStyleSheet(
            f"CheckRow {{ {styles.get(status, styles['pending'])} border-radius: 3px; }}"
        )

    def _apply_badge(self, status: str, elapsed: float = None):
        if status == "waiting" and elapsed is not None:
            txt = f"WAIT {elapsed:.0f}s"
        else:
            txt = {"pending": "PENDING", "checking": "CHECKING",
                   "waiting": "WAITING", "ok": "OK", "fault": "FAULT"}.get(status, "—")

        colors = {
            "pending":  ("#64748B", "#E2E8F0", "#CBD5E1"),
            "checking": ("#2563EB", "#DBEAFE", "#2563EB"),
            "waiting":  ("#f39c12", "#FFFBEB", "#f39c12"),
            "ok":       ("#1F2937", "#BBF7D0", "#2ecc71"),
            "fault":    ("#1F2937", "#FECACA", "#e74c3c"),
        }
        col, bg, border = colors.get(status, colors["pending"])
        self.badge.setText(txt)
        self.badge.setStyleSheet(f"""
            font-size: 8px; font-weight: bold;
            color: {col}; background-color: {bg};
            border: 1px solid {border}; border-radius: 2px;
        """)


# =====================================================
# Ventana de arranque
# =====================================================
class StartupWindow(QWidget):
    startup_confirmed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Turbojet HMI — Startup Sequence")
        self.setMinimumSize(1200, 740)
        self.setStyleSheet("background-color: #F1F5F9; color: #1F2937;")

        self._check_index      = 0
        self._all_ok           = False
        self._sequence_started = False
        self._latest_data: dict = {}
        self._waiting_for_data = False
        self._current_waiting  = False   # True si el check actual está en wait_mode

        self._check_timer = QTimer()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        from PyQt6.QtWidgets import QStackedWidget
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_welcome())
        self._stack.addWidget(self._build_main_body())
        root.addWidget(self._stack, stretch=1)

        root.addWidget(self._build_footer())

    # =====================================================
    # HEADER
    # =====================================================
    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setFixedHeight(52)
        header.setStyleSheet(
            "background-color: #E2E8F0; border-bottom: 1px solid #CBD5E1;"
        )

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel(
            "TURBOJET <span style='font-weight:normal; color:#475569;'>CONTROL SYSTEM</span>"
        )
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1F2937;")
        layout.addWidget(title)

        layout.addStretch()

        self.phase_lbl = QLabel("PRE-START")
        self.phase_lbl.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #475569; letter-spacing: 2px;"
        )
        layout.addWidget(self.phase_lbl)

        layout.addStretch()

        self.clock_label = QLabel("")
        self.clock_label.setStyleSheet("font-size: 11px; color: #475569;")
        layout.addWidget(self.clock_label)

        self._clock_timer = QTimer()
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        return header

    # =====================================================
    # BIENVENIDA
    # =====================================================
    def _build_welcome(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(24)

        title = QLabel("TURBOJET")
        title.setStyleSheet(
            "font-size: 48px; font-weight: bold; color: #1F2937; letter-spacing: 6px;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("CONTROL SYSTEM")
        subtitle.setStyleSheet("font-size: 18px; color: #475569; letter-spacing: 4px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        warn_frame = QFrame()
        warn_frame.setStyleSheet("""
            QFrame {
                background-color: #FFFBEB;
                border: 1px solid #FDE68A;
                border-radius: 4px;
            }
        """)
        warn_layout = QVBoxLayout(warn_frame)
        warn_layout.setContentsMargins(24, 16, 24, 16)
        warn_lbl = QLabel(
            "⚠  Before starting the ignition sequence, ensure all physical safety\n"
            "checks have been performed and the area is clear."
        )
        warn_lbl.setStyleSheet(
            "font-size: 11px; color: #92400E; border: none; background: transparent;"
        )
        warn_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warn_layout.addWidget(warn_lbl)
        warn_frame.setFixedWidth(600)
        layout.addWidget(warn_frame, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(16)

        self.begin_btn = QPushButton("▶  BEGIN STARTUP SEQUENCE")
        self.begin_btn.setFixedSize(320, 56)
        self.begin_btn.setStyleSheet("""
            QPushButton {
                background-color: #EFF6FF;
                color: #2563EB;
                font-size: 14px; font-weight: bold;
                border: 2px solid #2563EB;
                border-radius: 4px; letter-spacing: 1px;
            }
            QPushButton:hover { background-color: #2563EB; color: #FFFFFF; }
        """)
        self.begin_btn.clicked.connect(self._on_begin_startup)
        layout.addWidget(self.begin_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        emerg_btn = QPushButton("EMERGENCY SHUTDOWN")
        emerg_btn.setFixedSize(200, 36)
        emerg_btn.setStyleSheet("""
            QPushButton {
                background-color: #FEF2F2; color: #e74c3c;
                font-size: 10px; font-weight: bold;
                border: 1px solid #e74c3c; border-radius: 3px;
            }
            QPushButton:hover { background-color: #e74c3c; color: white; }
        """)
        emerg_btn.clicked.connect(self._on_emergency)
        layout.addWidget(emerg_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        return page

    # =====================================================
    # CUERPO PRINCIPAL
    # =====================================================
    def _build_main_body(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")

        body = QHBoxLayout(page)
        body.setContentsMargins(20, 16, 20, 16)
        body.setSpacing(16)

        body.addWidget(self._build_checklist(),    stretch=2)
        body.addWidget(self._build_flow_panel(),   stretch=3)
        body.addWidget(self._build_status_panel(), stretch=2)

        return page

    # =====================================================
    # CHECKLIST
    # =====================================================
    def _build_checklist(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        title = QLabel("PRE-START CHECKLIST")
        title.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #475569; letter-spacing: 2px;"
        )
        layout.addWidget(title)

        # Leyenda
        legend = QHBoxLayout()
        for symbol, label, color in [
            ("✓", "Immediate check", "#2ecc71"),
            ("⏳", "Wait until ready", "#f39c12"),
        ]:
            lbl = QLabel(f"{symbol} {label}")
            lbl.setStyleSheet(f"font-size: 8px; color: {color}; border: none; background: transparent;")
            legend.addWidget(lbl)
        legend.addStretch()
        layout.addLayout(legend)

        self._check_rows: dict[str, CheckRow] = {}
        for check in STARTUP_CHECKS:
            row = CheckRow(check)
            self._check_rows[check.key] = row
            layout.addWidget(row)

        layout.addStretch()
        return frame

    # =====================================================
    # DIAGRAMA DE FLUJO
    # =====================================================
    def _build_flow_panel(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(0)

        title = QLabel("IGNITION SEQUENCE")
        title.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #475569; letter-spacing: 2px;"
        )
        layout.addWidget(title)
        layout.addSpacing(10)

        flow_steps = [
            ("sensors",       "Verify sensors"),
            ("oil_temp",      "Heat oil / Wait temperature"),
            ("oil_pump",      "Start oil pump"),
            ("blower",        "Start blower"),
            ("fuel_press",    "Verify fuel system"),
            ("fuel_valve",    "Set fuel valve"),
            ("ignition",      "Arm ignition system"),
            ("comb_chamber",  "Verify combustion chamber"),
            ("temp_range",    "Check temperature range"),
            ("press_range",   "Check pressure range"),
            (None,            "ENGINE READY — Await operator"),
        ]

        self._flow_frames: dict[str, QFrame] = {}
        self._flow_labels: dict[str, QLabel] = {}

        for key, label in flow_steps:
            is_last = key is None

            step_frame = QFrame()
            step_frame.setFixedHeight(34)
            step_frame.setStyleSheet("""
                QFrame {
                    background-color: #E2E8F0;
                    border: 1px solid #CBD5E1;
                    border-radius: 3px;
                }
            """)

            step_layout = QHBoxLayout(step_frame)
            step_layout.setContentsMargins(12, 0, 12, 0)

            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"font-size: {'10px' if not is_last else '11px'}; "
                f"font-weight: {'bold' if is_last else 'normal'}; "
                f"color: {'#CBD5E1' if not is_last else '#64748B'}; "
                "border: none; background: transparent;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            step_layout.addWidget(lbl)

            layout.addWidget(step_frame)

            if key:
                self._flow_frames[key] = step_frame
                self._flow_labels[key] = lbl

            if not is_last:
                arrow = QLabel("▼")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setStyleSheet(
                    "font-size: 8px; color: #CBD5E1; background: transparent; border: none;"
                )
                arrow.setFixedHeight(10)
                layout.addWidget(arrow)

        layout.addStretch()
        return frame

    # =====================================================
    # PANEL DE ESTADO
    # =====================================================
    def _build_status_panel(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("STATUS")
        title.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #475569; letter-spacing: 2px;"
        )
        layout.addWidget(title)

        self.status_lbl = QLabel("VERIFYING...")
        self.status_lbl.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #2563EB;"
        )
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_lbl)

        self.counter_lbl = QLabel("0 / 10 checks passed")
        self.counter_lbl.setStyleSheet("font-size: 10px; color: #475569;")
        self.counter_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.counter_lbl)

        self.progress = QProgressBar()
        self.progress.setRange(0, len(STARTUP_CHECKS))
        self.progress.setValue(0)
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #E2E8F0; border: none; border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #2563EB; border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress)

        layout.addSpacing(6)

        self.current_check_lbl = QLabel("")
        self.current_check_lbl.setStyleSheet("font-size: 9px; color: #2563EB;")
        self.current_check_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_check_lbl.setWordWrap(True)
        layout.addWidget(self.current_check_lbl)

        # Timeout label — visible solo en wait_mode
        self.timeout_lbl = QLabel("")
        self.timeout_lbl.setStyleSheet("font-size: 9px; color: #f39c12;")
        self.timeout_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.timeout_lbl)

        layout.addStretch()

        self.start_btn = QPushButton("START ENGINE")
        self.start_btn.setEnabled(False)
        self.start_btn.setFixedHeight(50)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #BBF7D0; color: #3a6a3a;
                font-size: 14px; font-weight: bold;
                border: 1px solid #2a4a2a; border-radius: 4px;
            }
            QPushButton:enabled {
                background-color: #27ae60; color: white;
                border: 1px solid #2ecc71;
            }
            QPushButton:enabled:hover { background-color: #2ecc71; }
        """)
        self.start_btn.clicked.connect(self._on_start_confirmed)
        layout.addWidget(self.start_btn)

        layout.addSpacing(8)

        self.emergency_btn = QPushButton("EMERGENCY SHUTDOWN")
        self.emergency_btn.setFixedHeight(40)
        self.emergency_btn.setStyleSheet("""
            QPushButton {
                background-color: #c0392b; color: white;
                font-size: 11px; font-weight: bold;
                border: 1px solid #e74c3c; border-radius: 4px;
            }
            QPushButton:hover { background-color: #e74c3c; }
        """)
        self.emergency_btn.clicked.connect(self._on_emergency)
        layout.addWidget(self.emergency_btn)

        return frame

    # =====================================================
    # FOOTER
    # =====================================================
    def _build_footer(self) -> QWidget:
        footer = QFrame()
        footer.setFixedHeight(32)
        footer.setStyleSheet(
            "background-color: #E2E8F0; border-top: 1px solid #CBD5E1;"
        )

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 0, 20, 0)

        note = QLabel("★  START ENGINE unlocks automatically when all checks pass")
        note.setStyleSheet("font-size: 9px; color: #2563EB;")
        layout.addWidget(note)

        layout.addStretch()

        self.footer_status = QLabel("Press BEGIN STARTUP SEQUENCE to start")
        self.footer_status.setStyleSheet("font-size: 9px; color: #475569;")
        layout.addWidget(self.footer_status)

        return footer

    # =====================================================
    # LÓGICA — BEGIN STARTUP
    # =====================================================
    def _on_begin_startup(self):
        self._sequence_started = True
        self._stack.setCurrentIndex(1)
        self.phase_lbl.setText("▶  STARTUP SEQUENCE")
        self.phase_lbl.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #2563EB; letter-spacing: 2px;"
        )
        self.footer_status.setText("Startup sequence in progress...")
        self._waiting_for_data = True

    # =====================================================
    # RECIBIR DATOS DE SIMULACIÓN
    # =====================================================
    def update_data(self, data: dict):
        self._latest_data = data

        if not self._sequence_started:
            return

        if self._waiting_for_data:
            self._waiting_for_data = False
            self._run_current_check()
        elif self._current_waiting:
            # Estamos esperando que una variable alcance su valor
            self._retry_waiting_check()

    # =====================================================
    # EJECUTAR CHECK ACTUAL
    # =====================================================
    def _run_current_check(self):
        if self._check_index >= len(STARTUP_CHECKS):
            return

        check = STARTUP_CHECKS[self._check_index]
        check._elapsed_s = 0.0
        row = self._check_rows[check.key]

        if check.wait_mode:
            row.set_status("waiting", elapsed=0.0)
            self._highlight_flow_waiting(check.key)
            self.status_lbl.setText("WAITING...")
            self.status_lbl.setStyleSheet(
                "font-size: 16px; font-weight: bold; color: #f39c12;"
            )
        else:
            row.set_status("checking")
            self._highlight_flow_step(check.key)
            self.status_lbl.setText("CHECKING...")
            self.status_lbl.setStyleSheet(
                "font-size: 16px; font-weight: bold; color: #2563EB;"
            )

        self.current_check_lbl.setText(check.description)
        self.footer_status.setText(f"{'Waiting' if check.wait_mode else 'Checking'}: {check.label}...")

        value  = self._latest_data.get(check.sensor_key, None)
        passed = False
        if value is not None:
            try:
                passed = check.check_fn(value)
            except Exception:
                passed = False

        if passed:
            QTimer.singleShot(600, lambda: self._complete_check(check, value, True))
        elif check.wait_mode:
            # Seguir reintentando en cada ciclo de datos
            self._current_waiting = True
            self._update_timeout_label(check)
        else:
            # Falla inmediata para checks binarios
            QTimer.singleShot(600, lambda: self._complete_check(check, value, False))

    # =====================================================
    # REINTENTAR CHECK EN WAIT MODE
    # =====================================================
    def _retry_waiting_check(self):
        if self._check_index >= len(STARTUP_CHECKS):
            return

        check = STARTUP_CHECKS[self._check_index]
        check._elapsed_s += 0.1   # cada ciclo de datos es ~100ms

        value  = self._latest_data.get(check.sensor_key, None)
        passed = False
        if value is not None:
            try:
                passed = check.check_fn(value)
            except Exception:
                passed = False

        # Actualizar valor en la fila
        row = self._check_rows[check.key]
        row.set_status("waiting", value=value, elapsed=check._elapsed_s)
        self._update_timeout_label(check)

        if passed:
            self._current_waiting = False
            QTimer.singleShot(400, lambda: self._complete_check(check, value, True))
        elif check._elapsed_s >= check.timeout_s:
            # Timeout agotado → fault
            self._current_waiting = False
            QTimer.singleShot(400, lambda: self._complete_check(check, value, False))

    def _update_timeout_label(self, check: StartupCheck):
        remaining = max(0, check.timeout_s - check._elapsed_s)
        self.timeout_lbl.setText(
            f"⏳ Waiting... {check._elapsed_s:.0f}s / timeout: {check.timeout_s:.0f}s  "
            f"({remaining:.0f}s remaining)"
        )

    # =====================================================
    # COMPLETAR CHECK
    # =====================================================
    def _complete_check(self, check: StartupCheck, value, passed: bool):
        row = self._check_rows[check.key]

        if passed:
            row.set_status("ok", value)
            self._highlight_flow_ok(check.key)
            self.timeout_lbl.setText("")

            completed = sum(1 for c in STARTUP_CHECKS if c.status == "ok")
            self.progress.setValue(completed)
            self.counter_lbl.setText(f"{completed} / {len(STARTUP_CHECKS)} checks passed")

            self._check_index += 1

            if self._check_index >= len(STARTUP_CHECKS):
                QTimer.singleShot(400, self._on_all_checks_complete)
            else:
                self._waiting_for_data = True
        else:
            row.set_status("fault", value)
            self._on_check_fault(check, value)

    # =====================================================
    # COMPLETADO / FAULT
    # =====================================================
    def _on_all_checks_complete(self):
        self._all_ok = True
        self.timeout_lbl.setText("")
        self.status_lbl.setText("ALL CHECKS PASSED")
        self.status_lbl.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #2ecc71;"
        )
        self.current_check_lbl.setText("System ready — awaiting operator confirmation")
        self.footer_status.setText("Ready — press START ENGINE to proceed")
        self.progress.setStyleSheet("""
            QProgressBar { background-color: #E2E8F0; border: none; border-radius: 4px; }
            QProgressBar::chunk { background-color: #2ecc71; border-radius: 4px; }
        """)
        self._highlight_flow_complete()
        self.start_btn.setEnabled(True)

    def _on_check_fault(self, check: StartupCheck, value):
        self.status_lbl.setText("FAULT DETECTED")
        self.status_lbl.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #e74c3c;"
        )
        val_str = f"{value:.2f}" if value is not None else "—"
        self.current_check_lbl.setText(
            f"Failed: {check.label}\n"
            f"Value: {val_str}   "
            f"{'Timeout exceeded' if check.wait_mode else 'Out of range'}\n"
            "Resolve fault and restart the sequence."
        )
        self.timeout_lbl.setText("")
        self.footer_status.setText(f"FAULT: {check.label}")
        self.progress.setStyleSheet("""
            QProgressBar { background-color: #E2E8F0; border: none; border-radius: 4px; }
            QProgressBar::chunk { background-color: #e74c3c; border-radius: 4px; }
        """)

    # =====================================================
    # HIGHLIGHT DIAGRAMA
    # =====================================================
    def _highlight_flow_step(self, key: str):
        for k, frame in self._flow_frames.items():
            lbl   = self._flow_labels[k]
            status = next((c.status for c in STARTUP_CHECKS if c.key == k), "pending")
            if k == key:
                frame.setStyleSheet("QFrame { background-color: #EFF6FF; border: 1px solid #2563EB; border-radius: 3px; }")
                lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #2563EB; border: none; background: transparent;")
            elif status == "ok":
                frame.setStyleSheet("QFrame { background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 3px; }")
                lbl.setStyleSheet("font-size: 10px; color: #2ecc71; border: none; background: transparent;")
            else:
                frame.setStyleSheet("QFrame { background-color: #E2E8F0; border: 1px solid #CBD5E1; border-radius: 3px; }")
                lbl.setStyleSheet("font-size: 10px; color: #CBD5E1; border: none; background: transparent;")

    def _highlight_flow_waiting(self, key: str):
        if key in self._flow_frames:
            self._flow_frames[key].setStyleSheet(
                "QFrame { background-color: #FFFBEB; border: 1px solid #f39c12; border-radius: 3px; }"
            )
            self._flow_labels[key].setStyleSheet(
                "font-size: 10px; font-weight: bold; color: #f39c12; border: none; background: transparent;"
            )

    def _highlight_flow_ok(self, key: str):
        if key in self._flow_frames:
            self._flow_frames[key].setStyleSheet(
                "QFrame { background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 3px; }"
            )
            self._flow_labels[key].setStyleSheet(
                "font-size: 10px; color: #2ecc71; border: none; background: transparent;"
            )

    def _highlight_flow_complete(self):
        for k in self._flow_frames:
            self._flow_frames[k].setStyleSheet(
                "QFrame { background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 3px; }"
            )
            self._flow_labels[k].setStyleSheet(
                "font-size: 10px; color: #2ecc71; border: none; background: transparent;"
            )

    # =====================================================
    # CALLBACKS
    # =====================================================
    def _on_start_confirmed(self):
        if self._all_ok:
            self.startup_confirmed.emit()

    def _on_emergency(self):
        self._current_waiting = False
        self.emergency_btn.setEnabled(False)
        self.emergency_btn.setText("EMERGENCY ACTIVATED")
        self.status_lbl.setText("EMERGENCY SHUTDOWN")
        self.status_lbl.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #e74c3c;"
        )
        self.footer_status.setText("Emergency activated — restart required")

    def _update_clock(self):
        self.clock_label.setText(datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))