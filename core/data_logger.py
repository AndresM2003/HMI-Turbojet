import csv
import os
from datetime import datetime

from core.telemetry_protocol import SENSOR_FIELDS


class DataLogger:
    def __init__(self, logs_dir: str = "logs"):
        self._logs_dir = logs_dir
        self._file = None
        self._writer = None
        self._filepath = ""
        os.makedirs(self._logs_dir, exist_ok=True)

    @property
    def filepath(self) -> str:
        return self._filepath

    @property
    def is_active(self) -> bool:
        return self._file is not None and not self._file.closed

    def start(self) -> bool:
        if self.is_active:
            return True

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._filepath = os.path.join(self._logs_dir, f"session_{timestamp}.csv")
        try:
            self._file = open(self._filepath, "w", newline="", encoding="utf-8")
        except OSError as error:
            self._file = None
            raise OSError(f"Could not open telemetry log {self._filepath}: {error}") from error

        self._writer = csv.writer(self._file)
        self._writer.writerow(["timestamp", "elapsed_s", "sequence", *SENSOR_FIELDS])
        self._file.flush()
        return True

    def stop(self) -> None:
        if self._file is None:
            return
        try:
            self._file.flush()
            self._file.close()
        finally:
            self._file = None
            self._writer = None

    def log(self, elapsed_s: float, telemetry: dict) -> None:
        if not self.is_active or self._writer is None:
            return
        sensors = telemetry["sensors"]
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            f"{elapsed_s:.3f}",
            telemetry["sequence"],
        ]
        row.extend("" if sensors[field] is None else sensors[field] for field in SENSOR_FIELDS)
        try:
            self._writer.writerow(row)
            self._file.flush()
        except OSError:
            self.stop()
            raise
