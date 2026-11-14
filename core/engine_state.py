# core/engine_state.py

from enum import Enum
from dataclasses import dataclass, field


class EngineStatus(Enum):
    IDLE      = 0
    STARTING  = 1
    RUNNING   = 2
    STOPPING  = 3
    EMERGENCY = 4
    FAULT     = 5


@dataclass
class AlertLimits:
    """Límites de alerta. Centraliza todos los umbrales en un solo lugar."""
    egt_warning:   float = 700.0   # °C
    fuel_low:      float = 12.0    # L/min
    rpm_max:       float = 40000.0 # RPM
    pressure_min:  float = 1.0     # bar
    pressure_max:  float = 4.0     # bar


class EngineState:
    def __init__(self):
        self.status:    EngineStatus = EngineStatus.IDLE
        self.connected: bool         = False

        # Datos del motor
        self.rpm:       float = 0.0
        self.egt:       float = 0.0
        self.fuel_flow: float = 0.0
        self.pressure:  float = 0.0

        # Límites
        self.limits = AlertLimits()

    # =====================================================
    # Actualización desde datos crudos
    # =====================================================
    def update(self, data: dict) -> None:
        """
        Actualiza el estado del motor desde un diccionario de datos.
        Valida que los campos existan y sean numéricos.
        """
        self.rpm       = self._parse(data, "rpm",       0.0)
        self.egt       = self._parse(data, "egt",       0.0)
        self.fuel_flow = self._parse(data, "fuel_flow", 0.0)
        self.pressure  = self._parse(data, "pressure",  0.0)

    def _parse(self, data: dict, key: str, default: float) -> float:
        try:
            return float(data[key])
        except (KeyError, TypeError, ValueError):
            return default

    # =====================================================
    # Evaluación de alertas
    # =====================================================
    def check_alerts(self) -> dict[str, bool]:
        """
        Evalúa las condiciones de alerta contra los límites definidos.
        Retorna un dict {nombre_alerta: bool}.
        """
        return {
            "egt_high":     self.egt       > self.limits.egt_warning,
            "fuel_low":     self.fuel_flow < self.limits.fuel_low,
            "rpm_over":     self.rpm       > self.limits.rpm_max,
            "pressure_low": self.pressure  < self.limits.pressure_min,
            "pressure_high":self.pressure  > self.limits.pressure_max,
        }

    # =====================================================
    # Serialización
    # =====================================================
    def to_dict(self) -> dict:
        """Serializa el estado actual para UI o logging."""
        return {
            "rpm":       self.rpm,
            "egt":       self.egt,
            "fuel_flow": self.fuel_flow,
            "pressure":  self.pressure,
        }

    # =====================================================
    # Estado del motor
    # =====================================================
    def set_status(self, status: EngineStatus) -> None:
        self.status = status

    @property
    def is_active(self) -> bool:
        """True si el motor está en un estado operativo."""
        return self.status in (
            EngineStatus.STARTING,
            EngineStatus.RUNNING,
            EngineStatus.STOPPING,
        )