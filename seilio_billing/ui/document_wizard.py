"""Step-by-step wizard to create/edit a quote, invoice or bill and issue it:
save -> render PDF -> (invoices) generate Factur-X -> deposit to the Tiime
folder, all in one flow with explanations and cross-checks at each step.
"""
from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QStackedWidget,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QLineEdit,
    QComboBox,
    QDateEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QDialogButtonBox,
    QFrame,
)

from seilio_billing.db import DATA_DIR
from seilio_billing.i18n import tr
from seilio_billing.models import Client, Company, Document, DocumentType, DocumentStatus, LineItem
from seilio_billing.numbering import generate_document_number
from seilio_billing.facturx_export import render_document_pdf, generate_facturx_pdf
from seilio_billing.tiime_export import deposit_to_tiime, tiime_dir_for
from seilio_billing.ui import fit_to_screen
from seilio_billing.ui.i18n import type_label, type_labels

DOCS_EXPORT_DIR = DATA_DIR / "documents"


def _line_columns():
    return [
        tr("wizard.line.description"), tr("wizard.line.qty"), tr("wizard.line.unit"),
        tr("wizard.line.rate"), tr("wizard.line.vat"), tr("wizard.line.amount"),
    ]


def _type_explanations():
    return {
        DocumentType.quote: tr("wizard.explain.quote"),
        DocumentType.invoice: tr("wizard.explain.invoice"),
        DocumentType.bill: tr("wizard.explain.bill"),
    }


def _step_titles():
    return [tr("wizard.step.type_client"), tr("wizard.step.line_items"), tr("wizard.step.review"), tr("wizard.step.issue")]


