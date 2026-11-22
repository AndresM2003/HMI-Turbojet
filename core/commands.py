"""Protocolo de comandos HMI → ESP32 (v1). Una línea JSON terminada en \\n.

Comando (HMI → ESP32):
    {"version":1,"type":"command","id":12,"command":"oil_pump","value":"on"}
Confirmación (ESP32 → HMI), obligatoria para dar el comando por ejecutado:
    {"version":1,"type":"command_ack","id":12,"ok":true,"message":"optional text"}

Comandos y valores:
    oil_pump       "on" | "off"
    fuel_solenoid  "open" | "close"
    fuel_servo     número 0–100 (% de apertura)
    control_mode   "auto" | "manual"
    spark_pulse, stop, emergency_stop   (sin valor)
El firmware arranca en "auto" y solo acepta oil_pump, fuel_solenoid, fuel_servo y spark_pulse mientras
esté en "manual". stop, emergency_stop y control_mode se aceptan siempre.
El firmware decide la duración del pulso de bujía y cómo ejecuta stop / emergency_stop.
"""

import json
import math

MAX_ACK_BYTES = 1024
SERVO = "fuel_servo"
VALUE_CHOICES = {
    "oil_pump": ("on", "off"),
    "fuel_solenoid": ("open", "close"),
    "control_mode": ("auto", "manual"),
}
NO_VALUE_COMMANDS = ("spark_pulse", "stop", "emergency_stop")


class CommandProtocolError(ValueError):
    pass


def validate_command(command: str, value=None):
    if command in VALUE_CHOICES:
        if value not in VALUE_CHOICES[command]:
            raise CommandProtocolError(f"{command}: value must be one of {VALUE_CHOICES[command]}")
    elif command == SERVO:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise CommandProtocolError("fuel_servo: value must be a number")
        if not 0 <= value <= 100:
            raise CommandProtocolError("fuel_servo: value must be between 0 and 100")
    elif command in NO_VALUE_COMMANDS:
        if value is not None:
            raise CommandProtocolError(f"{command} takes no value")
    else:
        raise CommandProtocolError(f"unknown command: {command}")


def build_command_frame(command_id: int, command: str, value=None) -> bytes:
    if isinstance(command_id, bool) or not isinstance(command_id, int) or command_id < 0:
        raise CommandProtocolError("id must be a non-negative integer")
    validate_command(command, value)
    message = {"version": 1, "type": "command", "id": command_id, "command": command}
    if value is not None:
        message["value"] = value
    return (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")


def parse_command_ack(frame: bytes) -> dict:
    if len(frame) > MAX_ACK_BYTES:
        raise CommandProtocolError("ack exceeds the size limit")
    try:
        message = json.loads(frame.decode("utf-8").strip())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CommandProtocolError(f"invalid ack JSON: {error}") from error
    if not isinstance(message, dict) or message.get("version") != 1 or message.get("type") != "command_ack":
        raise CommandProtocolError("unsupported ack version or type")
    ack_id, ok, text = message.get("id"), message.get("ok"), message.get("message", "")
    if isinstance(ack_id, bool) or not isinstance(ack_id, int) or ack_id < 0:
        raise CommandProtocolError("ack id must be a non-negative integer")
    if not isinstance(ok, bool):
        raise CommandProtocolError("ack ok must be boolean")
    if not isinstance(text, str):
        raise CommandProtocolError("ack message must be a string")
    return {"id": ack_id, "ok": ok, "message": text}
