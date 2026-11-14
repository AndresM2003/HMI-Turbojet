# ui/panels.py

from PyQt6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QMenu, QCheckBox, QWidgetAction, QSizePolicy
)
from PyQt6.QtCore import Qt
import pyqtgraph as pg


_PANEL_BG  = "#FFFFFF"
_PANEL_BDR = "#CBD5E1"


def _panel_style(class_name: str) -> str:
    return f"""
        {class_name} {{
            background-color: {_PANEL_BG};
            border: 1px solid {_PANEL_BDR};
            border-radius: 4px;
        }}
        QLabel {{
            border: none;
            background: transparent;
        }}
    """


# =====================================================
# Definición de variables disponibles
# =====================================================
AVAILABLE_SIGNALS = {
    "rpm":       {"label": "RPM",       "color": "#2563EB", "unit": "RPM"},
    "egt":       {"label": "EGT",       "color": "#ff7043", "unit": "°C"},
    "fuel_flow": {"label": "Fuel Flow", "color": "#66bb6a", "unit": "L/min"},
    "pressure":  {"label": "Pressure",  "color": "#ffa726", "unit": "bar"},
}

PRESETS = {
    "RPM & EGT":           ["rpm", "egt"],
    "Fuel Flow & Pressure": ["fuel_flow", "pressure"],
    "All signals":         ["rpm", "egt", "fuel_flow", "pressure"],
}


