from PyQt6.QtCore import QSize
from PyQt6.QtGui import QGuiApplication


def fit_to_screen(width: int, height: int, margin: int = 40) -> QSize:
    """Clamp a desired window size to the available screen geometry, so a
    window never opens larger than the screen (leaving a small margin for
    window decorations/taskbars)."""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return QSize(width, height)
    avail = screen.availableGeometry()
    return QSize(min(width, avail.width() - margin), min(height, avail.height() - margin))
