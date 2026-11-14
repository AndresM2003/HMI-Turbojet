# main.py

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from ui.startup_window import StartupWindow
from ui.main_window import MainWindow
from com.dummy_data import DummyDataThread
from core.data_logger import DataLogger


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget {
            color: #1F2937;
        }
        QToolTip {
            color: #FFFFFF;
            background-color: #1F2937;
            border: 1px solid #475569;
            padding: 4px;
        }
    """)

    logger     = DataLogger(logs_dir="logs")
    logger.start()

    startup     = StartupWindow()
    main_window = None
    start_time  = time.time()

    data_thread = DummyDataThread()

    def handle_data(data):
        nonlocal main_window
        t = time.time() - start_time

        logger.log(t, data)

        if startup.isVisible():
            startup.update_data(data)

        if main_window is not None:
            main_window.update_ui(data, t)

    data_thread.data_updated.connect(handle_data)
    data_thread.start()

    startup.show()

    def on_startup_confirmed():
        nonlocal main_window
        startup.close()
        main_window = MainWindow()
        main_window.show()

    startup.startup_confirmed.connect(on_startup_confirmed)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()