# ui/systems_panel.py

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QProgressBar, QScrollArea
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from dataclasses import dataclass


# =====================================================
# Modelo de variable
# =====================================================
@dataclass
class SystemVariable:
    key:        str
    label:      str
    unit:       str
    min_val:    float
    max_val:    float
    warn_limit: float   # por encima → WARNING
    fault_limit: float  # por encima → FAULT
    fmt:        str = ".1f"


# =====================================================
# Definición de sistemas y sus variables
# =====================================================
MAIN_SYSTEM_VARS = [
    SystemVariable("intake_temp",     "Intake Temp",       "°C",    0,    60,    45,    55,    ".1f"),
    SystemVariable("intake_pressure", "Intake Pressure",   "bar",   0.8,  2.5,   2.0,   2.3,   ".2f"),
    SystemVariable("intake_flow",     "Intake Air Flow",   "kg/s",  0,    1.2,   1.0,   1.15,  ".3f"),
    SystemVariable("comb_temp",       "Combustion Temp",   "°C",    0,    900,   700,   850,   ".1f"),
    SystemVariable("comb_pressure",   "Combustion Press",  "bar",   0,    5.0,   3.5,   4.5,   ".2f"),
    SystemVariable("turbine_inlet",   "Turbine Inlet Temp","°C",    0,    950,   750,   900,   ".1f"),
    SystemVariable("turbine_outlet",  "Turbine Outlet EGT","°C",    0,    800,   700,   780,   ".1f"),
    SystemVariable("turbo_rpm",       "Turbo RPM",         "RPM",   0,    150000,120000,140000,".0f"),
    SystemVariable("boost_pressure",  "Boost Pressure",    "bar",   0,    3.5,   2.8,   3.2,   ".2f"),
    SystemVariable("exhaust_temp",    "Exhaust Temp",      "°C",    0,    700,   550,   650,   ".1f"),
]

FUEL_SYSTEM_VARS = [
    SystemVariable("tank_pressure",   "Tank Pressure",     "bar",   0,    10.0,  8.0,   9.5,   ".2f"),
    SystemVariable("tank_level",      "Tank Level",        "%",     0,    100,   20,    10,    ".1f"),
    SystemVariable("fuel_flow",       "Fuel Flow",         "L/min", 0,    50,    35,    45,    ".1f"),
    SystemVariable("fuel_pressure",   "Fuel Pressure",     "bar",   0,    6.0,   4.5,   5.5,   ".2f"),
    SystemVariable("fuel_temp",       "Fuel Temp",         "°C",    0,    60,    45,    55,    ".1f"),
    SystemVariable("valve_position",  "Valve Position",    "%",     0,    100,   90,    95,    ".1f"),
    SystemVariable("regulator_press", "Regulator Press",   "bar",   0,    4.0,   3.0,   3.8,   ".2f"),
]

LUBRICATION_VARS = [
    SystemVariable("oil_pressure",    "Oil Pressure",      "bar",   0,    6.0,   4.5,   5.5,   ".2f"),
    SystemVariable("oil_temp",        "Oil Temp",          "°C",    0,    120,   90,    110,   ".1f"),
    SystemVariable("oil_flow",        "Oil Flow",          "L/min", 0,    10,    7.5,   9.0,   ".2f"),
    SystemVariable("oil_level",       "Oil Level",         "%",     0,    100,   25,    10,    ".1f"),
    SystemVariable("pump_rpm",        "Pump RPM",          "RPM",   0,    3000,  2500,  2800,  ".0f"),
    SystemVariable("oil_inlet_temp",  "Turbo Inlet Temp",  "°C",    0,    80,    65,    75,    ".1f"),
    SystemVariable("oil_outlet_temp", "Turbo Outlet Temp", "°C",    0,    120,   95,    110,   ".1f"),
    SystemVariable("filter_dp",       "Filter ΔP",         "bar",   0,    1.0,   0.6,   0.8,   ".2f"),
]


