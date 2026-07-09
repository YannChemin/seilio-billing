from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QFormLayout,
    QPushButton,
    QLabel,
    QMessageBox,
    QGroupBox,
)

from seilio_billing.models import Company
from seilio_billing.pa_connector import PA_REGISTRATION_CHECKLIST, ManualPAConnector

EXPORT_DIR = Path.home() / ".local" / "share" / "seilio-billing" / "pa_export"
IMPORT_DIR = Path.home() / ".local" / "share" / "seilio-billing" / "pa_import"


class SettingsTab(QWidget):
    def __init__(self, session_factory):
        super().__init__()
        self.session_factory = session_factory
        self.session = session_factory()

        layout = QVBoxLayout(self)

        company_box = QGroupBox("Company identity")
        form = QFormLayout(company_box)
        self.fields = {}
        for key, label in [
            ("name", "Name"),
            ("address_line", "Address"),
            ("postal_code", "Postal code"),
            ("city", "City"),
            ("country", "Country"),
            ("siret", "SIRET"),
            ("vat_number", "VAT number"),
            ("email", "Email"),
            ("phone", "Phone"),
            ("iban", "IBAN"),
            ("bic", "BIC"),
            ("bank_name", "Bank name"),
        ]:
            edit = QLineEdit()
            form.addRow(label, edit)
            self.fields[key] = edit
        save_btn = QPushButton("Save company info")
        save_btn.clicked.connect(self._save_company)
        form.addRow(save_btn)
        layout.addWidget(company_box)

        pa_box = QGroupBox("Plateforme Agréée (PA / e-invoicing) setup")
        pa_layout = QVBoxLayout(pa_box)
        pa_layout.addWidget(
            QLabel(
                "Reception of e-invoices via an accredited platform is mandatory "
                "from 1 Sept 2026; issuance from 1 Sept 2027. This app cannot itself "
                "be a PA (that needs DGFiP accreditation) — pick one and wire it in:"
            )
        )
        for step in PA_REGISTRATION_CHECKLIST:
            item_label = QLabel(f"• {step}")
            item_label.setWordWrap(True)
            pa_layout.addWidget(item_label)

        row = QHBoxLayout()
        open_export_btn = QPushButton("Open PA export folder")
        open_export_btn.clicked.connect(self._prepare_folders)
        row.addWidget(open_export_btn)
        row.addStretch()
        pa_layout.addLayout(row)
        self.pa_status_label = QLabel(f"Export folder: {EXPORT_DIR}\nImport folder: {IMPORT_DIR}")
        pa_layout.addWidget(self.pa_status_label)

        layout.addWidget(pa_box)
        layout.addStretch()

        self.refresh()

    def refresh(self):
        company = self.session.query(Company).first()
        if company is None:
            return
        for key, edit in self.fields.items():
            edit.setText(getattr(company, key) or "")

    def _save_company(self):
        company = self.session.query(Company).first()
        if company is None:
            company = Company()
            self.session.add(company)
        for key, edit in self.fields.items():
            setattr(company, key, edit.text().strip())
        self.session.commit()
        QMessageBox.information(self, "Saved", "Company info updated.")

    def _prepare_folders(self):
        ManualPAConnector(EXPORT_DIR, IMPORT_DIR)
        QMessageBox.information(
            self,
            "Folders ready",
            f"Export folder ready at:\n{EXPORT_DIR}\n\nImport folder ready at:\n{IMPORT_DIR}",
        )
