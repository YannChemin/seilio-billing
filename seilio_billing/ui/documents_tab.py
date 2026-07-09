from __future__ import annotations

import datetime as dt

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLineEdit,
    QComboBox,
    QFormLayout,
    QMessageBox,
    QHeaderView,
    QDateEdit,
    QDoubleSpinBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
)

from seilio_billing.models import Client, Document, DocumentType, DocumentStatus, LineItem, Payment
from seilio_billing.ledger import append_ledger_entry

DOC_COLUMNS = ["Type", "Number", "Client", "Date", "Title", "Status", "Total"]
LINE_COLUMNS = ["Description", "Qty", "Unit", "Unit rate", "VAT %", "Amount"]


class PaymentDialog(QDialog):
    def __init__(self, parent, default_amount: float):
        super().__init__(parent)
        self.setWindowTitle("Record payment")
        layout = QFormLayout(self)
        self.date_edit = QDateEdit(calendarPopup=True)
        self.date_edit.setDate(dt.date.today())
        self.amount_edit = QDoubleSpinBox()
        self.amount_edit.setMaximum(1_000_000)
        self.amount_edit.setDecimals(2)
        self.amount_edit.setValue(default_amount)
        self.method_edit = QLineEdit()
        self.method_edit.setPlaceholderText("virement, chèque, espèces...")
        layout.addRow("Date", self.date_edit)
        layout.addRow("Amount", self.amount_edit)
        layout.addRow("Method", self.method_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return self.date_edit.date().toPyDate(), self.amount_edit.value(), self.method_edit.text().strip()


class DocumentsTab(QWidget):
    def __init__(self, session_factory):
        super().__init__()
        self.session_factory = session_factory
        self.session = session_factory()
        self._editing_id: int | None = None

        outer = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        self.type_filter = QComboBox()
        self.type_filter.addItems(["All"] + [t.value for t in DocumentType])
        self.type_filter.currentIndexChanged.connect(self.refresh)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All"] + [s.value for s in DocumentStatus])
        self.status_filter.currentIndexChanged.connect(self.refresh)
        filter_row.addWidget(QLabel("Type"))
        filter_row.addWidget(self.type_filter)
        filter_row.addWidget(QLabel("Status"))
        filter_row.addWidget(self.status_filter)
        filter_row.addStretch()
        outer.addLayout(filter_row)

        body = QHBoxLayout()
        outer.addLayout(body)

        self.table = QTableWidget(0, len(DOC_COLUMNS))
        self.table.setHorizontalHeaderLabels(DOC_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self._on_select)
        body.addWidget(self.table, stretch=2)

        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form = QFormLayout()

        self.type_edit = QComboBox()
        self.type_edit.addItems([t.value for t in DocumentType])
        self.number_edit = QLineEdit()
        self.client_edit = QComboBox()
        self.date_edit = QDateEdit(calendarPopup=True)
        self.date_edit.setDate(dt.date.today())
        self.title_edit = QLineEdit()
        self.status_edit = QComboBox()
        self.status_edit.addItems([s.value for s in DocumentStatus])

        form.addRow("Type", self.type_edit)
        form.addRow("Number", self.number_edit)
        form.addRow("Client", self.client_edit)
        form.addRow("Date", self.date_edit)
        form.addRow("Title", self.title_edit)
        form.addRow("Status", self.status_edit)
        form_layout.addLayout(form)

        form_layout.addWidget(QLabel("Line items"))
        self.line_table = QTableWidget(0, len(LINE_COLUMNS))
        self.line_table.setHorizontalHeaderLabels(LINE_COLUMNS)
        self.line_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        form_layout.addWidget(self.line_table)

        line_btn_row = QHBoxLayout()
        add_line_btn = QPushButton("Add line")
        add_line_btn.clicked.connect(self._add_line)
        remove_line_btn = QPushButton("Remove selected line")
        remove_line_btn.clicked.connect(self._remove_line)
        line_btn_row.addWidget(add_line_btn)
        line_btn_row.addWidget(remove_line_btn)
        form_layout.addLayout(line_btn_row)

        self.total_label = QLabel("Total: 0.00 EUR")
        form_layout.addWidget(self.total_label)
        self.line_table.itemChanged.connect(self._recalc_total)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._save)
        self.new_btn = QPushButton("New")
        self.new_btn.clicked.connect(self._clear_form)
        self.pay_btn = QPushButton("Mark as paid…")
        self.pay_btn.clicked.connect(self._mark_paid)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete)
        btn_row.addWidget(self.new_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.pay_btn)
        btn_row.addWidget(self.delete_btn)
        form_layout.addLayout(btn_row)

        body.addWidget(form_container, stretch=1)

        self._reload_client_choices()
        self.refresh()

    def _reload_client_choices(self):
        self.client_edit.clear()
        self._clients = self.session.query(Client).order_by(Client.name).all()
        for c in self._clients:
            self.client_edit.addItem(c.name, c.id)

    def refresh(self):
        self._reload_client_choices()
        query = self.session.query(Document)
        if self.type_filter.currentText() != "All":
            query = query.filter(Document.type == DocumentType(self.type_filter.currentText()))
        if self.status_filter.currentText() != "All":
            query = query.filter(Document.status == DocumentStatus(self.status_filter.currentText()))
        docs = query.order_by(Document.issue_date.desc()).all()
        self.table.setRowCount(len(docs))
        for row, d in enumerate(docs):
            values = [
                d.type.value,
                d.number,
                d.client.name if d.client else "",
                d.issue_date.isoformat(),
                d.title,
                d.status.value,
                f"{d.total():.2f}",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val or "")
                item.setData(256, d.id)
                self.table.setItem(row, col, item)

    def _on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 0)
        doc_id = item.data(256)
        doc = self.session.get(Document, doc_id)
        if doc is None:
            return
        self._load_form(doc)

    def _load_form(self, doc: Document):
        self._editing_id = doc.id
        self.type_edit.setCurrentText(doc.type.value)
        self.number_edit.setText(doc.number)
        if doc.client_id is not None:
            idx = self.client_edit.findData(doc.client_id)
            if idx >= 0:
                self.client_edit.setCurrentIndex(idx)
        self.date_edit.setDate(doc.issue_date)
        self.title_edit.setText(doc.title)
        self.status_edit.setCurrentText(doc.status.value)

        self.line_table.blockSignals(True)
        self.line_table.setRowCount(0)
        for li in doc.line_items:
            self._append_line_row(li.description, li.quantity, li.unit, li.unit_rate, li.vat_rate)
        self.line_table.blockSignals(False)
        self._recalc_total()

    def _clear_form(self):
        self._editing_id = None
        self.number_edit.clear()
        self.title_edit.clear()
        self.date_edit.setDate(dt.date.today())
        self.status_edit.setCurrentIndex(0)
        self.line_table.setRowCount(0)
        self.table.clearSelection()
        self._recalc_total()

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
        self.total_label.setText(f"Total: {total:.2f} EUR")

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

    def _save(self):
        if self.client_edit.count() == 0:
            QMessageBox.warning(self, "No client", "Add a client first.")
            return
        if self._editing_id is not None:
            doc = self.session.get(Document, self._editing_id)
        else:
            doc = Document()
            self.session.add(doc)
        doc.type = DocumentType(self.type_edit.currentText())
        doc.number = self.number_edit.text().strip()
        doc.client_id = self.client_edit.currentData()
        doc.issue_date = self.date_edit.date().toPyDate()
        doc.title = self.title_edit.text().strip()
        doc.status = DocumentStatus(self.status_edit.currentText())

        doc.line_items.clear()
        for line in self._collect_lines():
            doc.line_items.append(LineItem(**line))

        self.session.commit()
        self._clear_form()
        self.refresh()

    def _mark_paid(self):
        if self._editing_id is None:
            QMessageBox.information(self, "Select a document", "Save or select a document first.")
            return
        doc = self.session.get(Document, self._editing_id)
        dialog = PaymentDialog(self, default_amount=doc.total())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        paid_date, amount, method = dialog.values()
        payment = Payment(document_id=doc.id, paid_date=paid_date, amount=amount, method=method)
        self.session.add(payment)
        self.session.commit()
        append_ledger_entry(
            self.session, payment, nature=f"{doc.type.value} {doc.number or doc.id} — {doc.title}"
        )
        doc.status = DocumentStatus.paid
        self.session.commit()
        QMessageBox.information(self, "Recorded", "Payment recorded in the livre de recettes.")
        self.refresh()

    def _delete(self):
        if self._editing_id is None:
            return
        doc = self.session.get(Document, self._editing_id)
        if doc is None:
            return
        if doc.payments:
            QMessageBox.warning(
                self, "Cannot delete", "This document has recorded payments and is part of the ledger."
            )
            return
        self.session.delete(doc)
        self.session.commit()
        self._clear_form()
        self.refresh()
