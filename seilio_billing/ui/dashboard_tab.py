from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from seilio_billing.i18n import tr
from seilio_billing.models import Company, Document, DocumentStatus, LedgerEntry
from seilio_billing.ui.declarations_tab import PLAFOND_SERVICES
from seilio_billing.ui.document_wizard import DocumentWizard


class DashboardTab(QWidget):
    def __init__(self, session_factory):
        super().__init__()
        self.session_factory = session_factory
        self.session = session_factory()

        layout = QVBoxLayout(self)

        header_row = QHBoxLayout()

        text_col = QVBoxLayout()
        self.heading_label = QLabel("")
        self.heading_label.setWordWrap(True)
        heading_font = QFont()
        heading_font.setBold(True)
        heading_font.setPointSize(heading_font.pointSize() + 6)
        self.heading_label.setFont(heading_font)
        text_col.addWidget(self.heading_label)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        text_col.addWidget(self.summary_label)

        header_row.addLayout(text_col, stretch=1)

        new_doc_btn = QPushButton(tr("dashboard.new_document"))
        new_doc_btn.setMinimumHeight(48)
        new_doc_btn.setStyleSheet("font-size: 16pt; font-weight: bold; padding: 8px 20px;")
        new_doc_btn.clicked.connect(self._new_document)
        header_row.addWidget(new_doc_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        header_row.setContentsMargins(0, 0, 24, 0)
        layout.addLayout(header_row)

        refresh_btn = QPushButton(tr("dashboard.refresh"))
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)
        layout.addStretch()

        self.refresh()

    def _new_document(self):
        wizard = DocumentWizard(self.session, document=None, parent=self)
        wizard.exec()
        self.refresh()

    def refresh(self):
        year = dt.date.today().year
        ytd = sum(
            e.amount for e in self.session.query(LedgerEntry).all() if e.date.year == year
        )
        drafts = self.session.query(Document).filter(Document.status == DocumentStatus.draft).count()
        sent_unpaid = self.session.query(Document).filter(Document.status == DocumentStatus.sent).count()
        pct = (ytd / PLAFOND_SERVICES) * 100 if PLAFOND_SERVICES else 0

        company = self.session.query(Company).first()
        company_name = company.name if company and company.name else "Seilio Douar E.I."

        self.heading_label.setText(tr('dashboard.heading', company=company_name))
        self.summary_label.setText(
            f"<p>{tr('dashboard.revenue', year=year, ytd=ytd, pct=pct, ceiling=PLAFOND_SERVICES)}</p>"
            f"<p>{tr('dashboard.drafts', n=drafts)}</p>"
            f"<p>{tr('dashboard.sent_unpaid', n=sent_unpaid)}</p>"
        )