class QuickClientDialog(QDialog):
    """Add a client without leaving the wizard."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("wizard.newclient.title"))
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.postal_edit = QLineEdit()
        self.city_edit = QLineEdit()
        self.country_edit = QLineEdit(text="France")
        self.vat_edit = QLineEdit()
        self.email_edit = QLineEdit()
        layout.addRow(tr("wizard.newclient.name"), self.name_edit)
        layout.addRow(tr("wizard.newclient.address"), self.address_edit)
        layout.addRow(tr("wizard.newclient.postal_code"), self.postal_edit)
        layout.addRow(tr("wizard.newclient.city"), self.city_edit)
        layout.addRow(tr("wizard.newclient.country"), self.country_edit)
        layout.addRow(tr("wizard.newclient.vat"), self.vat_edit)
        layout.addRow(tr("wizard.newclient.email"), self.email_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, tr("wizard.err.missing_name.title"), tr("wizard.err.missing_name.body"))
            return
        self.accept()

    def to_client(self) -> Client:
        return Client(
            name=self.name_edit.text().strip(),
            address_line=self.address_edit.text().strip(),
            postal_code=self.postal_edit.text().strip(),
            city=self.city_edit.text().strip(),
            country=self.country_edit.text().strip(),
            vat_number=self.vat_edit.text().strip(),
            contact_email=self.email_edit.text().strip(),
        )


def _step_row(number: int, title: str) -> QListWidgetItem:
    item = QListWidgetItem(f"{number}.  {title}")
    return item


class DocumentWizard(QDialog):
    """4-step wizard: Type & client -> Line items -> Review & checks -> Issue."""

    def __init__(self, session, document: Document | None = None, parent=None):
        super().__init__(parent)
        self.session = session
        self.document = document
        self._is_new = document is None
        self._issued_result: dict | None = None

        self.setWindowTitle(
            tr("wizard.title.new") if self._is_new else tr("wizard.title.edit", number=document.number or document.id)
        )
        self.resize(fit_to_screen(880, 640))

        outer = QVBoxLayout(self)
        body = QHBoxLayout()
        outer.addLayout(body, stretch=1)

        self.stepper = QListWidget()
        self.stepper.setFixedWidth(170)
        self.stepper.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for i, title in enumerate(_step_titles()):
            self.stepper.addItem(_step_row(i + 1, title))
        self.stepper.currentRowChanged.connect(self._on_stepper_clicked)
        body.addWidget(self.stepper)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, stretch=1)

        self._build_step1()
        self._build_step2()
        self._build_step3()
        self._build_step4()

        nav = QHBoxLayout()
        self.back_btn = QPushButton(tr("wizard.nav.back"))
        self.back_btn.clicked.connect(self._go_back)
        self.next_btn = QPushButton(tr("wizard.nav.next"))
        self.next_btn.clicked.connect(self._go_next)
        self.cancel_btn = QPushButton(tr("wizard.nav.cancel"))
        self.cancel_btn.clicked.connect(self.reject)
        nav.addWidget(self.cancel_btn)
        nav.addStretch()
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        outer.addLayout(nav)

        self._reload_client_choices()
        if document is not None:
            self._load_from_document(document)
        else:
            self.type_edit.setCurrentIndex(0)
            self._update_type_explanation()

        self._max_reached = 0
        self._goto_step(0)

    # ---------------------------------------------------------- step 1 ----
    def _build_step1(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.step1_explain = QLabel()
        self.step1_explain.setWordWrap(True)
        layout.addWidget(self.step1_explain)

        form = QFormLayout()
        self.type_edit = QComboBox()
        self.type_edit.addItems(list(type_labels().keys()))
        self.type_edit.currentIndexChanged.connect(self._update_type_explanation)
        form.addRow(tr("wizard.step1.type"), self.type_edit)

        client_row = QHBoxLayout()
        self.client_edit = QComboBox()
        client_row.addWidget(self.client_edit, stretch=1)
        new_client_btn = QPushButton(tr("wizard.step1.new_client"))
        new_client_btn.clicked.connect(self._new_client)
        client_row.addWidget(new_client_btn)
        form.addRow(tr("wizard.step1.client"), client_row)

        self.date_edit = QDateEdit(calendarPopup=True)
        self.date_edit.setDate(dt.date.today())
        form.addRow(tr("wizard.step1.date"), self.date_edit)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(tr("wizard.step1.title_placeholder"))
        form.addRow(tr("wizard.step1.title"), self.title_edit)

        layout.addLayout(form)
        layout.addStretch()
        self.stack.addWidget(page)

    def _current_doc_type(self) -> DocumentType:
        return type_labels()[self.type_edit.currentText()]

    def _update_type_explanation(self, *_):
        doc_type = self._current_doc_type()
        self.step1_explain.setText(_type_explanations()[doc_type])

    def _new_client(self):
        dialog = QuickClientDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        client = dialog.to_client()
        self.session.add(client)
        self.session.commit()
        self._reload_client_choices()
        idx = self.client_edit.findData(client.id)
        if idx >= 0:
            self.client_edit.setCurrentIndex(idx)

    def _reload_client_choices(self):
        current = self.client_edit.currentData()
        self.client_edit.clear()
        for c in self.session.query(Client).order_by(Client.name).all():
            self.client_edit.addItem(c.name, c.id)
        if current is not None:
            idx = self.client_edit.findData(current)
            if idx >= 0:
                self.client_edit.setCurrentIndex(idx)

    # ---------------------------------------------------------- step 2 ----
    def _build_step2(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        explain = QLabel(tr("wizard.step2.explain"))
        explain.setWordWrap(True)
        layout.addWidget(explain)

        columns = _line_columns()
        self.line_table = QTableWidget(0, len(columns))
        self.line_table.setHorizontalHeaderLabels(columns)
        self.line_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.line_table.itemChanged.connect(self._recalc_total)
        layout.addWidget(self.line_table)

        line_btn_row = QHBoxLayout()
        add_line_btn = QPushButton(tr("wizard.step2.add_line"))
        add_line_btn.clicked.connect(self._add_line)
        remove_line_btn = QPushButton(tr("wizard.step2.remove_line"))
        remove_line_btn.clicked.connect(self._remove_line)
        line_btn_row.addWidget(add_line_btn)
        line_btn_row.addWidget(remove_line_btn)
        line_btn_row.addStretch()
        layout.addLayout(line_btn_row)

        self.total_label = QLabel(tr("wizard.step2.total", total=0.0))
        f = QFont()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 2)
        self.total_label.setFont(f)
        layout.addWidget(self.total_label)

        self.stack.addWidget(page)

    def _append_line_row(self, description="", qty=1.0, unit="", rate=0.0, vat=0.0):
        row = self.line_table.rowCount()
        self.line_table.insertRow(row)
        self.line_table.setItem(row, 0, QTableWidgetItem(description))
        self.line_table.setItem(row, 1, QTableWidgetItem(str(qty)))
        self.line_table.setItem(row, 2, QTableWidgetItem(unit))
        self.line_table.setItem(row, 3, QTableWidgetItem(str(rate)))
        self.line_table.setItem(row, 4, QTableWidgetItem(str(vat)))
        amount_item = QTableWidgetItem(f"{qty * rate:.2f}")
        amount_item.setFlags(amount_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.line_table.setItem(row, 5, amount_item)

    def _add_line(self):
        self._append_line_row()

    def _remove_line(self):
        rows = sorted({idx.row() for idx in self.line_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.line_table.removeRow(r)
        self._recalc_total()

    def _recalc_total(self, *_):
        total = 0.0
        self.line_table.blockSignals(True)
        for row in range(self.line_table.rowCount()):
            try:
                qty = float(self.line_table.item(row, 1).text() or 0)
                rate = float(self.line_table.item(row, 3).text() or 0)
            except (ValueError, AttributeError):
                qty, rate = 0.0, 0.0
            amount = qty * rate
            total += amount
            item = self.line_table.item(row, 5)
            if item is None:
                item = QTableWidgetItem()
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.line_table.setItem(row, 5, item)
            item.setText(f"{amount:.2f}")
        self.line_table.blockSignals(False)
        self.total_label.setText(tr("wizard.step2.total", total=total))

    def _collect_lines(self) -> list[dict]:
        lines = []
        for row in range(self.line_table.rowCount()):
            def cell(col, default=""):
                item = self.line_table.item(row, col)
                return item.text() if item else default

            try:
                qty = float(cell(1, "0") or 0)
                rate = float(cell(3, "0") or 0)
                vat = float(cell(4, "0") or 0)
            except ValueError:
                qty, rate, vat = 0.0, 0.0, 0.0
            lines.append(
                dict(description=cell(0), quantity=qty, unit=cell(2), unit_rate=rate, vat_rate=vat)
            )
        return lines

    # ---------------------------------------------------------- step 3 ----
    def _build_step3(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        explain = QLabel(tr("wizard.step3.explain"))
        explain.setWordWrap(True)
        layout.addWidget(explain)

        self.checks_label = QLabel()
        self.checks_label.setWordWrap(True)
        self.checks_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.checks_label)

        layout.addWidget(_hline())

        preview_btn = QPushButton(tr("wizard.step3.preview_btn"))
        preview_btn.clicked.connect(self._preview_pdf)
        layout.addWidget(preview_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

        self.stack.addWidget(page)

    def _run_checks(self) -> list[tuple[bool, str]]:
        checks = []
        company = self.session.query(Company).first()
        company_ok = bool(company and company.name and company.siret)
        checks.append((company_ok, tr("wizard.check.company")))

        client_id = self.client_edit.currentData()
        client = self.session.get(Client, client_id) if client_id else None
        client_ok = bool(client and client.name and (client.address_line or client.city))
        checks.append((client_ok, tr("wizard.check.client")))

        lines = self._collect_lines()
        has_lines = any(l["description"].strip() for l in lines)
        checks.append((has_lines, tr("wizard.check.has_lines")))

        total = sum(l["quantity"] * l["unit_rate"] for l in lines)
        checks.append((total > 0, tr("wizard.check.total_positive")))

        doc_type = self._current_doc_type()
        if doc_type == DocumentType.invoice:
            vat_note_ok = True  # franchise-en-base text is always included
            checks.append((vat_note_ok, tr("wizard.check.vat_note")))
            checks.append((bool(company and company.iban), tr("wizard.check.iban")))
        return checks

    def _refresh_checks(self):
        checks = self._run_checks()
        lines = []
        for ok, label in checks:
            mark = "✅" if ok else "⚠️"
            lines.append(f"{mark} {label}")
        self.checks_label.setText("<br>".join(lines))
        self._checks_all_ok = all(ok for ok, _ in checks)

    def _current_company(self) -> Company | None:
        return self.session.query(Company).first()

    def _build_preview_document(self) -> Document:
        """An in-memory (unpersisted) Document mirroring the current form,
        used for PDF preview without touching the database."""
        doc = Document(
            type=self._current_doc_type(),
            number=self.number_edit.text().strip() or "(auto)",
            issue_date=self.date_edit.date().toPyDate(),
            title=self.title_edit.text().strip(),
            currency="EUR",
        )
        client_id = self.client_edit.currentData()
        doc.client = self.session.get(Client, client_id) if client_id else None
        doc.line_items = [LineItem(**line) for line in self._collect_lines()]
        return doc

    def _preview_pdf(self):
        company = self._current_company()
        if company is None:
            QMessageBox.warning(self, tr("documents.err.no_company.title"), tr("documents.err.no_company.body"))
            return
        doc = self._build_preview_document()
        try:
            pdf_bytes = render_document_pdf(company, doc)
        except Exception as exc:  # noqa: BLE001 - surface render errors to the user
            QMessageBox.critical(self, tr("wizard.err.preview_failed.title"), str(exc))
            return
        tmp = Path(tempfile.gettempdir()) / f"seilio_preview_{doc.type.value}.pdf"
        tmp.write_bytes(pdf_bytes)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(tmp)))

    # ---------------------------------------------------------- step 4 ----
    def _build_step4(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.step4_explain = QLabel()
        self.step4_explain.setWordWrap(True)
        layout.addWidget(self.step4_explain)

        form = QFormLayout()
        self.number_edit = QLineEdit()
        self.number_edit.setPlaceholderText(tr("wizard.step4.number_placeholder"))
        form.addRow(tr("wizard.step4.number"), self.number_edit)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.save_draft_btn = QPushButton(tr("wizard.step4.save_draft"))
        self.save_draft_btn.clicked.connect(self._save_draft)
        self.issue_btn = QPushButton(tr("wizard.step4.issue"))
        self.issue_btn.setDefault(True)
        self.issue_btn.clicked.connect(self._issue)
        btn_row.addWidget(self.save_draft_btn)
        btn_row.addWidget(self.issue_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addWidget(_hline())

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.result_label)

        result_btn_row = QHBoxLayout()
        self.open_pdf_btn = QPushButton(tr("wizard.step4.open_pdf"))
        self.open_pdf_btn.clicked.connect(self._open_result_pdf)
        self.open_pdf_btn.setEnabled(False)
        self.open_folder_btn = QPushButton(tr("wizard.step4.open_folder"))
        self.open_folder_btn.clicked.connect(self._open_tiime_folder)
        self.open_folder_btn.setEnabled(False)
        self.done_btn = QPushButton(tr("wizard.step4.done"))
        self.done_btn.clicked.connect(self.accept)
        self.done_btn.setEnabled(False)
        result_btn_row.addWidget(self.open_pdf_btn)
        result_btn_row.addWidget(self.open_folder_btn)
        result_btn_row.addStretch()
        result_btn_row.addWidget(self.done_btn)
        layout.addLayout(result_btn_row)

        layout.addStretch()
        self.stack.addWidget(page)

    def _update_step4_explain(self):
        doc_type = self._current_doc_type()
        if doc_type == DocumentType.invoice:
            self.step4_explain.setText(tr("wizard.step4.explain.invoice"))
        else:
            self.step4_explain.setText(tr("wizard.step4.explain.other", type=type_label(doc_type)))

    def _save_draft(self):
        doc = self._persist(status=DocumentStatus.draft)
        QMessageBox.information(self, tr("wizard.draft_saved.title"), tr("wizard.draft_saved.body", number=doc.number))
        self.document = doc
        self._is_new = False
        self.accept()

    def _issue(self):
        if not getattr(self, "_checks_all_ok", True):
            resp = QMessageBox.question(
                self,
                tr("wizard.warn_present.title"),
                tr("wizard.warn_present.body"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp != QMessageBox.StandardButton.Yes:
                return

        company = self._current_company()
        if company is None:
            QMessageBox.warning(self, tr("documents.err.no_company.title"), tr("documents.err.no_company.body"))
            return
        if self.client_edit.currentData() is None:
            QMessageBox.warning(self, tr("wizard.err.no_client.title"), tr("wizard.err.no_client.body"))
            return

        doc = self._persist(status=DocumentStatus.sent)
        doc.issued_at = dt.datetime.now()

        DOCS_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            pdf_bytes = render_document_pdf(company, doc)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("wizard.err.pdf_failed.title"), str(exc))
            return
        pdf_path = DOCS_EXPORT_DIR / f"{doc.type.value}_{doc.number}.pdf"
        pdf_path.write_bytes(pdf_bytes)
        doc.pdf_export_path = str(pdf_path)

        result_lines = [
            tr("wizard.result.issued", type=type_label(doc.type), number=doc.number),
            tr("wizard.result.pdf", path=pdf_path),
        ]
        tiime_path = None
        if doc.type == DocumentType.invoice:
            try:
                facturx_bytes = generate_facturx_pdf(company, doc)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, tr("wizard.err.facturx_failed.title"), str(exc))
                self.session.commit()
                return
            facturx_name = f"facturx_{doc.number}.pdf"
            facturx_path = DOCS_EXPORT_DIR / facturx_name
            facturx_path.write_bytes(facturx_bytes)
            doc.facturx_export_path = str(facturx_path)

            tiime_dir = tiime_dir_for(company)
            tiime_path = deposit_to_tiime(facturx_bytes, facturx_name, tiime_dir)
            doc.tiime_deposited_at = dt.datetime.now()
            result_lines.append(tr("wizard.result.facturx", path=facturx_path))
            result_lines.append(tr("wizard.result.deposited", path=tiime_path))

        self.session.commit()
        self.document = doc
        self._is_new = False
        self._issued_result = {"pdf_path": pdf_path, "tiime_dir": tiime_dir_for(company) if doc.type == DocumentType.invoice else None}

        self.result_label.setText("<br>".join(result_lines))
        self.open_pdf_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(tiime_path is not None)
        self.done_btn.setEnabled(True)
        self.issue_btn.setEnabled(False)
        self.save_draft_btn.setEnabled(False)

    def _open_result_pdf(self):
        if self._issued_result and self._issued_result.get("pdf_path"):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._issued_result["pdf_path"])))

    def _open_tiime_folder(self):
        if self._issued_result and self._issued_result.get("tiime_dir"):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._issued_result["tiime_dir"])))

    # -------------------------------------------------------- persistence -
    def _persist(self, status: DocumentStatus) -> Document:
        if self.document is not None and self.document.id is not None:
            doc = self.document
        else:
            doc = Document()
            self.session.add(doc)
        doc.type = self._current_doc_type()
        number = self.number_edit.text().strip()
        if not number:
            number = generate_document_number(self.session)
            self.number_edit.setText(number)
        doc.number = number
        doc.client_id = self.client_edit.currentData()
        doc.issue_date = self.date_edit.date().toPyDate()
        doc.title = self.title_edit.text().strip()
        doc.status = status
        doc.currency = "EUR"

        doc.line_items.clear()
        for line in self._collect_lines():
            doc.line_items.append(LineItem(**line))

        self.session.commit()
        return doc

    def _load_from_document(self, doc: Document):
        self.type_edit.setCurrentText(type_label(doc.type))
        self._update_type_explanation()
        if doc.client_id is not None:
            idx = self.client_edit.findData(doc.client_id)
            if idx >= 0:
                self.client_edit.setCurrentIndex(idx)
        self.date_edit.setDate(doc.issue_date)
        self.title_edit.setText(doc.title)
        self.number_edit.setText(doc.number)

        self.line_table.blockSignals(True)
        self.line_table.setRowCount(0)
        for li in doc.line_items:
            self._append_line_row(li.description, li.quantity, li.unit, li.unit_rate, li.vat_rate)
        self.line_table.blockSignals(False)
        self._recalc_total()

    # -------------------------------------------------------- navigation -
    def _goto_step(self, index: int):
        self._max_reached = max(getattr(self, "_max_reached", 0), index)
        self.stack.setCurrentIndex(index)
        self.stepper.blockSignals(True)
        self.stepper.setCurrentRow(index)
        self.stepper.blockSignals(False)
        self.back_btn.setEnabled(index > 0)
        self.next_btn.setVisible(index < len(_step_titles()) - 1)
        if index == 2:
            self._refresh_checks()
        if index == 3:
            self._update_step4_explain()

    def _on_stepper_clicked(self, row: int):
        if row < 0:
            return
        if row > self._max_reached:
            self.stepper.blockSignals(True)
            self.stepper.setCurrentRow(self.stack.currentIndex())
            self.stepper.blockSignals(False)
            return
        self._goto_step(row)

    def _go_back(self):
        idx = self.stack.currentIndex()
        if idx > 0:
            self._goto_step(idx - 1)

    def _go_next(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            if self.client_edit.currentData() is None:
                QMessageBox.warning(self, tr("wizard.err.no_client.title"), tr("wizard.err.no_client.body"))
                return
        if idx == 1:
            if not any(self.line_table.item(r, 0) and self.line_table.item(r, 0).text().strip() for r in range(self.line_table.rowCount())):
                resp = QMessageBox.question(
                    self,
                    tr("wizard.no_lines.title"),
                    tr("wizard.no_lines.body"),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if resp != QMessageBox.StandardButton.Yes:
                    return
        if idx < len(_step_titles()) - 1:
            self._goto_step(idx + 1)


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line
