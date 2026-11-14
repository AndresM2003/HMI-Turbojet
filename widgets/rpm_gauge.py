# widgets/rpm_gauge.py

import math
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtCore import Qt, QTimer, QRectF


class RPMGauge(QWidget):
    def __init__(
        self,
        max_rpm=40000,
        green_limit=34000,
        yellow_limit=37000,
    ):
        super().__init__()

        self.max_rpm = max_rpm
        self.green_limit = green_limit
        self.yellow_limit = yellow_limit

        self.current_value = 0
        self.target_value = 0
        self.peak_value = 0

        self.setMinimumSize(450, 450)

        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

    # =====================================================
    # API
    # =====================================================
    def set_value(self, value):
        value = max(0, min(value, self.max_rpm))
        self.target_value = value

        if value > self.peak_value:
            self.peak_value = value

    def reset_peak(self):
        self.peak_value = 0

    # =====================================================
    # Animación suave
    # =====================================================
    def animate(self):
        diff = self.target_value - self.current_value
        self.current_value += diff * 0.08
        self.update()

    # =====================================================
    # Paint principal
    # =====================================================
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        size = min(w, h)
        radius = size / 2 - 25

        painter.translate(w / 2, h / 2)

        self.draw_background(painter, radius)
        self.draw_zones(painter, radius)
        self.draw_scale(painter, radius)
        self.draw_peak_marker(painter, radius)
        self.draw_needle(painter, radius)
        self.draw_text(painter, radius)

    # =====================================================
    # Fondo
    # =====================================================
    def draw_background(self, painter, radius):
        painter.setPen(QPen(QColor(100, 116, 139), 4))
        painter.setBrush(QColor(255, 255, 255))

        painter.drawEllipse(
            int(-radius),
            int(-radius),
            int(radius * 2),
            int(radius * 2),
        )

    # =====================================================
    # Zonas por valores reales
    # =====================================================
    def draw_zones(self, painter, radius):
        arc_rect = QRectF(
            -radius + 22,
            -radius + 22,
            (radius - 22) * 2,
            (radius - 22) * 2
        )

        pen = QPen()
        pen.setWidth(12)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)

        start_angle = 225
        total_span = 270

        def rpm_to_qt_angle(rpm):
            # Conversión consistente con la aguja
            angle = start_angle - (rpm / self.max_rpm) * total_span
            return angle * 16

        # Verde
        painter.setPen(QPen(QColor(22, 163, 74), 12))
        painter.drawArc(
            arc_rect,
            int(rpm_to_qt_angle(0)),
            int(-(self.green_limit / self.max_rpm) * total_span * 16)
        )

        # Amarillo
        painter.setPen(QPen(QColor(217, 119, 6), 12))
        painter.drawArc(
            arc_rect,
            int(rpm_to_qt_angle(self.green_limit)),
            int(-((self.yellow_limit - self.green_limit) / self.max_rpm) * total_span * 16)
        )

        # Rojo
        painter.setPen(QPen(QColor(220, 38, 38), 12))
        painter.drawArc(
            arc_rect,
            int(rpm_to_qt_angle(self.yellow_limit)),
            int(-((self.max_rpm - self.yellow_limit) / self.max_rpm) * total_span * 16)
        )

    # =====================================================
    # Escala jerárquica 1k / 5k / 10k
    # =====================================================
    def draw_scale(self, painter, radius):
        start_angle = 225
        total_span = 270

        painter.setFont(QFont("Consolas", 10))
        metrics = painter.fontMetrics()

        for rpm in range(0, self.max_rpm + 1000, 1000):
            angle = start_angle - (rpm / self.max_rpm) * total_span
            rad = math.radians(angle)

            if rpm % 10000 == 0:
                length = 25
                thickness = 3
            elif rpm % 5000 == 0:
                length = 18
                thickness = 2
            else:
                length = 10
                thickness = 1

            painter.setPen(QPen(QColor(71, 85, 105), thickness))

            x1 = (radius - length) * math.cos(rad)
            y1 = -(radius - length) * math.sin(rad)
            x2 = radius * math.cos(rad)
            y2 = -radius * math.sin(rad)

            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

            # Texto solo cada 10k
            if rpm % 10000 == 0:
                label = f"{rpm//1000}"
                text_w = metrics.horizontalAdvance(label)
                text_h = metrics.height()

                tx = (radius - 50) * math.cos(rad)
                ty = -(radius - 50) * math.sin(rad)

                painter.drawText(
                    int(tx - text_w / 2),
                    int(ty + text_h / 4),
                    label
                )

    # =====================================================
    # Indicador de pico máximo
    # =====================================================
    def draw_peak_marker(self, painter, radius):
        start_angle = 225
        total_span = 270

        angle = start_angle - (self.peak_value / self.max_rpm) * total_span
        rad = math.radians(angle)

        painter.setPen(QPen(QColor(37, 99, 235), 2))

        x1 = (radius - 35) * math.cos(rad)
        y1 = -(radius - 35) * math.sin(rad)
        x2 = radius * math.cos(rad)
        y2 = -radius * math.sin(rad)

        painter.drawLine(int(x1), int(y1), int(x2), int(y2))

    # =====================================================
    # Aguja técnica
    # =====================================================
    def draw_needle(self, painter, radius):
        angle = 225 - (self.current_value / self.max_rpm) * 270
        rad = math.radians(angle)

        painter.setPen(QPen(QColor(51, 65, 85), 3))

        x = (radius - 60) * math.cos(rad)
        y = -(radius - 60) * math.sin(rad)

        painter.drawLine(0, 0, int(x), int(y))

        painter.setBrush(QColor(203, 213, 225))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(-10, -10, 20, 20)

    # =====================================================
    # Valor digital técnico
    # =====================================================
    def draw_text(self, painter, radius):
        painter.setPen(QColor(31, 41, 55))
        painter.setFont(QFont("Consolas", 20, QFont.Weight.DemiBold))

        value_str = f"{int(self.current_value):05d}"

        painter.drawText(
            -120,
            int(radius * 0.38),
            240,
            40,
            Qt.AlignmentFlag.AlignCenter,
            value_str
        )

        # Unidad más pequeña
        painter.setFont(QFont("Consolas", 12))
        painter.drawText(
            -120,
            int(radius * 0.38) + 25,
            240,
            20,
            Qt.AlignmentFlag.AlignCenter,
            "RPM"
        )
