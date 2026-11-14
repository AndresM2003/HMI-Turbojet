import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    segoe_font = os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf"
    )
    if os.path.isfile(segoe_font):
        QFontDatabase.addApplicationFont(segoe_font)
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet("""
        QToolTip {
            color: #FFFFFF;
            background-color: #1F2937;
            border: 1px solid #475569;
            padding: 4px;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
