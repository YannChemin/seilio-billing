"""Follow the OS light/dark color scheme.

Qt6's native platform theme integration doesn't reliably kick in on every
Linux desktop (depends on the xdg-desktop-portal / GTK theme plugin being
present), so we explicitly force the Fusion style and build the palette
from Qt's own color-scheme signal, which Qt derives from the desktop
portal regardless of style. Reapplies live if the user flips their OS theme
while the app is running.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory


def _dark_palette() -> QPalette:
    palette = QPalette()
    window = QColor(37, 37, 38)
    base = QColor(30, 30, 30)
    text = QColor(220, 220, 220)
    disabled_text = QColor(127, 127, 127)
    highlight = QColor(58, 110, 165)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, window)
    palette.setColor(QPalette.ColorRole.ToolTipBase, text)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, window)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("red"))
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("black"))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    return palette


def _apply(app: QApplication) -> None:
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        app.setPalette(_dark_palette())
    else:
        app.setPalette(QApplication.style().standardPalette())


def follow_os_theme(app: QApplication) -> None:
    """Force the Fusion style (consistent palette support across desktops)
    and keep the app's palette in sync with the OS light/dark setting."""
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")
    _apply(app)
    app.styleHints().colorSchemeChanged.connect(lambda _scheme: _apply(app))
