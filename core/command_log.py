"""Texto del registro de acciones (LOG) de la pantalla principal. Sin Qt."""

LABELS = {
    "oil_pump": "OIL PUMP",
    "fuel_solenoid": "FUEL SOLENOID",
    "fuel_servo": "FUEL SERVO",
    "spark_pulse": "SPARK PULSE",
    "control_mode": "CONTROL MODE",
    "stop": "STOP",
    "emergency_stop": "EMERGENCY STOP",
}

_EVENTS = {  # evento → (nivel, texto)
    "SENT": ("info", "SENT"),
    "ACK": ("ok", "ACK ✓"),
    "REJECTED": ("error", "REJECTED"),
    "NO_ACK": ("warn", "NO ACK"),
    "FAILED": ("error", "SEND FAILED"),
    "BLOCKED": ("warn", "BLOCKED"),
}


def describe_command(command: str, value=None) -> str:
    label = LABELS.get(command, command.upper())
    if value is None:
        return label
    if isinstance(value, (int, float)):
        return f"{label}: {value:g} %"
    return f"{label}: {str(value).upper()}"


def format_event(event: str, command: str, value=None, message: str = "") -> tuple[str, str]:
    level, text = _EVENTS.get(event, ("info", event))
    line = f"{describe_command(command, value)}   {text}"
    if message and event in ("REJECTED", "BLOCKED", "FAILED"):
        line += f" — {message}"
    return level, line
