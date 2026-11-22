from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from ui.command_center import CommandCenter

ALL_GROUPS = ("control_mode", "oil_pump", "fuel_solenoid", "fuel_servo", "spark_pulse", "stop", "emergency_stop")
FUEL_GROUPS = ("fuel_solenoid", "fuel_servo", "spark_pulse")

_GREEN, _BLUE, _AMBER, _RED, _GRAY = ("#2E8B57", "#2A7FB8", "#D98E04", "#C0392B", "#6B7A85")
_HOVER = {_GREEN: "#3AA168", _BLUE: "#3A92CC", _AMBER: "#EAA11A", _RED: "#D64A3B", _GRAY: "#7D8C97"}
_STATE_COLORS = {"ACK": "#1E7B45", "SENDING": "#8A5A00", "NO_ACK": "#B3261E",
                 "REJECTED": "#B3261E", "FAILED": "#B3261E"}


def _style(color: str) -> str:
    return (f"QPushButton {{ background: {color}; color: #FFFFFF; border: 1px solid {color}; "
            f"font-weight: bold; font-size: 10px; padding: 6px 10px; }}"
            f"QPushButton:hover {{ background: {_HOVER[color]}; }}"
            "QPushButton:disabled { background: #E3E7EA; color: #9AA4AB; border-color: #CDD3D7; }")


