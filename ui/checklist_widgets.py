from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.checklist import CheckStatus
from ui.theme import STATE_COLORS, accent_for_title


def card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    frame.setStyleSheet(f"QFrame#card {{ border-top: 3px solid {accent_for_title(title)}; }}")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(6)
    heading = QLabel(title.upper())
    heading.setStyleSheet("font-size: 9px; font-weight: bold; color: #55626A; letter-spacing: 1px;")
    layout.addWidget(heading)
    return frame, layout


class CheckRow(QFrame):
    confirm_clicked = pyqtSignal(str)

    def __init__(self, spec):
        super().__init__()
        self.key = spec.key
        self.setFixedHeight(46)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 2, 8, 2)
        row.setSpacing(8)
        self.icon = QLabel("○")
        self.icon.setFixedWidth(18)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.name = QLabel(spec.label)
        self.name.setStyleSheet("font-size: 11px;")
        self.detail = QLabel(spec.description)
        self.detail.setStyleSheet("font-size: 9px; color: #5F6B73;")
        text.addWidget(self.name)
        text.addWidget(self.detail)
        self.confirm = QPushButton("CONFIRM")
        self.confirm.setFixedSize(66, 22)
        self.confirm.setStyleSheet("font-size: 8px; padding: 0; color: #1F6FA8; border-color: #1F6FA8;")
        self.confirm.clicked.connect(lambda: self.confirm_clicked.emit(self.key))
        self.badge = QLabel()
        self.badge.setFixedSize(74, 20)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.icon)
        row.addLayout(text, 1)
        row.addWidget(self.confirm)
        row.addWidget(self.badge)
        self.set_pending()

    def _paint(self, state: str, badge: str, icon: str, detail: str):
        color = STATE_COLORS[state]
        self.setStyleSheet(f"CheckRow {{ background: #FFFFFF; border: 1px solid {color if state != 'PENDING' else '#B8C0C5'}; }}")
        self.icon.setText(icon)
        self.icon.setStyleSheet(f"font-size: 14px; color: {color};")
        self.badge.setText(badge)
        self.badge.setStyleSheet(f"font-size: 8px; font-weight: bold; color: #FFFFFF; background: {color};")
        self.detail.setText(detail)
        self.confirm.setVisible(state == "MANUAL")

    def set_pending(self):
        self._paint("PENDING", "PENDING", "○", self.detail.text())

    def set_status(self, status: CheckStatus):
        icon = {"OK": "✓", "WAIT": "…", "FAULT": "✗", "MANUAL": "?"}[status.state]
        badge = "OK (MANUAL)" if status.manual else status.state
        self._paint(status.state, badge, icon, status.detail)


class ChecklistPanel(QFrame):
    confirm_requested = pyqtSignal(str)

    def __init__(self, title: str, specs):
        super().__init__()
        self.setObjectName("card")
        self.setStyleSheet(f"QFrame#card {{ border-top: 3px solid {accent_for_title(title)}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        heading = QLabel(title.upper())
        heading.setStyleSheet("font-size: 9px; font-weight: bold; color: #55626A; letter-spacing: 1px;")
        layout.addWidget(heading)
        self.rows = {spec.key: CheckRow(spec) for spec in specs}
        for row in self.rows.values():
            row.confirm_clicked.connect(self.confirm_requested)
            layout.addWidget(row)
        layout.addStretch()

    def set_statuses(self, statuses: dict[str, CheckStatus]):
        for key, status in statuses.items():
            if key in self.rows:
                self.rows[key].set_status(status)

    def set_pending(self):
        for row in self.rows.values():
            row.set_pending()


class FlowPanel(QFrame):
    """Diagrama de secuencia: una caja por paso, coloreada según el estado del chequeo."""

    def __init__(self, title: str, steps: list[tuple[str | None, str]]):
        super().__init__()
        self.setObjectName("card")
        self.setStyleSheet(f"QFrame#card {{ border-top: 3px solid {accent_for_title(title)}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)
        heading = QLabel(title.upper())
        heading.setStyleSheet("font-size: 9px; font-weight: bold; color: #55626A; letter-spacing: 1px;")
        layout.addWidget(heading)
        layout.addSpacing(8)
        self.boxes: dict[str, QLabel] = {}
        for index, (key, text) in enumerate(steps):
            box = QLabel(text)
            box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.setFixedHeight(30)
            layout.addWidget(box)
            if key:
                self.boxes[key] = box
            self._style(box, "PENDING")
            if index < len(steps) - 1:
                arrow = QLabel("▼")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setFixedHeight(14)
                arrow.setStyleSheet("font-size: 8px; color: #AEB7BC;")
                layout.addWidget(arrow)
        layout.addStretch()

    @staticmethod
    def _style(box: QLabel, state: str):
        color = STATE_COLORS[state]
        box.setStyleSheet(
            f"background: #FFFFFF; border: 1px solid {color if state != 'PENDING' else '#B8C0C5'}; "
            f"color: {color if state != 'PENDING' else '#5F6B73'}; font-size: 10px;"
        )

    def set_states(self, states: dict[str, str]):
        for key, state in states.items():
            if key in self.boxes:
                self._style(self.boxes[key], state)


LIVE_FIELDS = (
    ("t1_c", "T1 compressor out", "°C", 1), ("t2_c", "T2 chamber in", "°C", 1),
    ("t3_c", "T3 chamber out", "°C", 1), ("t4_c", "T4 turbine in", "°C", 1),
    ("t5_c", "T5 oil", "°C", 1), ("rpm", "RPM", "rpm", 0), ("maf_g_s", "MAF", "g/s", 2),
    ("mq6_1_ppm", "GAS 1", "ppm", 1), ("mq6_2_ppm", "GAS 2", "ppm", 1),
)


class LiveValues(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.values: dict[str, QLabel] = {}
        for key, name, unit, _ in LIVE_FIELDS:
            row = QHBoxLayout()
            label = QLabel(name)
            label.setStyleSheet("font-size: 10px; color: #55626A;")
            value = QLabel("—")
            value.setStyleSheet("font-size: 11px; font-weight: bold;")
            value.setMinimumWidth(80)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(label, 1)
            row.addWidget(value)
            unit_label = QLabel(unit)
            unit_label.setFixedWidth(34)
            row.addWidget(unit_label)
            layout.addLayout(row)
            self.values[key] = value

    def set_sensors(self, sensors: dict | None):
        for key, _, _, decimals in LIVE_FIELDS:
            value = None if sensors is None else sensors.get(key)
            self.values[key].setText("—" if value is None else f"{value:,.{decimals}f}")
