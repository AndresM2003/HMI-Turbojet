# widgets/brayton_plot.py

import math
import numpy as np
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QHBoxLayout, QWidget
from PyQt6.QtCore import Qt
import pyqtgraph as pg


# Constante de gas ideal para aire (J/kg·K)
R_AIR   = 287.0
# Gamma para aire (cp/cv)
GAMMA   = 1.4
# Masa de aire de referencia (kg) — ajustar con dato real cuando esté disponible
M_AIR   = 0.05


def _specific_volume(T_K: float, P_Pa: float) -> float:
    """v = RT/P  (m³/kg)"""
    return (R_AIR * T_K) / max(P_Pa, 1.0)


def _isentropic_curve(T1: float, P1: float, T2: float, P2: float,
                      n: int = 40) -> tuple[list, list]:
    """
    Genera puntos de una curva isentrópica entre dos estados.
    Retorna (volúmenes, presiones) en unidades normalizadas.
    """
    pressures = np.linspace(P1, P2, n)
    volumes   = []
    for P in pressures:
        # Relación isentrópica: T/T1 = (P/P1)^((γ-1)/γ)
        T = T1 * (P / P1) ** ((GAMMA - 1) / GAMMA)
        v = _specific_volume(T, P)
        volumes.append(v)
    return list(volumes), list(pressures)


