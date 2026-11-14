# widgets/alerts_panel.py

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QScrollArea
)
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtCore import Qt, QTimer
from dataclasses import dataclass


@dataclass
class Alert:
    name:    str
    message: str
    level:   str        # "warning" | "critical"
    active:  bool = False
    latched: bool = False


class AlertItem(QWidget):
    def __init__(self, alert: Alert, parent=None):
        super().__init__(parent)
        self.alert = alert
        self.setFixedHeight(45)
        self.blink_state = True

        self.timer = QTimer()
        self.timer.timeout.connect(self._toggle_blink)
        self.timer.start(500)

    def _toggle_blink(self):
        if self.alert.level == "critical" and self.alert.latched:
            self.blink_state = not self.blink_state
            self.update()
        else:
            self.blink_state = True

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        if self.alert.latched and self.alert.level == "critical":
            bg = QColor(254, 226, 226)
        elif self.alert.latched:
            bg = QColor(255, 251, 235)
        else:
            bg = QColor(248, 250, 252)
        painter.fillRect(rect, bg)
        painter.setPen(QPen(QColor(203, 213, 225), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        color = QColor(220, 38, 38) if self.alert.level == "critical" else QColor(217, 119, 6)

        painter.setPen(Qt.PenStyle.NoPen)
        if self.alert.latched:
            if self.alert.level == "critical" and not self.blink_state:
                painter.setBrush(QColor(254, 202, 202))
            else:
                painter.setBrush(color)
        else:
            painter.setBrush(QColor(148, 163, 184))
        painter.drawEllipse(10, 12, 20, 20)

        painter.setPen(QColor(31, 41, 55))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(45, 28, self.alert.message)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color if self.alert.latched else QColor(148, 163, 184))
        painter.drawEllipse(self.width() - 25, 15, 15, 15)


class AlertsPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            AlertsPanel {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)

        # Catálogo completo de alertas posibles — ninguna visible al inicio
        self._catalog: dict[str, Alert] = {}
        # Solo las que están actualmente latched y visibles
        self._visible: dict[str, AlertItem] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 10, 8, 10)
        outer.setSpacing(6)

        self.title = QLabel("ALERTS (0)")
        self.title.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #475569; letter-spacing: 2px;"
        )
        outer.addWidget(self.title)

        # Área scrollable para las alertas activas
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #F1F5F9; width: 5px; border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: #CBD5E1; border-radius: 2px;
            }
        """)

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(4)
        self._content_layout.addStretch()

        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll, stretch=1)

        # Placeholder cuando no hay alertas
        self._empty_lbl = QLabel("No active alerts")
        self._empty_lbl.setStyleSheet(
            "font-size: 10px; color: #64748B; border: none; background: transparent;"
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._content_layout.insertWidget(0, self._empty_lbl)

    # =====================================================
    # API pública
    # =====================================================
    def register_alert(self, alert: Alert):
        """Registra una alerta en el catálogo sin mostrarla."""
        self._catalog[alert.name] = alert

    def update_alert(self, name: str, condition_active: bool):
        if name not in self._catalog:
            return

        alert = self._catalog[name]

        if condition_active:
            alert.active  = True
            alert.latched = True
            self._show_alert(name)
        else:
            alert.active = False
            # Mantiene visible si está latched (requiere reset manual)

        self._update_counter()

    def reset_alarms(self):
        """Oculta las alertas que ya no están activas."""
        to_remove = [
            name for name, alert in self._catalog.items()
            if alert.latched and not alert.active
        ]
        for name in to_remove:
            alert = self._catalog[name]
            alert.latched = False
            self._hide_alert(name)

        self._update_counter()

    # =====================================================
    # Mostrar / ocultar items
    # =====================================================
    def _show_alert(self, name: str):
        if name in self._visible:
            self._visible[name].update()
            return

        alert = self._catalog[name]
        item  = AlertItem(alert)
        self._visible[name] = item

        # Insertar antes del stretch (último elemento)
        count = self._content_layout.count()
        self._content_layout.insertWidget(count - 1, item)

        # Ocultar placeholder
        self._empty_lbl.setVisible(False)

    def _hide_alert(self, name: str):
        if name not in self._visible:
            return

        item = self._visible.pop(name)
        self._content_layout.removeWidget(item)
        item.deleteLater()

        if not self._visible:
            self._empty_lbl.setVisible(True)

    def _update_counter(self):
        count = sum(1 for a in self._catalog.values() if a.latched)
        self.title.setText(f"ALERTS ({count})")