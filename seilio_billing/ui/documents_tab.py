from __future__ import annotations

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QComboBox,
    QMessageBox,
    QHeaderView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QDateEdit,
    QDoubleSpinBox,
    QLabel,
)

import datetime as dt

from seilio_billing.i18n import tr
from seilio_billing.models import Company, Document, DocumentType, DocumentStatus, Payment
from seilio_billing.ledger import append_ledger_entry
from seilio_billing.facturx_export import generate_facturx_pdf
from seilio_billing.tiime_export import deposit_to_tiime, tiime_dir_for
from seilio_billing.ui.document_wizard import DocumentWizard, DOCS_EXPORT_DIR
from seilio_billing.ui.i18n import type_label, status_label, type_labels, status_labels


def _doc_columns():
    return [
        tr("documents.col.type"), tr("documents.col.number"), tr("documents.col.client"),
        tr("documents.col.date"), tr("documents.col.title"), tr("documents.col.status"),
        tr("documents.col.total"), tr("documents.col.facturx"),
    ]


def _payment_methods():
    return [
        tr("documents.pay_method.transfer"),
        tr("documents.pay_method.card"),
        tr("documents.pay_method.cash"),
        tr("documents.pay_method.check"),
        tr("documents.pay_method.direct_debit"),
        tr("documents.pay_method.online"),
        tr("documents.pay_method.paypal"),
        tr("documents.pay_method.other"),
    ]


