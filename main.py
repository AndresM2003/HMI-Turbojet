import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from core.demo_telemetry import demo_message
from core.telemetry_protocol import parse_telemetry_frame
from ui.command_center import CommandCenter
from ui.main_window import MainWindow
from ui.shutdown_window import ShutdownWindow
from ui.startup_window import StartupWindow


class AppController:
    """Flujo: Startup → Main → (Shutdown ⇄ Main) → cerrar sesión → Startup.

    Vista previa (sin ESP32): abre la interfaz sin conexión, vacía o con datos simulados.
    """

    def __init__(self, app: QApplication):
        self.app = app
        self.commands = CommandCenter()
        self.startup: StartupWindow | None = None
        self.main: MainWindow | None = None
        self.shutdown: ShutdownWindow | None = None
        self._demo_timer: QTimer | None = None
        self._demo_started = 0.0
        self._demo_sequence = 0
        app.aboutToQuit.connect(self._cleanup)

    def show_startup(self):
        self.startup = StartupWindow(commands=self.commands)
        self.startup.session_ready.connect(self._enter_main)
        self.startup.preview_requested.connect(self._open_preview)
        self.startup.show()

    def _enter_main(self, reader, logger, started_at):
        self.main = MainWindow(commands=self.commands)
        self.main.attach_session(reader, logger, started_at)
        self.main.shutdown_requested.connect(self._open_shutdown)
        self.main.show()
        self.startup = None

    # ---------- vista previa ----------
    def _open_preview(self, simulated: bool):
        self.commands.set_preview(True)
        self.main = MainWindow(commands=self.commands)
        self.main.setWindowTitle("Turbojet Control System — PREVIEW (no hardware)")
        label = "COM: PREVIEW — SIMULATED DATA" if simulated else "COM: PREVIEW — NO DATA"
        self.main.com_label.setText(label)
        self.main.com_label.setMinimumWidth(190)
        self.main.com_label.setStyleSheet("font-size: 9px; font-weight: bold; color: #8A5A00;")
        self.main.shutdown_requested.connect(self._open_shutdown)
        self.main.show()
        if simulated:
            self._demo_started = time.monotonic()
            self._demo_sequence = 0
            self._demo_timer = QTimer()
            self._demo_timer.timeout.connect(self._push_demo_frame)
            self._demo_timer.start(250)
        if self.startup is not None:
            self.startup.close()
            self.startup = None

    def _push_demo_frame(self):
        self._demo_sequence += 1
        message = demo_message(self._demo_sequence, time.monotonic() - self._demo_started)
        telemetry = parse_telemetry_frame((json.dumps(message) + "\n").encode("utf-8"))
        if self.main is not None:
            self.main._on_telemetry(telemetry)
        if self.shutdown is not None:
            self.shutdown._on_telemetry(telemetry)

    # ---------- apagado ----------
    def _open_shutdown(self):
        self.shutdown = ShutdownWindow(self.main.reader, commands=self.commands)
        self.shutdown.back_requested.connect(self._back_to_main)
        self.shutdown.session_closed.connect(self._close_session)
        self.main.hide()
        self.shutdown.show()

    def _back_to_main(self):
        self.main.show()
        self.shutdown.dismiss()
        self.shutdown = None

    def _close_session(self):
        self._stop_demo()
        self.commands.set_preview(False)
        self.commands.set_reader(None)
        self.commands.reset()
        self.show_startup()  # primero la nueva ventana, para no quedarse sin ventanas visibles
        if self.shutdown is not None:
            self.shutdown.dismiss()
            self.shutdown = None
        self.main.close()    # MainWindow.closeEvent detiene el lector serial y el logger
        self.main = None

    def _stop_demo(self):
        if self._demo_timer is not None:
            self._demo_timer.stop()
            self._demo_timer = None

    def _cleanup(self):
        self._stop_demo()
        if self.shutdown is not None:
            self.shutdown.dismiss()
        if self.main is not None:
            self.main.close()
            if self.main.reader is not None:
                self.main.reader.wait(3000)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    controller = AppController(app)
    if "--demo" in sys.argv:        # python main.py --demo     → interfaz con datos simulados
        controller._open_preview(True)
    elif "--preview" in sys.argv:   # python main.py --preview  → interfaz vacía
        controller._open_preview(False)
    else:
        controller.show_startup()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
