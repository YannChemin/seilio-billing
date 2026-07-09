from __future__ import annotations

import datetime as dt

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

from seilio_billing.models import Document, DocumentStatus, LedgerEntry
from seilio_billing.ui.declarations_tab import PLAFOND_SERVICES


class DashboardTab(QWidget):
    def __init__(self, session_factory):
        super().__init__()
        self.session_factory = session_factory
        self.session = session_factory()

        layout = QVBoxLayout(self)
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)
        layout.addStretch()

        self.refresh()

    def refresh(self):
        year = dt.date.today().year
        ytd = sum(
            e.amount for e in self.session.query(LedgerEntry).all() if e.date.year == year
        )
        drafts = self.session.query(Document).filter(Document.status == DocumentStatus.draft).count()
        sent_unpaid = self.session.query(Document).filter(Document.status == DocumentStatus.sent).count()
        pct = (ytd / PLAFOND_SERVICES) * 100 if PLAFOND_SERVICES else 0

        self.summary_label.setText(
            f"<h2>Seilio Douar E.I. — Dashboard</h2>"
            f"<p><b>Revenue encaissé {year}:</b> {ytd:.2f} EUR "
            f"({pct:.1f}% of the {PLAFOND_SERVICES:.0f} EUR services ceiling)</p>"
            f"<p><b>Drafts needing action:</b> {drafts}</p>"
            f"<p><b>Sent, awaiting payment:</b> {sent_unpaid}</p>"
        )