class PaymentDialog(QDialog):
    def __init__(self, parent, default_amount: float):
        super().__init__(parent)
        self.setWindowTitle(tr("documents.pay_dialog.title"))
        layout = QFormLayout(self)
        self.date_edit = QDateEdit(calendarPopup=True)
        self.date_edit.setDate(dt.date.today())
        self.amount_edit = QDoubleSpinBox()
        self.amount_edit.setMaximum(1_000_000)
        self.amount_edit.setDecimals(2)
        self.amount_edit.setValue(default_amount)
        self.method_edit = QComboBox()
        self.method_edit.setEditable(True)
        self.method_edit.addItems(_payment_methods())
        layout.addRow(tr("documents.pay_dialog.date"), self.date_edit)
        layout.addRow(tr("documents.pay_dialog.amount"), self.amount_edit)
        layout.addRow(tr("documents.pay_dialog.method"), self.method_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return self.date_edit.date().toPyDate(), self.amount_edit.value(), self.method_edit.currentText().strip()


class DocumentsTab(QWidget):
    def __init__(self, session_factory):
        super().__init__()
        self.session_factory = session_factory
        self.session = session_factory()
        self._selected_id: int | None = None

        outer = QVBoxLayout(self)

        intro = QLabel(tr("documents.intro"))
        intro.setWordWrap(True)
        outer.addWidget(intro)

        filter_row = QHBoxLayout()
        self.type_filter = QComboBox()
        self.type_filter.addItems([tr("documents.filter.all")] + list(type_labels().keys()))
        self.type_filter.currentIndexChanged.connect(self.refresh)
        self.status_filter = QComboBox()
        self.status_filter.addItems([tr("documents.filter.all")] + list(status_labels().keys()))
        self.status_filter.currentIndexChanged.connect(self.refresh)
        filter_row.addWidget(QLabel(tr("documents.filter.type")))
        filter_row.addWidget(self.type_filter)
        filter_row.addWidget(QLabel(tr("documents.filter.status")))
        filter_row.addWidget(self.status_filter)
        filter_row.addStretch()
        outer.addLayout(filter_row)

        columns = _doc_columns()
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.itemDoubleClicked.connect(lambda _: self._edit())
        outer.addWidget(self.table, stretch=1)

        btn_row = QHBoxLayout()
        self.new_btn = QPushButton(tr("documents.btn.new"))
        self.new_btn.clicked.connect(self._new)
        self.edit_btn = QPushButton(tr("documents.btn.edit"))
        self.edit_btn.clicked.connect(self._edit)
        self.pay_btn = QPushButton(tr("documents.btn.pay"))
        self.pay_btn.clicked.connect(self._mark_paid)
        self.open_pdf_btn = QPushButton(tr("documents.btn.open_pdf"))
        self.open_pdf_btn.clicked.connect(self._open_pdf)
        self.regen_btn = QPushButton(tr("documents.btn.regen"))
        self.regen_btn.clicked.connect(self._regenerate_facturx)
        self.delete_btn = QPushButton(tr("documents.btn.delete"))
        self.delete_btn.clicked.connect(self._delete)
        for b in (self.new_btn, self.edit_btn, self.pay_btn, self.open_pdf_btn, self.regen_btn, self.delete_btn):
            btn_row.addWidget(b)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        self.refresh()

    def refresh(self):
        query = self.session.query(Document)
        if self.type_filter.currentText() != tr("documents.filter.all"):
            query = query.filter(Document.type == type_labels()[self.type_filter.currentText()])
        if self.status_filter.currentText() != tr("documents.filter.all"):
            query = query.filter(Document.status == status_labels()[self.status_filter.currentText()])
        docs = query.order_by(Document.issue_date.desc()).all()
        self.table.setRowCount(len(docs))
        for row, d in enumerate(docs):
            if d.tiime_deposited_at:
                facturx_state = tr("documents.state.deposited")
            elif d.type != DocumentType.invoice:
                facturx_state = "—"
            else:
                facturx_state = tr("documents.state.not_yet")
            values = [
                type_label(d.type),
                d.number,
                d.client.name if d.client else "",
                d.issue_date.isoformat(),
                d.title,
                status_label(d.status),
                f"{d.total():.2f}",
                facturx_state,
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val or "")
                item.setData(256, d.id)
                self.table.setItem(row, col, item)
        self._selected_id = None
        self._update_button_state()

    def _on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self._selected_id = None
        else:
            item = self.table.item(rows[0].row(), 0)
            self._selected_id = item.data(256)
        self._update_button_state()

    def _update_button_state(self):
        has_selection = self._selected_id is not None
        doc = self.session.get(Document, self._selected_id) if has_selection else None
        self.edit_btn.setEnabled(has_selection)
        self.pay_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)
        self.open_pdf_btn.setEnabled(bool(doc and doc.pdf_export_path))
        self.regen_btn.setEnabled(bool(doc and doc.type == DocumentType.invoice))

    def _new(self):
        wizard = DocumentWizard(self.session, document=None, parent=self)
        wizard.exec()
        self.refresh()

    def _edit(self):
        if self._selected_id is None:
            QMessageBox.information(self, tr("documents.err.select.title"), tr("documents.err.select.body"))
            return
        doc = self.session.get(Document, self._selected_id)
        if doc is None:
            return
        wizard = DocumentWizard(self.session, document=doc, parent=self)
        wizard.exec()
        self.refresh()

    def _open_pdf(self):
        doc = self.session.get(Document, self._selected_id) if self._selected_id else None
        if doc and doc.pdf_export_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(doc.pdf_export_path))

    def _regenerate_facturx(self):
        doc = self.session.get(Document, self._selected_id) if self._selected_id else None
        if doc is None or doc.type != DocumentType.invoice:
            return
        company = self.session.query(Company).first()
        if company is None:
            QMessageBox.warning(self, tr("documents.err.no_company.title"), tr("documents.err.no_company.body"))
            return
        try:
            facturx_bytes = generate_facturx_pdf(company, doc)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("documents.err.generation_failed.title"), str(exc))
            return
        DOCS_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        facturx_name = f"facturx_{doc.number}.pdf"
        facturx_path = DOCS_EXPORT_DIR / facturx_name
        facturx_path.write_bytes(facturx_bytes)
        doc.facturx_export_path = str(facturx_path)
        tiime_dir = tiime_dir_for(company)
        tiime_path = deposit_to_tiime(facturx_bytes, facturx_name, tiime_dir)
        doc.tiime_deposited_at = dt.datetime.now()
        self.session.commit()
        QMessageBox.information(
            self, tr("documents.regen.done.title"), tr("documents.regen.done.body", path=tiime_path)
        )
        self.refresh()

    def _mark_paid(self):
        if self._selected_id is None:
            QMessageBox.information(self, tr("documents.err.select.title"), tr("documents.err.select.body"))
            return
        doc = self.session.get(Document, self._selected_id)
        dialog = PaymentDialog(self, default_amount=doc.total())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        paid_date, amount, method = dialog.values()
        payment = Payment(document_id=doc.id, paid_date=paid_date, amount=amount, method=method)
        self.session.add(payment)
        self.session.commit()
        append_ledger_entry(
            self.session, payment, nature=f"{type_label(doc.type)} {doc.number or doc.id} — {doc.title}"
        )
        doc.status = DocumentStatus.paid
        self.session.commit()
        QMessageBox.information(self, tr("documents.pay.recorded.title"), tr("documents.pay.recorded.body"))
        self.refresh()

    def _delete(self):
        if self._selected_id is None:
            return
        doc = self.session.get(Document, self._selected_id)
        if doc is None:
            return
        if doc.payments:
            QMessageBox.warning(
                self, tr("documents.err.cannot_delete.title"), tr("documents.err.cannot_delete.body")
            )
            return
        self.session.delete(doc)
        self.session.commit()
        self.refresh()
