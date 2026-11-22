import math

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

_BOX_FILL = QColor("#FFFFFF")
_BOX_LINE = QColor("#8A959C")
_PIPE = QColor("#59656C")
_TEXT = QColor("#2F3A41")
_VALUE = QColor("#14202A")
_MUTED = QColor("#5F6B73")
_TC = QColor("#1F6FA8")
_GAS = QColor("#8C6D1F")
_AIR = (QColor("#E6F0F8"), QColor("#4F83AD"))
_COMB = (QColor("#FBE9D7"), QColor("#C97B2A"))
_FUEL = (QColor("#FFF3D1"), QColor("#B7891F"))
_OIL = (QColor("#E3F3E8"), QColor("#3E9B63"))


def _fmt(value, decimals=1, unit=""):
    if value is None:
        return "—"
    return f"{value:,.{decimals}f} {unit}".strip()


class RPMGauge(QWidget):
    """Gauge de RPM. Sin límites configurados el arco es neutro (sin verde/amarillo/rojo)."""

    START_ANGLE = 225
    SPAN = 270

    def __init__(self, max_rpm: float = 40000, caution_rpm: float | None = None,
                 limit_rpm: float | None = None, parent=None):
        super().__init__(parent)
        self.max_rpm = max_rpm
        self.caution_rpm = caution_rpm
        self.limit_rpm = limit_rpm
        self._target = 0.0
        self._shown = 0.0
        self._has_value = False
        self.setMinimumSize(180, 180)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(30)

    def set_value(self, value: float | None):
        self._has_value = value is not None
        self._target = 0.0 if value is None else max(0.0, min(float(value), self.max_rpm))
        self.update()

    def _animate(self):
        diff = self._target - self._shown
        if abs(diff) > 0.5:
            self._shown += diff * 0.2
            self.update()

    def _angle(self, rpm: float) -> float:
        return self.START_ANGLE - (rpm / self.max_rpm) * self.SPAN

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height())
        radius = size / 2 - 8
        p.translate(self.width() / 2, self.height() / 2)

        p.setPen(QPen(QColor("#8A959C"), 3))
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QPointF(0, 0), radius, radius)

        arc = QRectF(-radius + radius * 0.10, -radius + radius * 0.10, (radius * 0.90) * 2, (radius * 0.90) * 2)
        width = max(5, radius * 0.07)
        zones = [(0, self.max_rpm, "#AEB7BC")]
        if self.caution_rpm is not None and self.limit_rpm is not None:
            zones = [(0, self.caution_rpm, "#3E9B63"), (self.caution_rpm, self.limit_rpm, "#D9A21E"),
                     (self.limit_rpm, self.max_rpm, "#C9483D")]
        for start, end, color in zones:
            p.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawArc(arc, int(self._angle(start) * 16), int(-(end - start) / self.max_rpm * self.SPAN * 16))

        if zones[0][2] == "#AEB7BC" and self._shown > 0:
            p.setPen(QPen(QColor("#1F6FA8"), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawArc(arc, int(self._angle(0) * 16), int(-self._shown / self.max_rpm * self.SPAN * 16))

        ticks = 40
        major_every = 10
        label_font = QFont("Consolas", max(6, int(radius * 0.075)))
        p.setFont(label_font)
        for i in range(ticks + 1):
            rpm = self.max_rpm * i / ticks
            rad = math.radians(self._angle(rpm))
            major = i % major_every == 0
            length = radius * (0.13 if major else 0.07)
            p.setPen(QPen(QColor("#1F2A30"), 2 if major else 1))
            p.drawLine(QPointF((radius - length) * math.cos(rad), -(radius - length) * math.sin(rad)),
                       QPointF(radius * math.cos(rad), -radius * math.sin(rad)))
            if major:
                tx = (radius * 0.76) * math.cos(rad)
                ty = -(radius * 0.76) * math.sin(rad)
                p.setPen(_TEXT)
                p.drawText(QRectF(tx - 22, ty - 9, 44, 18), Qt.AlignmentFlag.AlignCenter, f"{rpm / 1000:g}k")

        rad = math.radians(self._angle(self._shown))
        p.setPen(QPen(QColor("#14202A") if self._has_value else QColor("#AEB7BC"), max(2, radius * 0.025)))
        p.drawLine(QPointF(0, 0), QPointF(radius * 0.62 * math.cos(rad), -radius * 0.62 * math.sin(rad)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#8A959C"))
        p.drawEllipse(QPointF(0, 0), radius * 0.05, radius * 0.05)

        p.setPen(_VALUE)
        p.setFont(QFont("Consolas", max(9, int(radius * 0.17)), QFont.Weight.DemiBold))
        text = f"{self._target:,.0f}" if self._has_value else "—"
        p.drawText(QRectF(-radius * 0.4, radius * 0.22, radius * 0.8, radius * 0.22), Qt.AlignmentFlag.AlignCenter, text)
        p.setPen(_MUTED)
        p.setFont(QFont("Consolas", max(7, int(radius * 0.09))))
        p.drawText(QRectF(-radius * 0.2, radius * 0.44, radius * 0.4, radius * 0.14), Qt.AlignmentFlag.AlignCenter, "RPM")


class ProcessMimic(QWidget):
    """Esquema tipo P&ID del motor con los puntos de medición y sus valores en vivo.

    Los símbolos de equipo (bomba, tanque, solenoide, servo) son estáticos: el protocolo
    de telemetría v1 no reporta su estado, así que no se dibuja ningún estado.
    """

    W, H = 660.0, 340.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._s: dict = {}
        self.setMinimumSize(420, 220)

    def set_sensors(self, sensors: dict):
        self._s = dict(sensors)
        self.update()

    # --- helpers de dibujo (coordenadas lógicas 660x340) ---
    def _box(self, p, x, y, w, h, text, size=10, colors=None):
        fill, line = colors or (_BOX_FILL, _BOX_LINE)
        p.setPen(QPen(line, 1.5))
        p.setBrush(fill)
        p.drawRect(QRectF(x, y, w, h))
        p.setPen(_TEXT)
        p.setFont(QFont("Segoe UI", 1))
        font = p.font(); font.setPixelSize(size); p.setFont(font)
        p.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter, text)

    def _text(self, p, x, y, w, h, text, size=10, color=_TEXT, bold=False, align=Qt.AlignmentFlag.AlignCenter):
        font = QFont("Segoe UI"); font.setPixelSize(size); font.setBold(bold)
        p.setFont(font); p.setPen(color)
        p.drawText(QRectF(x, y, w, h), align, text)

    def _pipe(self, p, x1, y1, x2, y2, arrow=False, dashed=False, color=_PIPE):
        pen = QPen(color, 2.5 if color is not _PIPE else 2, Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine)
        p.setPen(pen)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        if arrow:
            p.setBrush(color)
            p.drawPolygon(QPolygonF([QPointF(x2, y2), QPointF(x2 - 8, y2 - 5), QPointF(x2 - 8, y2 + 5)]))

    def _tag(self, p, cx, cy, name, value, color, diamond=False, value_above=True, unit="°C"):
        p.setPen(QPen(color, 2))
        p.setBrush(_BOX_FILL)
        if diamond:
            p.drawPolygon(QPolygonF([QPointF(cx, cy - 20), QPointF(cx + 20, cy), QPointF(cx, cy + 20), QPointF(cx - 20, cy)]))
        else:
            p.drawEllipse(QPointF(cx, cy), 19, 19)
        self._text(p, cx - 19, cy - 10, 38, 20, name, 10, _VALUE, True)
        ty = cy - 44 if value_above else cy + 21
        self._text(p, cx - 50, ty, 100, 20, _fmt(value, 1, unit), 12, _VALUE, True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / self.W, self.height() / self.H)
        p.translate((self.width() - self.W * scale) / 2, (self.height() - self.H * scale) / 2)
        p.scale(scale, scale)
        s = self._s

        # camino de aire
        self._text(p, 0, 120, 85, 30, "AIR IN ▶", 10, _MUTED)
        self._pipe(p, 70, 135, 95, 135, arrow=True, color=_AIR[1])
        self._box(p, 95, 110, 55, 50, "MAF", colors=_AIR)
        self._text(p, 70, 84, 105, 20, _fmt(s.get("maf_g_s"), 2, "g/s"), 12, _VALUE, True)
        self._pipe(p, 150, 135, 170, 135, color=_AIR[1])
        self._box(p, 170, 85, 100, 100, "COMPRESSOR", colors=_AIR)
        self._pipe(p, 270, 135, 300, 135, arrow=True, color=_AIR[1])
        self._box(p, 300, 85, 130, 100, "COMBUSTION\nCHAMBER", colors=_COMB)
        self._pipe(p, 430, 135, 460, 135, arrow=True, color=_COMB[1])
        self._box(p, 460, 85, 100, 100, "TURBINE", colors=_AIR)
        self._pipe(p, 560, 135, 590, 135, arrow=True, color=_COMB[1])
        self._text(p, 592, 120, 66, 30, "EXHAUST", 10, _MUTED)

        # eje, RPM y aceite
        self._pipe(p, 220, 205, 520, 205, dashed=True)
        self._text(p, 375, 187, 90, 16, "TURBO SHAFT", 9, _MUTED, align=Qt.AlignmentFlag.AlignLeft)
        self._box(p, 480, 194, 60, 22, "RPM", 9)
        self._text(p, 445, 220, 130, 22, _fmt(s.get("rpm"), 0, "rpm"), 12, _VALUE, True)
        self._pipe(p, 210, 205, 210, 265, color=_OIL[1])
        self._box(p, 170, 265, 80, 50, "OIL\nPUMP", colors=_OIL)
        self._tag(p, 282, 290, "T5", s.get("t5_c"), _TC, value_above=False)

        # línea de combustible
        self._pipe(p, 365, 185, 365, 270, color=_FUEL[1])
        self._box(p, 350, 215, 30, 22, "SRV", 8, colors=_FUEL)
        self._box(p, 350, 245, 30, 22, "SV", 8, colors=_FUEL)
        self._box(p, 320, 270, 90, 55, "C3H8\nTANK", colors=_FUEL)
        self._tag(p, 450, 292, "G1", s.get("mq6_1_ppm"), _GAS, diamond=True, value_above=False, unit="ppm")
        self._tag(p, 540, 292, "G2", s.get("mq6_2_ppm"), _GAS, diamond=True, value_above=False, unit="ppm")

        # temperaturas del ciclo
        for cx, target_y, name, key in ((240, 85, "T1", "t1_c"), (325, 85, "T2", "t2_c"),
                                        (415, 85, "T3", "t3_c"), (505, 85, "T4", "t4_c")):
            self._pipe(p, cx, 74, cx, target_y)
            self._tag(p, cx, 55, name, s.get(key), _TC)

        for i, line in enumerate(("○ thermocouple   ◇ MQ6 gas", "▭ RPM sensor", "equipment states: not reported")):
            self._text(p, 0, 2 + i * 14, 185, 14, line, 9, _MUTED, align=Qt.AlignmentFlag.AlignLeft)
