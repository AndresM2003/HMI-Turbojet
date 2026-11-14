# ui/commands_panel.py

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QGridLayout, QLabel, QPushButton
)
from PyQt6.QtCore import pyqtSignal


_BTN_NORMAL = """
    QPushButton {
        background-color: #E2E8F0;
        color: #334155;
        font-size: 11px;
        font-weight: bold;
        padding: 10px 6px;
        border: 1px solid #94A3B8;
        border-radius: 3px;
    }
    QPushButton:hover {
        background-color: #2563EB;
        color: #FFFFFF;
        border: 1px solid #2563EB;
    }
    QPushButton:disabled {
        background-color: #F1F5F9;
        color: #94A3B8;
        border: 1px solid #CBD5E1;
    }
"""


class CommandsPanel(QFrame):
    ignite_requested    = pyqtSignal()
    cool_down_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
            CommandsPanel {
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

        title = QLabel("COMMANDS")
        title.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #475569; letter-spacing: 2px;"
        )
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(8)

        self.ignite_btn       = self._make_btn("IGNITE")
        self.cool_down_btn    = self._make_btn("COOL DOWN")
        self.reset_alarms_btn = self._make_btn("RESET ALARMS")

        self.ignite_btn.clicked.connect(self.ignite_requested.emit)
        self.cool_down_btn.clicked.connect(self.cool_down_requested.emit)

        grid.addWidget(self.ignite_btn,       0, 0)
        grid.addWidget(self.cool_down_btn,    0, 1)
        grid.addWidget(self.reset_alarms_btn, 1, 0, 1, 2)

        layout.addLayout(grid)
        layout.addStretch()
        self.setLayout(layout)

        self.set_engine_state("RUNNING")

    def _make_btn(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setStyleSheet(_BTN_NORMAL)
        return btn

    def set_engine_state(self, state: str):
        if state == "RUNNING":
            self.ignite_btn.setEnabled(False)
            self.cool_down_btn.setEnabled(True)
        elif state == "STOPPING":
            self.ignite_btn.setEnabled(False)
            self.cool_down_btn.setEnabled(False)
        elif state == "EMERGENCY":
            self.ignite_btn.setEnabled(False)
            self.cool_down_btn.setEnabled(False)

        self.reset_alarms_btn.setEnabled(True)