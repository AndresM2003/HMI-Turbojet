# Paleta clara tipo HMI industrial (ISA-101): fondo gris claro; el color solo indica estado.
STATE_COLORS = {
    "OK": "#1E7B45",
    "WAIT": "#A86B00",
    "FAULT": "#B3261E",
    "MANUAL": "#1F6FA8",
    "PENDING": "#7B868D",
}

WINDOW_STYLE = """
    QWidget { background: #E4E7E9; color: #1F2A30; }
    QFrame#card { background: #F7F9FA; border: 1px solid #B3BBC1; }
    QLabel { background: transparent; }
    QPushButton, QComboBox {
        background: #EEF0F2; border: 1px solid #9AA4AB; padding: 6px 10px; color: #1F2A30;
    }
    QPushButton:hover { border-color: #1F6FA8; }
    QPushButton:disabled { color: #7B868D; border-color: #AEB6BC; }
    QComboBox QAbstractItemView { background: #F6F7F8; color: #1F2A30; selection-background-color: #BFD6E6; }
    QProgressBar { background: #EEF0F2; border: 0; height: 8px; }
    QProgressBar::chunk { background: #1F6FA8; }
"""


# Color de acento (franja superior) de cada tarjeta, según su categoría.
_ACCENTS = (
    (("alarm",), "#C0392B"),
    (("log",), "#5B7C99"),
    (("trend",), "#7B5EA7"),
    (("gas", "fuel", "safety", "pipeline"), "#C98A1B"),
    (("temp", "thermal", "derived"), "#D9822B"),
    (("control", "status", "ignition", "pre-check", "shutdown"), "#2E8B57"),
    (("process", "rpm", "sequence"), "#1F6FA8"),
)


def accent_for_title(title: str) -> str:
    lowered = title.lower()
    for words, color in _ACCENTS:
        if any(word in lowered for word in words):
            return color
    return "#5B7C99"
