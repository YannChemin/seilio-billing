from __future__ import annotations

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMainWindow, QTabWidget

from seilio_billing.i18n import tr
from seilio_billing.icons import icon_path
from seilio_billing.models import Company
from seilio_billing.ui import fit_to_screen
from seilio_billing.ui.clients_tab import ClientsTab
from seilio_billing.ui.dashboard_tab import DashboardTab
from seilio_billing.ui.declarations_tab import DeclarationsTab
from seilio_billing.ui.documents_tab import DocumentsTab
from seilio_billing.ui.ledger_tab import LedgerTab
from seilio_billing.ui.settings_tab import SettingsTab

TABS = [
    ("dashboard", "tabs.dashboard", DashboardTab),
    ("clients", "tabs.clients", ClientsTab),
    ("documents", "tabs.documents", DocumentsTab),
    ("ledger", "tabs.ledger", LedgerTab),
    ("declarations", "tabs.declarations", DeclarationsTab),
    ("settings", "tabs.settings", SettingsTab),
]


class MainWindow(QMainWindow):
    def __init__(self, session_factory):
        super().__init__()
        probe_session = session_factory()
        company = probe_session.query(Company).first()
        company_name = (company.name if company and company.name else "Seilio Douar E.I.")
        probe_session.close()
        self.setWindowTitle(tr("app.title", company=company_name))
        self.resize(fit_to_screen(1100, 700))
        app_icon = icon_path("app")
        if app_icon.exists():
            self.setWindowIcon(QIcon(str(app_icon)))

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self._instances = {}
        for key, label_key, cls in TABS:
            widget = cls(session_factory)
            label = tr(label_key)
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