# =====================================================
# Widget de variable individual
# =====================================================
class VariableRow(QWidget):
    _STATUS_COLORS = {
        "OK":      "#2ecc71",
        "WARNING": "#f39c12",
        "FAULT":   "#e74c3c",
    }

    def __init__(self, var: SystemVariable, parent=None):
        super().__init__(parent)
        self.var = var
        self.setFixedHeight(52)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(3)

        # --- Fila superior: label | valor | estado ---
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.label_lbl = QLabel(var.label)
        self.label_lbl.setStyleSheet("font-size: 11px; color: #475569;")
        self.label_lbl.setFixedWidth(140)

        self.value_lbl = QLabel("—")
        self.value_lbl.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #1F2937; font-family: Consolas;"
        )
        self.value_lbl.setFixedWidth(90)

        self.unit_lbl = QLabel(var.unit)
        self.unit_lbl.setStyleSheet("font-size: 10px; color: #64748B;")
        self.unit_lbl.setFixedWidth(40)

        self.status_lbl = QLabel("—")
        self.status_lbl.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #64748B; "
            "padding: 1px 6px; border-radius: 2px;"
        )
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setFixedWidth(60)

        top_row.addWidget(self.label_lbl)
        top_row.addWidget(self.value_lbl)
        top_row.addWidget(self.unit_lbl)
        top_row.addStretch()
        top_row.addWidget(self.status_lbl)

        # --- Barra de progreso ---
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #E2E8F0;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #2ecc71;
                border-radius: 2px;
            }
        """)

        layout.addLayout(top_row)
        layout.addWidget(self.progress)

    def update_value(self, value: float):
        self.value_lbl.setText(f"{value:{self.var.fmt}}")

        # Estado
        if value >= self.var.fault_limit:
            status = "FAULT"
        elif value >= self.var.warn_limit:
            status = "WARNING"
        else:
            status = "OK"

        color = self._STATUS_COLORS[status]
        self.status_lbl.setText(status)
        self.status_lbl.setStyleSheet(
            f"font-size: 10px; font-weight: bold; color: {color}; "
            f"padding: 1px 6px; border-radius: 2px;"
        )

        # Barra de progreso
        span   = self.var.max_val - self.var.min_val
        norm   = (value - self.var.min_val) / span if span > 0 else 0
        norm   = max(0.0, min(1.0, norm))
        self.progress.setValue(int(norm * 1000))

        # Color de la barra según estado
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: #E2E8F0;
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 2px;
            }}
        """)

    def clear(self):
        self.value_lbl.setText("—")
        self.status_lbl.setText("—")
        self.status_lbl.setStyleSheet(
            "font-size: 10px; font-weight: bold; color: #64748B; "
            "padding: 1px 6px; border-radius: 2px;"
        )
        self.progress.setValue(0)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #E2E8F0;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #CBD5E1;
                border-radius: 2px;
            }
        """)


# =====================================================
# Columna de sistema
# =====================================================
class SystemColumn(QFrame):
    def __init__(self, title: str, variables: list[SystemVariable], parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            SystemColumn {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)

        self._rows: dict[str, VariableRow] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        # Título
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #2563EB; letter-spacing: 2px;"
        )
        outer.addWidget(title_lbl)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #CBD5E1; border: none; max-height: 1px;")
        outer.addWidget(sep)

        # Scroll para muchas variables
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: #F1F5F9;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #CBD5E1;
                border-radius: 3px;
            }
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(2)

        for var in variables:
            row = VariableRow(var)
            self._rows[var.key] = row
            content_layout.addWidget(row)

            # Separador entre variables
            sep_line = QFrame()
            sep_line.setFrameShape(QFrame.Shape.HLine)
            sep_line.setStyleSheet(
                "background-color: #E2E8F0; border: none; max-height: 1px;"
            )
            content_layout.addWidget(sep_line)

        content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def update_data(self, data: dict):
        for key, row in self._rows.items():
            if key in data:
                row.update_value(data[key])

    def clear(self):
        for row in self._rows.values():
            row.clear()


# =====================================================
# Panel completo de sistemas
# =====================================================
class SystemsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.main_col  = SystemColumn("MAIN SYSTEM",    MAIN_SYSTEM_VARS)
        self.fuel_col  = SystemColumn("FUEL SYSTEM",    FUEL_SYSTEM_VARS)
        self.lub_col   = SystemColumn("LUBRICATION",    LUBRICATION_VARS)

        layout.addWidget(self.main_col)
        layout.addWidget(self.fuel_col)
        layout.addWidget(self.lub_col)

    def update_data(self, data: dict):
        self.main_col.update_data(data)
        self.fuel_col.update_data(data)
        self.lub_col.update_data(data)

    def clear(self):
        self.main_col.clear()
        self.fuel_col.clear()
        self.lub_col.clear()