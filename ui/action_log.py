import html
from datetime import datetime

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QTextEdit

from ui.command_center import CommandCenter

_COLORS = {"info": "#3E4A51", "ok": "#1E7B45", "warn": "#8A5A00", "error": "#B3261E"}


class ActionLog(QTextEdit):
    """Historial de acciones, estilo monitor serial: una línea por evento con su hora."""

    def __init__(self, commands: CommandCenter):
        super().__init__()
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 9))
        self.setStyleSheet("QTextEdit { background: #FFFFFF; border: 1px solid #B3BBC1; }")
        self.document().setMaximumBlockCount(500)
        commands.log_event.connect(self.add_line)

    def add_line(self, level: str, text: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        color = _COLORS.get(level, _COLORS["info"])
        self.append(
            f'<span style="color:#6B777E">{stamp}</span>&nbsp;&nbsp;'
            f'<span style="color:{color}">{html.escape(text).replace(" ", "&nbsp;")}</span>'
        )