class BraytonPlot(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            BraytonPlot {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(4)

        # Título + leyenda
        top = QHBoxLayout()
        title = QLabel("BRAYTON CYCLE  —  P-v Diagram")
        title.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #475569; "
            "letter-spacing: 1px; border: none; background: transparent;"
        )
        top.addWidget(title)
        top.addStretch()

        # Indicadores de eficiencia térmica
        self.eta_lbl = QLabel("η = —")
        self.eta_lbl.setStyleSheet(
            "font-size: 10px; color: #2563EB; font-family: Consolas; "
            "border: none; background: transparent;"
        )
        top.addWidget(self.eta_lbl)

        layout.addLayout(top)

        # Plot
        self.plot = pg.PlotWidget()
        self.plot.setBackground("#FFFFFF")
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        self.plot.setLabel("left",   "Pressure (bar)")
        self.plot.setLabel("bottom", "Specific Volume (m³/kg)")

        # Curvas del ciclo
        self._curve_12 = self.plot.plot(pen=pg.mkPen("#2563EB", width=2))  # compresión
        self._curve_23 = self.plot.plot(pen=pg.mkPen("#ff7043", width=2))  # combustión
        self._curve_34 = self.plot.plot(pen=pg.mkPen("#ffa726", width=2))  # expansión
        self._curve_41 = self.plot.plot(pen=pg.mkPen("#66bb6a", width=2))  # escape

        # Puntos de estado
        self._points = self.plot.plot(
            pen=None,
            symbol="o",
            symbolSize=8,
            symbolBrush="#1F2937",
            symbolPen=pg.mkPen("#1F2937", width=1)
        )

        # Etiquetas de puntos (1, 2, 3, 4)
        self._point_labels: list[pg.TextItem] = []
        for i, label in enumerate(["1", "2", "3", "4"]):
            txt = pg.TextItem(
                text=label,
                color="#1F2937",
                anchor=(0.5, 1.2)
            )
            txt.setFont(pg.QtGui.QFont("Consolas", 9))
            self.plot.addItem(txt)
            self._point_labels.append(txt)

        # Leyenda manual
        legend_data = [
            ("#2563EB", "1→2 Isentropic compression"),
            ("#ff7043", "2→3 Isobaric combustion"),
            ("#ffa726", "3→4 Isentropic expansion"),
            ("#66bb6a", "4→1 Isobaric exhaust"),
        ]
        legend_widget = QWidget()
        legend_widget.setStyleSheet("background: transparent; border: none;")
        legend_layout = QHBoxLayout(legend_widget)
        legend_layout.setContentsMargins(4, 0, 4, 0)
        legend_layout.setSpacing(12)
        for color, text in legend_data:
            dot = QLabel("━")
            dot.setStyleSheet(f"color: {color}; font-size: 12px; border: none; background: transparent;")
            lbl = QLabel(text)
            lbl.setStyleSheet("font-size: 8px; color: #475569; border: none; background: transparent;")
            legend_layout.addWidget(dot)
            legend_layout.addWidget(lbl)
        legend_layout.addStretch()

        layout.addWidget(self.plot, stretch=1)
        layout.addWidget(legend_widget)

        # Estado inicial vacío
        self._draw_empty()

    # =====================================================
    # API pública
    # =====================================================
    def update_cycle(self, data: dict):
        """
        Actualiza el diagrama con los datos actuales del motor.
        Espera las claves del dict de datos del sistema.
        """
        try:
            # Extraer valores — con fallbacks seguros
            T1 = data.get("intake_temp",    25.0)  + 273.15   # K
            P1 = data.get("intake_pressure", 1.0)  * 1e5      # Pa

            T2 = T1 * (data.get("boost_pressure", 2.0) /
                       max(data.get("intake_pressure", 1.0), 0.1)) ** ((GAMMA-1)/GAMMA)
            P2 = data.get("boost_pressure",  2.0)  * 1e5

            T3 = data.get("comb_temp",      700.0) + 273.15
            P3 = data.get("comb_pressure",  3.0)   * 1e5

            T4 = T3 * (data.get("pressure",  1.2) /
                       max(data.get("comb_pressure", 3.0), 0.1)) ** ((GAMMA-1)/GAMMA)
            P4 = data.get("pressure",        1.2)  * 1e5

            self._draw_cycle(T1, P1, T2, P2, T3, P3, T4, P4)
            self._update_efficiency(T1, T2, T3, T4)

        except Exception:
            self._draw_empty()

    def clear(self):
        self._draw_empty()

    # =====================================================
    # Dibujo
    # =====================================================
    def _draw_cycle(self, T1, P1, T2, P2, T3, P3, T4, P4):
        # Calcular volúmenes específicos en los 4 puntos
        v1 = _specific_volume(T1, P1)
        v2 = _specific_volume(T2, P2)
        v3 = _specific_volume(T3, P3)
        v4 = _specific_volume(T4, P4)

        # Convertir presiones a bar para mostrar
        p1_bar = P1 / 1e5
        p2_bar = P2 / 1e5
        p3_bar = P3 / 1e5
        p4_bar = P4 / 1e5

        # 1→2 Compresión isentrópica
        v12, p12 = _isentropic_curve(T1, P1, T2, P2)
        self._curve_12.setData(v12, [p/1e5 for p in p12])

        # 2→3 Combustión isobárica (presión constante P2≈P3, volumen aumenta)
        self._curve_23.setData([v2, v3], [p2_bar, p3_bar])

        # 3→4 Expansión isentrópica
        v34, p34 = _isentropic_curve(T3, P3, T4, P4)
        self._curve_34.setData(v34, [p/1e5 for p in p34])

        # 4→1 Escape isobárico
        self._curve_41.setData([v4, v1], [p4_bar, p1_bar])

        # Puntos de estado
        self._points.setData(
            [v1, v2, v3, v4],
            [p1_bar, p2_bar, p3_bar, p4_bar]
        )

        # Etiquetas
        offsets = [(0, -0.05), (0, 0.05), (0, 0.05), (0, -0.05)]
        for i, (v, p, (dv, dp)) in enumerate(
            zip([v1, v2, v3, v4],
                [p1_bar, p2_bar, p3_bar, p4_bar],
                offsets)
        ):
            self._point_labels[i].setPos(v + dv * v, p + dp * p)

    def _draw_empty(self):
        empty = [[], []]
        self._curve_12.setData(*empty)
        self._curve_23.setData(*empty)
        self._curve_34.setData(*empty)
        self._curve_41.setData(*empty)
        self._points.setData([], [])
        self.eta_lbl.setText("η = —")

    def _update_efficiency(self, T1, T2, T3, T4):
        """
        Eficiencia térmica del ciclo de Brayton ideal:
        η = 1 - T1/T2  (para ciclo ideal con relación de compresión)
        """
        try:
            eta = 1.0 - (T1 / max(T2, 1.0))
            eta = max(0.0, min(eta, 1.0))
            self.eta_lbl.setText(f"η = {eta*100:.1f}%")
        except Exception:
            self.eta_lbl.setText("η = —")