# =====================================================
# Panel de gráfica configurable
# =====================================================
class ConfigurablePlotPanel(QFrame):
    def __init__(self, default_signals: list[str]):
        super().__init__()
        self.setStyleSheet(_panel_style("ConfigurablePlotPanel"))

        self._active_signals: list[str] = list(default_signals)
        self._curves: dict[str, pg.PlotCurveItem] = {}
        self._data:   dict[str, list] = {key: [] for key in AVAILABLE_SIGNALS}
        self._x:      list[float] = []

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(6, 6, 6, 4)
        main_layout.setSpacing(4)
        self.setLayout(main_layout)

        # --- Toolbar ---
        toolbar = QWidget()
        toolbar.setStyleSheet("background: transparent; border: none;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)

        self.title_label = QLabel()
        self.title_label.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #475569; letter-spacing: 1px;"
        )
        toolbar_layout.addWidget(self.title_label)
        toolbar_layout.addStretch()

        # Botón de configuración
        self.config_btn = QPushButton("⚙ Signals")
        self.config_btn.setStyleSheet("""
            QPushButton {
                background-color: #E2E8F0;
                color: #475569;
                font-size: 10px;
                padding: 3px 8px;
                border: 1px solid #94A3B8;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #94A3B8;
                color: #1F2937;
            }
        """)
        self.config_btn.clicked.connect(self._show_config_menu)
        toolbar_layout.addWidget(self.config_btn)

        main_layout.addWidget(toolbar)

        # --- Plot ---
        self.plot = pg.PlotWidget()
        self.plot.setBackground(_PANEL_BG)
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel("bottom", "Time (s)")
        self.plot.addLegend(offset=(10, 10))
        main_layout.addWidget(self.plot)

        self._rebuild_curves()

    # =====================================================
    # Menú de configuración
    # =====================================================
    def _show_config_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #F1F5F9;
                border: 1px solid #CBD5E1;
                color: #1F2937;
                padding: 4px;
            }
            QMenu::separator {
                height: 1px;
                background: #CBD5E1;
                margin: 4px 0px;
            }
        """)

        # --- Sección PRESETS ---
        preset_label = QWidgetAction(menu)
        lbl = QLabel("  PRESETS")
        lbl.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #475569; "
            "letter-spacing: 1px; padding: 2px 4px;"
        )
        preset_label.setDefaultWidget(lbl)
        menu.addAction(preset_label)

        for preset_name, signals in PRESETS.items():
            action = menu.addAction(f"  {preset_name}")
            action.setData(signals)
            action.triggered.connect(
                lambda checked, s=signals: self._apply_preset(s)
            )

        menu.addSeparator()

        # --- Sección MANUAL ---
        manual_label = QWidgetAction(menu)
        lbl2 = QLabel("  MANUAL")
        lbl2.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #475569; "
            "letter-spacing: 1px; padding: 2px 4px;"
        )
        manual_label.setDefaultWidget(lbl2)
        menu.addAction(manual_label)

        self._checkboxes: dict[str, QCheckBox] = {}
        for key, meta in AVAILABLE_SIGNALS.items():
            action = QWidgetAction(menu)
            cb = QCheckBox(f"  {meta['label']}")
            cb.setChecked(key in self._active_signals)
            cb.setStyleSheet(f"""
                QCheckBox {{
                    color: {meta['color']};
                    font-size: 11px;
                    padding: 4px 8px;
                    background: transparent;
                }}
                QCheckBox::indicator {{
                    width: 14px;
                    height: 14px;
                }}
            """)
            cb.stateChanged.connect(
                lambda state, k=key: self._on_checkbox_changed(k, state)
            )
            action.setDefaultWidget(cb)
            menu.addAction(action)
            self._checkboxes[key] = cb

        menu.exec(self.config_btn.mapToGlobal(
            self.config_btn.rect().bottomLeft()
        ))

    # =====================================================
    # Aplicar preset
    # =====================================================
    def _apply_preset(self, signals: list[str]):
        self._active_signals = list(signals)
        self._rebuild_curves()

    # =====================================================
    # Checkbox manual
    # =====================================================
    def _on_checkbox_changed(self, key: str, state: int):
        if state == Qt.CheckState.Checked.value:
            if key not in self._active_signals:
                self._active_signals.append(key)
        else:
            if key in self._active_signals:
                self._active_signals.remove(key)

        # Al menos una señal debe estar activa
        if not self._active_signals:
            self._active_signals.append(key)
            if key in self._checkboxes:
                self._checkboxes[key].setChecked(True)
            return

        self._rebuild_curves()

    # =====================================================
    # Reconstruir curvas
    # =====================================================
    def _rebuild_curves(self):
        self.plot.clear()
        self.plot.addLegend(offset=(10, 10))
        self._curves = {}

        for key in self._active_signals:
            meta = AVAILABLE_SIGNALS[key]
            curve = self.plot.plot(
                pen=pg.mkPen(meta["color"], width=2),
                name=meta["label"]
            )
            self._curves[key] = curve

        # Actualizar título con las señales activas
        labels = [AVAILABLE_SIGNALS[k]["label"] for k in self._active_signals]
        self.title_label.setText(" & ".join(labels).upper())

        # Actualizar eje Y
        y_units = list({AVAILABLE_SIGNALS[k]["unit"] for k in self._active_signals})
        self.plot.setLabel("left", " / ".join(y_units))

        # Redibujar con datos existentes
        self._redraw()

    # =====================================================
    # Redibujar con datos actuales
    # =====================================================
    def _redraw(self):
        for key, curve in self._curves.items():
            curve.setData(self._x, self._data[key])

    # =====================================================
    # API pública
    # =====================================================
    def update_plot(self, t: float, data: dict):
        self._x.append(t)
        for key in AVAILABLE_SIGNALS:
            self._data[key].append(data.get(key, 0))

        # Ventana de 300 muestras
        self._x = self._x[-300:]
        for key in AVAILABLE_SIGNALS:
            self._data[key] = self._data[key][-300:]

        self._redraw()

    def freeze(self):
        pass


# =====================================================
# Panel de datos del motor — sin cambios
# =====================================================
class EngineDataPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(_panel_style("EngineDataPanel"))

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        title = QLabel("ENGINE STATUS")
        title.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #475569; letter-spacing: 2px;"
        )
        layout.addWidget(title)

        self._rows: dict[str, tuple[QLabel, str]] = {}
        fields = [
            ("rpm",       "RPM",       "",     "RPM"),
            ("egt",       "EGT",       ".1f",  "°C"),
            ("fuel_flow", "FUEL FLOW", ".1f",  "L/min"),
            ("pressure",  "PRESSURE",  ".2f",  "BAR"),
        ]

        for key, label_text, fmt, unit in fields:
            row_widget = QWidget()
            row_widget.setStyleSheet("background: transparent; border: none;")
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)

            lbl = QLabel(label_text)
            lbl.setFixedWidth(76)
            lbl.setStyleSheet("font-size: 11px; color: #475569;")

            val = QLabel("—")
            val.setStyleSheet(
                "font-size: 21px; font-weight: bold; color: #1F2937; font-family: Consolas;"
            )

            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet("font-size: 10px; color: #64748B;")

            row.addWidget(lbl,      alignment=Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(val,      alignment=Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(unit_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
            row.addStretch()

            layout.addWidget(row_widget)
            self._rows[key] = (val, fmt)

        layout.addStretch()
        self.setLayout(layout)

    def update_data(self, data: dict):
        for key, (val_label, fmt) in self._rows.items():
            value = data.get(key, 0)
            val_label.setText(f"{value:{fmt}}" if fmt else f"{int(value):,}")

    def clear(self):
        for val_label, _ in self._rows.values():
            val_label.setText("—")