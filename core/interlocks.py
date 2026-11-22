"""Enclavamientos de los comandos. Función pura: decide si un comando puede enviarse ahora.

Basado en la secuencia de encendido del proyecto: bomba de aceite → combustible → bujía.
Los comandos hacia el lado seguro (cerrar, apagar combustible, silenciar, parar) casi
siempre se permiten; solo necesitan conexión.
"""

from dataclasses import dataclass, field

# Comandos que solo valen en modo manual (en automático el controlador los maneja solo).
MANUAL_COMMANDS = ("oil_pump", "fuel_solenoid", "fuel_servo", "spark_pulse")


@dataclass(frozen=True)
class InterlockContext:
    connected: bool
    estop_released: bool | None
    critical_alarm: str | None  # código de la primera alarma crítica activa, si hay
    acked: dict = field(default_factory=dict)  # comando → último valor confirmado por el ESP32
    # acked["control_mode"] es el modo confirmado ("auto" por defecto)


def check_command(command: str, value, ctx: InterlockContext) -> tuple[bool, str]:
    if not ctx.connected:
        return False, "Not connected"
    if command in MANUAL_COMMANDS and ctx.acked.get("control_mode") != "manual":
        return False, "Automatic control is active — enable MANUAL CONTROL first"
    energizing = (
        (command == "fuel_solenoid" and value == "open")
        or (command == "fuel_servo" and value is not None and value > 0)
        or command == "spark_pulse"
    )
    if energizing:
        if ctx.estop_released is not True:
            return False, "Physical E-STOP is pressed or its state is unknown"
        if ctx.critical_alarm:
            return False, f"Critical alarm active: {ctx.critical_alarm}"
    if command == "fuel_solenoid" and value == "open" and ctx.acked.get("oil_pump") != "on":
        return False, "Turn the oil pump ON first (and wait for its ACK)"
    if command == "spark_pulse":
        if ctx.acked.get("oil_pump") != "on":
            return False, "Turn the oil pump ON first (and wait for its ACK)"
        if ctx.acked.get("fuel_solenoid") != "open":
            return False, "Open the fuel solenoid first (and wait for its ACK)"
    return True, ""


def needs_confirmation(command: str, value, rpm: float | None) -> str | None:
    if command == "control_mode" and value == "manual":
        return ("Take manual control?\n\nThe controller stops managing the oil pump, fuel solenoid, "
                "fuel servo and spark. You will have to operate them yourself.")
    if command == "oil_pump" and value == "off" and (rpm is None or rpm > 0):
        return ("The turbine may still be spinning. Turning the oil pump off "
                "can damage the turbo bearings.\n\nTurn it off anyway?")
    if command == "fuel_solenoid" and value == "open":
        return "Open the fuel solenoid?"
    if command == "fuel_servo" and value is not None and value > 0:
        return f"Set the fuel servo to {value:g} %?"
    if command == "spark_pulse":
        return "Fire a spark pulse?"
    if command == "stop":
        return "Stop the engine and open the shutdown sequence?"
    return None  # emergency_stop y el resto: sin confirmación (acción inmediata)
