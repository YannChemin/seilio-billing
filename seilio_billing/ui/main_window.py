from __future__ import annotations

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMainWindow, QTabWidget

from seilio_billing.icons import icon_path
from seilio_billing.ui.clients_tab import ClientsTab
from seilio_billing.ui.dashboard_tab import DashboardTab
from seilio_billing.ui.declarations_tab import DeclarationsTab
from seilio_billing.ui.documents_tab import DocumentsTab
from seilio_billing.ui.facturx_tab import FacturXTab
from seilio_billing.ui.import_tab import ImportTab
from seilio_billing.ui.ledger_tab import LedgerTab
from seilio_billing.ui.settings_tab import SettingsTab

TABS = [
    ("dashboard", "Dashboard", DashboardTab),
    ("clients", "Clients", ClientsTab),
    ("documents", "Documents", DocumentsTab),
    ("ledger", "Livre de recettes", LedgerTab),
    ("import", "Import LaTeX", ImportTab),
    ("facturx", "Factur-X export", FacturXTab),
    ("declarations", "Declarations", DeclarationsTab),
    ("settings", "Settings", SettingsTab),
]


class MainWindow(QMainWindow):
    def __init__(self, session_factory):
        super().__init__()
        self.setWindowTitle("Seilio Billing — Seilio Douar E.I.")
        self.resize(1100, 700)
        app_icon = icon_path("app")
        if app_icon.exists():
            self.setWindowIcon(QIcon(str(app_icon)))

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self._instances = {}
        for key, label, cls in TABS:
            if key == "import":
                widget = cls(session_factory, on_change=self._refresh_all)
            else:
                widget = cls(session_factory)
            icon_file = icon_path(key)
            if icon_file.exists():
                self.tabs.addTab(widget, QIcon(str(icon_file)), label)
            else:
                self.tabs.addTab(widget, label)
            self._instances[key] = widget

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int):
        widget = self.tabs.widget(index)
        if hasattr(widget, "refresh"):
            widget.refresh()

    def _refresh_all(self):
        for widget in self._instances.values():
            if hasattr(widget, "refresh"):
                widget.refresh()
