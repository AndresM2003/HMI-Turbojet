"""Verifica que la ESP32 manda tramas válidas, sin abrir el HMI.

Uso:
    python tools/check_esp32.py --list                       # lista los puertos serial
    python tools/check_esp32.py COM5 --seconds 15            # escucha el puerto en vivo
    python tools/check_esp32.py --file captura.txt           # analiza texto copiado del monitor serial
    echo {...} | python tools/check_esp32.py --file -        # una trama pegada por stdin

Usa el mismo validador que el HMI (core/telemetry_protocol.py y core/commands.py).
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.commands import CommandProtocolError, parse_command_ack
from core.telemetry_protocol import MAX_FRAME_BYTES, SENSOR_FIELDS, TelemetryProtocolError, parse_telemetry_frame


@dataclass
class Report:
    ok: int = 0
    invalid: int = 0
    ignored: int = 0
    acks: int = 0
    duplicates: int = 0
    gaps: int = 0
    lost_frames: int = 0
    restarts: int = 0
    null_counts: dict = field(default_factory=lambda: {name: 0 for name in SENSOR_FIELDS})
    alarms: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    first_time: float | None = None
    last_time: float | None = None

    @property
    def rate_hz(self) -> float | None:
        if self.first_time is None or self.last_time is None or self.ok < 2 or self.last_time <= self.first_time:
            return None
        return (self.ok - 1) / (self.last_time - self.first_time)


def analyze(lines) -> Report:
    """lines: iterable de (instante_en_s | None, bytes). Cada elemento es una línea recibida."""
    report = Report()
    last_sequence = None
    for number, (stamp, raw) in enumerate(lines, start=1):
        if not raw.endswith(b"\n"):
            raw += b"\n"
        if not raw.strip():
            continue
        if not raw.lstrip().startswith(b"{"):
            report.ignored += 1  # el HMI ignora estas líneas (log de depuración)
            continue
        if b'"command_ack"' in raw:
            try:
                parse_command_ack(raw)
                report.acks += 1
            except CommandProtocolError as error:
                report.invalid += 1
                report.errors.append((number, f"ack: {error}"))
            continue
        try:
            frame = parse_telemetry_frame(raw)
        except TelemetryProtocolError as error:
            report.invalid += 1
            if len(report.errors) < 10:
                report.errors.append((number, str(error)))
            continue
        report.ok += 1
        if stamp is not None:
            report.first_time = stamp if report.first_time is None else report.first_time
            report.last_time = stamp
        sequence = frame["sequence"]
        if last_sequence is not None:
            if sequence == last_sequence:
                report.duplicates += 1
            elif sequence < last_sequence:
                report.restarts += 1
            elif sequence > last_sequence + 1:
                report.gaps += 1
                report.lost_frames += sequence - last_sequence - 1
        last_sequence = sequence
        for name, value in frame["sensors"].items():
            if value is None:
                report.null_counts[name] += 1
        for alarm in frame["alarms"]:
            report.alarms[alarm["code"]] = alarm["severity"]
    return report


def print_report(report: Report, seconds: float | None = None) -> bool:
    total = report.ok + report.invalid
    print(f"\nValid telemetry frames : {report.ok}")
    print(f"Invalid frames         : {report.invalid}")
    print(f"Ignored lines (logs)   : {report.ignored}")
    print(f"Command ACKs           : {report.acks}")
    if report.rate_hz is not None:
        print(f"Measured rate          : {report.rate_hz:.2f} Hz")
    print(f"Sequence gaps / lost   : {report.gaps} / {report.lost_frames}")
    print(f"Sequence restarts      : {report.restarts}   Duplicates: {report.duplicates}")
    nulls = {name: count for name, count in report.null_counts.items() if count}
    print("Sensors sent as null   : " + (", ".join(f"{k} ({v}×)" for k, v in nulls.items()) or "none"))
    print("Alarms seen            : " + (", ".join(f"{k} [{v}]" for k, v in report.alarms.items()) or "none"))
    for number, message in report.errors[:5]:
        print(f"  line {number}: {message}")
    problems = []
    if report.ok == 0:
        problems.append("no valid telemetry frame received")
    if report.invalid:
        problems.append(f"{report.invalid} invalid frame(s)")
    if report.gaps or report.restarts:
        problems.append("sequence gaps or restarts (lost frames or ESP32 reboot)")
    if report.rate_hz is not None and not 0.5 <= report.rate_hz <= 10:
        problems.append(f"rate {report.rate_hz:.2f} Hz is outside the recommended 0.5–10 Hz")
    print("\nRESULT: " + ("PASS" if not problems and total else "CHECK → " + "; ".join(problems)))
    return not problems and total > 0


def _list_ports():
    from serial.tools import list_ports
    for port in list_ports.comports():
        ids = f"{port.vid:04X}:{port.pid:04X}" if port.vid is not None else "----:----"
        print(f"{port.device:<12} {ids}  {port.description}")


def _live(port: str, baud: int, seconds: float) -> Report:
    import serial
    connection = serial.Serial()
    connection.port, connection.baudrate, connection.timeout = port, baud, 0.5
    connection.dtr = connection.rts = False  # igual que el HMI: no reiniciar la ESP32 al abrir
    connection.open()
    connection.reset_input_buffer()
    collected, end = [], time.monotonic() + seconds
    print(f"Listening on {port} at {baud} baud for {seconds:.0f} s...")
    try:
        while time.monotonic() < end:
            raw = connection.readline(MAX_FRAME_BYTES + 1)
            if raw:
                collected.append((time.monotonic(), raw))
    finally:
        connection.close()
    return analyze(collected)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("port", nargs="?", help="serial port, e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--file", help="analyze a text capture instead of a live port ('-' = stdin)")
    parser.add_argument("--list", action="store_true", help="list serial ports and exit")
    args = parser.parse_args(argv)
    if args.list:
        _list_ports()
        return 0
    if args.file:
        source = sys.stdin.buffer if args.file == "-" else open(args.file, "rb")
        with source:
            report = analyze((None, line) for line in source)
    elif args.port:
        report = _live(args.port, args.baud, args.seconds)
    else:
        parser.error("give a port, --file, or --list")
    return 0 if print_report(report) else 1


if __name__ == "__main__":
    sys.exit(main())
