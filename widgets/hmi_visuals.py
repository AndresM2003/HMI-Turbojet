import math

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class RPMGauge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rpm: float | None = None
        self.setMinimumSize(180, 170)

    def set_value(self, value: float | None):
        self._rpm = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        radius = max(20, min(self.width(), self.height()) / 2 - 18)
        painter.setPen(QPen(QColor("#465158"), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawArc(
            int(-radius), int(-radius), int(2 * radius), int(2 * radius),
            225 * 16, -270 * 16,
        )

        if self._rpm is not None:
            angle = 225 - min(max(self._rpm, 0) / 40000, 1) * 270
            radians = math.radians(angle)
            end_x = math.cos(radians) * (radius - 10)
            end_y = -math.sin(radians) * (radius - 10)
            painter.setPen(QPen(QColor("#70A9CF"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(0, 0, int(end_x), int(end_y))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#AEB8BD"))
            painter.drawEllipse(-5, -5, 10, 10)

        painter.setPen(QColor("#E2E6E8"))
        painter.setFont(QFont("Segoe UI", 19, QFont.Weight.DemiBold))
        text = "—" if self._rpm is None else f"{self._rpm:,.0f}"
        painter.drawText(-self.width() // 2, 20, self.width(), 30, Qt.AlignmentFlag.AlignCenter, text)
        painter.setPen(QColor("#9CA6AB"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(-self.width() // 2, 56, self.width(), 18, Qt.AlignmentFlag.AlignCenter, "RPM")
        painter.setPen(QColor("#849096"))
        painter.setFont(QFont("Segoe UI", 8))
        for value in (0, 10, 20, 30, 40):
            angle = math.radians(225 - value * 270 / 4)
            x = math.cos(angle) * (radius - 25)
            y = -math.sin(angle) * (radius - 25)
            painter.drawText(int(x - 12), int(y - 6), 24, 12, Qt.AlignmentFlag.AlignCenter, str(value))


class ProcessMimic(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sensors: dict[str, float | None] = {}
        self.setMinimumHeight(230)

    def set_sensors(self, sensors: dict):
        self._sensors = dict(sensors)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont("Segoe UI", 8))

        width = self.width()
        height = self.height()
        line_color = QColor("#77838A")
        box_color = QColor("#2D3439")
        text_color = QColor("#D2D8DB")
        sensor_color = QColor("#70A9CF")
        left = 25
        top = int(height * 0.34)
        box_h = max(42, int(height * 0.28))
        gap = max(8, int(width * 0.018))
        box_width = (width - 2 * left - 3 * gap) // 4
        names = ("COMPRESSOR", "COMBUSTION\nCHAMBER", "TURBINE", "EXHAUST")
        temperature_sensors = (
            ("T1", "t1_c", 0, 0),
            ("T2", "t2_c", 1, -32),
            ("T3", "t3_c", 1, 32),
            ("T4", "t4_c", 2, 0),
        )
        painter.setPen(QPen(line_color, 2))
        painter.drawLine(left - 18, top + box_h // 2, left, top + box_h // 2)
        painter.setPen(text_color)
        painter.drawText(2, top + box_h // 2 - 8, 24, 16, Qt.AlignmentFlag.AlignCenter, "AIR")

        for index, name in enumerate(names):
            x = left + index * (box_width + gap)
            rect = (x, top, box_width, box_h)
            painter.setPen(QPen(line_color, 1))
            painter.setBrush(box_color)
            painter.drawRect(*rect)
            painter.setPen(text_color)
            painter.drawText(
                x + 3, top + 5, box_width - 6, box_h - 10,
                Qt.AlignmentFlag.AlignCenter, name,
            )
            if index < len(names) - 1:
                painter.setPen(QPen(line_color, 2))
                painter.drawLine(x + box_width, top + box_h // 2, x + box_width + gap, top + box_h // 2)

        for tag, key, box_index, offset in temperature_sensors:
            x = left + box_index * (box_width + gap)
            center_x = x + box_width // 2 + offset
            circle_y = top - 25
            value = self._sensors.get(key)
            value_text = "—" if value is None else f"{value:.0f}°C"
            painter.setPen(QPen(sensor_color, 2))
            painter.setBrush(box_color)
            painter.drawEllipse(center_x - 15, circle_y - 15, 30, 30)
            painter.setPen(text_color)
            painter.drawText(
                center_x - 14, circle_y - 7, 28, 14,
                Qt.AlignmentFlag.AlignCenter, tag,
            )
            painter.setPen(sensor_color)
            painter.drawText(
                center_x - 30, circle_y - 32, 60, 12,
                Qt.AlignmentFlag.AlignCenter, f"{tag} {value_text}",
            )

        lower_y = top + box_h + 38
        component_width = max(72, min(110, box_width))
        component_gap = max(12, int(width * 0.04))
        components = (
            ("OIL", "PUMP", "T5", "t5_c"),
            ("FUEL", "TANK", "G1", "mq6_1_ppm"),
            ("GAS", "SENSOR", "G2", "mq6_2_ppm"),
            ("SHAFT", "SENSOR", "RPM", "rpm"),
        )
        total_w = len(components) * component_width + (len(components) - 1) * component_gap
        start_x = max(10, (width - total_w) // 2)
        for index, (first, second, tag, key) in enumerate(components):
            x = start_x + index * (component_width + component_gap)
            painter.setPen(QPen(line_color, 1))
            painter.setBrush(box_color)
            painter.drawRect(x, lower_y, component_width, 36)
            painter.setPen(text_color)
            painter.drawText(x + 2, lower_y + 3, component_width - 4, 30, Qt.AlignmentFlag.AlignCenter, f"{first}\n{second}")
            value = self._sensors.get(key)
            unit = "°C" if key.endswith("_c") else "ppm" if "mq6" in key else "RPM"
            text = "—" if value is None else f"{value:.0f} {unit}"
            painter.setPen(sensor_color)
            painter.drawText(x - 10, lower_y + 42, component_width + 20, 14, Qt.AlignmentFlag.AlignCenter, f"{tag}  {text}")