class ControlPanel(QFrame):
    """Franja de control.

    Por defecto el sistema trabaja en AUTOMÁTICO y los controles manuales están desactivados.
    El botón MANUAL CONTROL los habilita (bomba, solenoide, servo, bujía); el mismo botón
    devuelve el control al automático. STOP y EMERGENCY STOP siempre están disponibles.
    """

    stop_requested = pyqtSignal()

    def __init__(self, commands: CommandCenter, groups=ALL_GROUPS):
        super().__init__()
        self.commands = commands
        self.setObjectName("card")
        self._buttons: list[tuple[QPushButton, str, callable]] = []
        self._state_labels: dict[str, QLabel] = {}
        self._lock_reason: str | None = None
        self._was_manual = False
        self.servo_slider: QSlider | None = None
        self.mode_button: QPushButton | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 6, 12, 8)
        outer.setSpacing(4)
        head = QHBoxLayout()
        title = QLabel("CONTROL")
        title.setStyleSheet("font-size: 9px; font-weight: bold; color: #55626A; letter-spacing: 1px;")
        hint = QLabel("AUTO: the controller manages the outputs · MANUAL: you operate them · "
                      "STOP and EMERGENCY STOP are always available · commands need the ESP32 ACK")
        hint.setStyleSheet("font-size: 8px; color: #6B777E;")
        head.addWidget(title)
        head.addSpacing(10)
        head.addWidget(hint)
        head.addStretch()
        outer.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(18)
        builders = {
            "control_mode": self._mode_group,
            "oil_pump": lambda: self._choice_group("OIL PUMP", "oil_pump", (("ON", "on", _GREEN), ("OFF", "off", _GRAY))),
            "fuel_solenoid": lambda: self._choice_group("FUEL SOLENOID", "fuel_solenoid", (("OPEN", "open", _GREEN), ("CLOSE", "close", _GRAY))),
            "fuel_servo": self._servo_group,
            "spark_pulse": lambda: self._momentary_group("SPARK", "spark_pulse", "PULSE", _AMBER),
            "stop": lambda: self._momentary_group("ENGINE", "stop", "STOP", _AMBER),
            "emergency_stop": lambda: self._momentary_group("EMERGENCY", "emergency_stop", "EMERGENCY STOP", _RED),
        }
        for name in groups:
            row.addWidget(builders[name]())
        row.addStretch()
        outer.addLayout(row)
        self.groups = tuple(groups)

        self.commands.changed.connect(self.refresh)
        self.refresh()

    # ---------- construcción de grupos ----------
    def _group(self, title: str, command: str) -> tuple[QWidget, QHBoxLayout]:
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        label = QLabel(title)
        label.setStyleSheet("font-size: 8px; font-weight: bold; color: #55626A;")
        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        state = QLabel("—")
        state.setStyleSheet("font-size: 9px; color: #7B868D;")
        self._state_labels[command] = state
        layout.addWidget(label)
        layout.addLayout(buttons)
        layout.addWidget(state)
        return box, buttons

    def _add_button(self, layout, text, color, command, getter):
        button = QPushButton(text)
        button.setStyleSheet(_style(color))
        button.clicked.connect(lambda checked=False, c=command, g=getter: self._on_click(c, g))
        layout.addWidget(button)
        self._buttons.append((button, command, getter))
        return button

    def _mode_group(self):
        box, buttons = self._group("CONTROL MODE", "control_mode")
        self.mode_button = self._add_button(
            buttons, "MANUAL CONTROL", _BLUE, "control_mode",
            lambda: "auto" if self.commands.manual_mode else "manual")
        self.mode_button.setMinimumWidth(130)
        return box

    def _choice_group(self, title, command, options):
        box, buttons = self._group(title, command)
        for text, value, color in options:
            self._add_button(buttons, text, color, command, lambda v=value: v)
        return box

    def _momentary_group(self, title, command, text, color):
        box, buttons = self._group(title, command)
        button = self._add_button(buttons, text, color, command, lambda: None)
        if command == "emergency_stop":
            button.setMinimumHeight(34)
            button.setMinimumWidth(130)
        return box

    def _servo_group(self):
        box, buttons = self._group("FUEL SERVO", "fuel_servo")
        self.servo_slider = QSlider(Qt.Orientation.Horizontal)
        self.servo_slider.setRange(0, 100)
        self.servo_slider.setFixedWidth(110)
        self.servo_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: #C9CFD3; }"
            "QSlider::sub-page:horizontal { background: #2A7FB8; }"
            "QSlider::handle:horizontal { background: #2A7FB8; width: 12px; margin: -5px 0; border-radius: 6px; }"
            "QSlider::sub-page:horizontal:disabled { background: #D5DADD; }"
            "QSlider::handle:horizontal:disabled { background: #B8C0C5; }")
        self.servo_value = QLabel("0 %")
        self.servo_value.setFixedWidth(38)
        self.servo_value.setStyleSheet("font-size: 10px; font-weight: bold;")
        self.servo_slider.valueChanged.connect(lambda v: (self.servo_value.setText(f"{v} %"), self.refresh()))
        buttons.addWidget(self.servo_slider)
        buttons.addWidget(self.servo_value)
        set_button = self._add_button(buttons, "SET", _BLUE, "fuel_servo", lambda: self.servo_slider.value())
        set_button.setFixedWidth(48)
        return box

    # ---------- comportamiento ----------
    def set_locked(self, reason: str | None):
        """Bloquea los comandos de combustible y bujía (p. ej. hasta autorizar la ignición)."""
        self._lock_reason = reason
        self.refresh()

    def _on_click(self, command, getter):
        value = getter()
        text = self.commands.confirmation_text(command, value)
        if text and QMessageBox.question(self, "Confirm command", text) != QMessageBox.StandardButton.Yes:
            return
        ok, reason = self.commands.send(command, value)
        if not ok:
            QMessageBox.warning(self, "Command not sent", reason)
            return
        if command == "stop":
            self.stop_requested.emit()

    def _state_text(self, command: str):
        state = self.commands.states.get(command)
        if command == "control_mode":
            if state is None or state.status in ("IDLE", "ACK"):
                mode = self.commands.confirmed_mode.upper()
                return (f"{mode} ✓" if state is not None else f"{mode} (default)"), \
                       ("#8A5A00" if self.commands.manual_mode else "#1E7B45"), ""
        if state is None or state.status == "IDLE":
            return "—", "#7B868D", ""
        if state.status == "ACK":
            shown = f"{state.value:g} %" if isinstance(state.value, (int, float)) else (
                "sent" if state.value is None else str(state.value).upper())
            return f"{shown} ✓", _STATE_COLORS["ACK"], state.message
        text = {"SENDING": "SENDING…", "NO_ACK": "NO ACK", "REJECTED": "REJECTED",
                "FAILED": "SEND FAILED"}[state.status]
        return text, _STATE_COLORS[state.status], state.message

    def refresh(self):
        manual = self.commands.manual_mode
        self.setStyleSheet(f"QFrame#card {{ border-top: 3px solid {'#D98E04' if manual else '#2E8B57'}; }}")
        for button, command, getter in self._buttons:
            allowed, reason = self.commands.check(command, getter())
            if allowed and self._lock_reason and command in FUEL_GROUPS:
                allowed, reason = False, self._lock_reason
            button.setEnabled(allowed)
            button.setToolTip("" if allowed else reason)
        if self.mode_button is not None:
            self.mode_button.setText("RETURN TO AUTO" if manual else "MANUAL CONTROL")
            self.mode_button.setStyleSheet(_style(_AMBER if manual else _BLUE))
        if self.servo_slider is not None:
            usable = manual and self.commands.connected and not self._lock_reason
            self.servo_slider.setEnabled(bool(usable))
            if self._was_manual and not manual:  # vuelve al automático: el servo deja de ser manual
                self.servo_slider.blockSignals(True)
                self.servo_slider.setValue(0)
                self.servo_slider.blockSignals(False)
                self.servo_value.setText("0 %")
        self._was_manual = manual
        for command, label in self._state_labels.items():
            text, color, tip = self._state_text(command)
            label.setText(text)
            label.setToolTip(tip)
            label.setStyleSheet(f"font-size: 9px; font-weight: bold; color: {color};")
