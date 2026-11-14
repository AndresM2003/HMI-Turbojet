# ui/control_panel.py

from PyQt6.QtWidgets import (
    QFrame, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QWidget, QMessageBox
)
from PyQt6.QtCore import pyqtSignal, Qt


class ControlPanel(QFrame):
    stop_requested      = pyqtSignal()
    emergency_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
            ControlPanel {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        title = QLabel("CONTROL")
        title.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #475569; letter-spacing: 2px;"
        )
        layout.addWidget(title)

        # --- STOP ---
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 10px;
                border-radius: 3px;
                border: none;
            }
            QPushButton:hover    { background-color: #f39c12; }
            QPushButton:disabled { background-color: #FEF3C7; color: #92400E; }
        """)
        self.stop_btn.clicked.connect(self._confirm_stop)
        layout.addWidget(self.stop_btn)

        # --- EMERGENCY ---
        self.emergency_btn = QPushButton("EMERGENCY SHUTDOWN")
        self.emergency_btn.setStyleSheet("""
            QPushButton {
                background-color: #c0392b;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 12px;
                border-radius: 3px;
                border: none;
            }
            QPushButton:hover    { background-color: #e74c3c; }
            QPushButton:disabled { background-color: #FEE2E2; color: #991B1B; }
        """)
        self.emergency_btn.clicked.connect(self._emergency)
        layout.addWidget(self.emergency_btn)

        # --- Sliders ---
        layout.addSpacing(4)
        layout.addWidget(self._build_slider("THROTTLE",   "throttle_slider",   0, 100, 0, "%"))
        layout.addWidget(self._build_slider("FUEL VALVE", "fuel_valve_slider", 0, 100, 0, "%"))

        layout.addStretch()
        self.setLayout(layout)

        self.set_engine_state("RUNNING")

    def _build_slider(self, label_text, attr_name, min_val, max_val, default, unit):
        container = QWidget()
        container.setStyleSheet("background: transparent; border: none;")
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)

        header = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setStyleSheet("font-size: 11px; color: #475569;")
        val_lbl = QLabel(f"{default}{unit}")
        val_lbl.setStyleSheet("font-size: 11px; color: #1F2937; font-family: Consolas;")
        header.addWidget(lbl)
        header.addStretch()
        header.addWidget(val_lbl)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(min_val)
        slider.setMaximum(max_val)
        slider.setValue(default)
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px; background: #CBD5E1; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #2563EB; width: 14px; height: 14px;
                margin: -5px 0; border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #2563EB; border-radius: 2px;
            }
        """)
        slider.valueChanged.connect(lambda v, l=val_lbl: l.setText(f"{v}{unit}"))

        setattr(self, attr_name, slider)
        v.addLayout(header)
        v.addWidget(slider)
        return container

    def _confirm_stop(self):
        reply = QMessageBox.question(
            self, "Confirm STOP", "Stop turbojet normally?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.stop_requested.emit()

    def _emergency(self):
        self.emergency_btn.setText("EMERGENCY ACTIVATED")
        self.emergency_btn.setEnabled(False)
        self.emergency_requested.emit()

    def set_engine_state(self, state: str):
        if state == "RUNNING":
            self.stop_btn.setEnabled(True)
        elif state in ("STOPPING", "EMERGENCY"):
            self.stop_btn.setEnabled(False)