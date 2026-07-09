from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QPushButton,
    QLabel,
    QFileDialog,
    QMessageBox,
)

from seilio_billing.models import Company, Document, DocumentType
from seilio_billing.facturx_export import generate_facturx_pdf


class FacturXTab(QWidget):
    def __init__(self, session_factory):
        super().__init__()
        self.session_factory = session_factory
        self.session = session_factory()

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Generate a Factur-X (EN16931) hybrid PDF+XML e-invoice for an invoice-type "
                "document. Ready for the 2027 issuance mandate once a Plateforme Agréée is wired up "
                "(see Settings)."
            )
        )

        row = QHBoxLayout()
        self.doc_combo = QComboBox()
        refresh_btn = QPushButton("Refresh list")
        refresh_btn.clicked.connect(self.refresh)
        generate_btn = QPushButton("Generate Factur-X PDF…")
        generate_btn.clicked.connect(self._generate)
        row.addWidget(self.doc_combo, stretch=1)
        row.addWidget(refresh_btn)
        row.addWidget(generate_btn)
        layout.addLayout(row)
        layout.addStretch()

        self.refresh()

    def refresh(self):
        self.doc_combo.clear()
        docs = (
            self.session.query(Document)
            .filter(Document.type == DocumentType.invoice)
            .order_by(Document.issue_date.desc())
            .all()
        )
        for d in docs:
            label = f"{d.number or d.id} — {d.client.name if d.client else '?'} — {d.issue_date.isoformat()} — {d.total():.2f} EUR"
            self.doc_combo.addItem(label, d.id)

    def _generate(self):
        doc_id = self.doc_combo.currentData()
        if doc_id is None:
            QMessageBox.information(self, "No invoice", "No invoice-type document available. Create one first.")
            return
        document = self.session.get(Document, doc_id)
        company = self.session.query(Company).first()
        if company is None:
            QMessageBox.warning(self, "No company", "Company identity is not set up (see Settings).")
            return

        default_name = f"facturx_{document.number or document.id}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Save Factur-X PDF", default_name, "PDF (*.pdf)")
        if not path:
            return
        try:
            pdf_bytes = generate_facturx_pdf(company, document)
        except Exception as exc:  # noqa: BLE001 - surface any generation/validation error to the user
            QMessageBox.critical(self, "Generation failed", str(exc))
            return
        with open(path, "wb") as f:
            f.write(pdf_bytes)
        QMessageBox.information(self, "Generated", f"Factur-X invoice written to {path}")
