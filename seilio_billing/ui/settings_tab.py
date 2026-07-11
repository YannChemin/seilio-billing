from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
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
    QFileDialog,
    QScrollArea,
    QComboBox,
)

from seilio_billing.i18n import tr, current_language, set_saved_language
from seilio_billing.models import Company
from seilio_billing.pa_connector import PA_REGISTRATION_CHECKLIST
from seilio_billing.tiime_export import DEFAULT_TIIME_DIR

_LANGUAGES = [
    ("en", "settings.language.en"),
    ("fr", "settings.language.fr"),
    ("br", "settings.language.br"),
    ("gallo", "settings.language.gallo"),
    ("cy", "settings.language.cy"),
]


class SettingsTab(QWidget):
    def __init__(self, session_factory):
        super().__init__()
        self.session_factory = session_factory
        self.session = session_factory()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)

        company_box = QGroupBox(tr("settings.box.company"))
        form = QFormLayout(company_box)
        self.fields = {}
        for key, label_key in [
            ("name", "settings.field.name"),
            ("address_line", "settings.field.address"),
            ("postal_code", "settings.field.postal_code"),
            ("city", "settings.field.city"),
            ("country", "settings.field.country"),
            ("siret", "settings.field.siret"),
            ("vat_number", "settings.field.vat"),
            ("email", "settings.field.email"),
            ("phone", "settings.field.phone"),
            ("iban", "settings.field.iban"),
            ("bic", "settings.field.bic"),
            ("bank_name", "settings.field.bank_name"),
        ]:
            edit = QLineEdit()
            form.addRow(tr(label_key), edit)
            self.fields[key] = edit
        save_btn = QPushButton(tr("settings.btn.save_company"))
        save_btn.clicked.connect(self._save_company)
        form.addRow(save_btn)
        layout.addWidget(company_box)

        tiime_box = QGroupBox(tr("settings.box.tiime"))
        tiime_layout = QVBoxLayout(tiime_box)
        explain = QLabel(tr("settings.tiime.explain"))
        explain.setWordWrap(True)
        tiime_layout.addWidget(explain)

        row = QHBoxLayout()
        self.tiime_dir_edit = QLineEdit()
        self.tiime_dir_edit.setPlaceholderText(str(DEFAULT_TIIME_DIR))
        browse_btn = QPushButton(tr("settings.tiime.browse"))
        browse_btn.clicked.connect(self._browse_tiime_dir)
        open_btn = QPushButton(tr("settings.tiime.open"))
        open_btn.clicked.connect(self._open_tiime_dir)
        row.addWidget(self.tiime_dir_edit, stretch=1)
        row.addWidget(browse_btn)
        row.addWidget(open_btn)
        tiime_layout.addLayout(row)
        layout.addWidget(tiime_box)

        pa_box = QGroupBox(tr("settings.box.pa"))
        pa_layout = QVBoxLayout(pa_box)
        pa_intro = QLabel(tr("settings.pa.intro"))
        pa_intro.setWordWrap(True)
        pa_layout.addWidget(pa_intro)
        for step in PA_REGISTRATION_CHECKLIST:
            item_label = QLabel(f"• {step}")
            item_label.setWordWrap(True)
            pa_layout.addWidget(item_label)
        layout.addWidget(pa_box)

        language_box = QGroupBox(tr("settings.box.language"))
        language_layout = QFormLayout(language_box)
        self.language_combo = QComboBox()
        for code, label_key in _LANGUAGES:
            self.language_combo.addItem(tr(label_key), code)
        idx = self.language_combo.findData(current_language())
        if idx >= 0:
            self.language_combo.setCurrentIndex(idx)
        self.language_combo.currentIndexChanged.connect(self._save_language)
        language_layout.addRow(tr("settings.language.label"), self.language_combo)
        note = QLabel(tr("settings.language.restart_note"))
        note.setWordWrap(True)
        language_layout.addRow(note)
        layout.addWidget(language_box)

        layout.addStretch()

        self.refresh()

    def refresh(self):
        company = self.session.query(Company).first()
        if company is None:
            return
        for key, edit in self.fields.items():
            edit.setText(getattr(company, key) or "")
        self.tiime_dir_edit.setText(company.tiime_export_dir or "")

    def _save_company(self):
        company = self.session.query(Company).first()
        if company is None:
            company = Company()
            self.session.add(company)
        for key, edit in self.fields.items():
            setattr(company, key, edit.text().strip())
        company.tiime_export_dir = self.tiime_dir_edit.text().strip()
        self.session.commit()
        QMessageBox.information(self, tr("settings.saved.title"), tr("settings.saved.body"))

    def _browse_tiime_dir(self):
        start_dir = self.tiime_dir_edit.text().strip() or str(DEFAULT_TIIME_DIR)
        path = QFileDialog.getExistingDirectory(self, tr("settings.tiime.choose_dialog"), start_dir)
        if path:
            self.tiime_dir_edit.setText(path)

    def _open_tiime_dir(self):
        path = Path(self.tiime_dir_edit.text().strip() or str(DEFAULT_TIIME_DIR))
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _save_language(self):
        code = self.language_combo.currentData()
        if code:
            set_saved_language(code)
