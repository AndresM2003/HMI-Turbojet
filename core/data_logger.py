# core/data_logger.py

import csv
import os
from datetime import datetime


class DataLogger:
    def __init__(self, logs_dir: str = "logs"):
        self._logs_dir  = logs_dir
        self._file      = None
        self._writer    = None
        self._active    = False
        self._filepath  = ""

        os.makedirs(self._logs_dir, exist_ok=True)

    # =====================================================
    # API pública
    # =====================================================
    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def filepath(self) -> str:
        return self._filepath

    def start(self) -> bool:
        """
        Abre un nuevo archivo CSV para la sesión actual.
        Retorna True si se inició correctamente.
        """
        if self._active:
            return True

        try:
            timestamp       = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._filepath  = os.path.join(self._logs_dir, f"session_{timestamp}.csv")
            self._file      = open(self._filepath, "w", newline="", encoding="utf-8")
            self._writer    = csv.writer(self._file)

            # Encabezado
            self._writer.writerow([
                "timestamp",
                "elapsed_s",
                "rpm",
                "egt_c",
                "fuel_flow_lmin",
                "pressure_bar",
            ])
            self._file.flush()
            self._active = True
            return True

        except OSError as e:
            print(f"[DataLogger] Error opening file: {e}")
            self._active = False
            return False

    def stop(self) -> None:
        """Cierra el archivo CSV de la sesión actual."""
        if not self._active:
            return

        try:
            if self._file:
                self._file.flush()
                self._file.close()
        except OSError as e:
            print(f"[DataLogger] Error closing file: {e}")
        finally:
            self._file   = None
            self._writer = None
            self._active = False

    def log(self, elapsed_s: float, data: dict) -> None:
        """
        Escribe una fila en el CSV.
        Solo actúa si el logger está activo.
        """
        if not self._active or self._writer is None:
            return

        try:
            self._writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                f"{elapsed_s:.3f}",
                f"{data.get('rpm', 0):.0f}",
                f"{data.get('egt', 0):.1f}",
                f"{data.get('fuel_flow', 0):.1f}",
                f"{data.get('pressure', 0):.2f}",
            ])
            self._file.flush()

        except OSError as e:
            print(f"[DataLogger] Error writing row: {e}")
            self.stop()