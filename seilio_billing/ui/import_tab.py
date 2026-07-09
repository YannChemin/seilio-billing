from __future__ import annotations

import datetime as dt
import json
import re

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QHeaderView,
    QMessageBox,
    QComboBox,
)

from seilio_billing.importer import find_candidate_files, parse_file, to_staging_kwargs
from seilio_billing.models import Client, Document, DocumentType, DocumentStatus, ImportStaging, LineItem

COLUMNS = ["Confidence", "Type", "Client", "Date", "Title", "Line items", "Source", "Status"]

MONTH_NAME_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s+(\d{4})"
)
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
    )
}


def parse_date_guess(text: str) -> dt.date | None:
    m = MONTH_NAME_RE.search(text)
    if m:
        return dt.date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


class ImportTab(QWidget):
    def __init__(self, session_factory, on_change=None):
        super().__init__()
        self.session_factory = session_factory
        self.session = session_factory()
        self.on_change = on_change

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        scan_btn = QPushButton("Scan legacy LaTeX archive")
        scan_btn.clicked.connect(self._scan)
        commit_btn = QPushButton("Commit selected row")
        commit_btn.clicked.connect(self._commit_selected)
        discard_btn = QPushButton("Discard selected row")
        discard_btn.clicked.connect(self._discard_selected)
        top_row.addWidget(scan_btn)
        top_row.addWidget(commit_btn)
        top_row.addWidget(discard_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        layout.addWidget(
            QLabel(
                "Nothing here is a real record until you commit it. Rows flagged "
                "medium/low confidence should be checked against the original file before committing."
            )
        )

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        self.refresh()

    def _scan(self):
        existing_paths = {s.source_path for s in self.session.query(ImportStaging.source_path)}
        files = find_candidate_files()
        added = 0
        for f in files:
            if str(f) in existing_paths:
                continue
            parsed = parse_file(f)
            self.session.add(ImportStaging(**to_staging_kwargs(parsed)))
            added += 1
        self.session.commit()
        QMessageBox.information(self, "Scan complete", f"{added} new file(s) staged for review.")
        self.refresh()

    def refresh(self):
        rows = self.session.query(ImportStaging).order_by(ImportStaging.confidence, ImportStaging.source_path).all()
        self.table.setRowCount(len(rows))
        for row, s in enumerate(rows):
            items = json.loads(s.line_items_json or "[]")
            items_text = "; ".join(f"{i['description']} ({i['quantity']}x{i['rate']})" for i in items)
            status = "committed" if s.committed_document_id else ("reviewed" if s.reviewed else "pending")
            values = [
                s.confidence,
                s.doc_type_guess,
                s.client_name_guess,
                s.date_guess,
                s.title_guess,
                items_text,
                s.source_path,
                status,
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val or "")
                item.setData(256, s.id)
                self.table.setItem(row, col, item)

    def _selected_staging(self) -> ImportStaging | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        staging_id = self.table.item(rows[0].row(), 0).data(256)
        return self.session.get(ImportStaging, staging_id)

    def _commit_selected(self):
        staging = self._selected_staging()
        if staging is None:
            QMessageBox.information(self, "Select a row", "Select a staged row first.")
            return
        if staging.committed_document_id:
            QMessageBox.information(self, "Already committed", "This row was already committed.")
            return

        client_name = staging.client_name_guess.strip() or "Unknown client"
        client = self.session.query(Client).filter_by(name=client_name).first()
        if client is None:
            client = Client(name=client_name)
            self.session.add(client)
            self.session.flush()

        issue_date = parse_date_guess(staging.date_guess) or dt.date.today()

        try:
            doc_type = DocumentType(staging.doc_type_guess)
        except ValueError:
            doc_type = DocumentType.invoice

        doc = Document(
            type=doc_type,
            client_id=client.id,
            issue_date=issue_date,
            title=staging.title_guess,
            status=DocumentStatus.draft,
            source_path=staging.source_path,
        )
        self.session.add(doc)
        self.session.flush()

        for item in json.loads(staging.line_items_json or "[]"):
            try:
                qty = float(item.get("quantity") or 0)
                rate = float(item.get("rate") or 0)
            except ValueError:
                qty, rate = 0.0, 0.0
            self.session.add(
                LineItem(
                    document_id=doc.id,
                    description=item.get("description", ""),
                    quantity=qty,
                    unit=item.get("unit", ""),
                    unit_rate=rate,
                    vat_rate=0.0,
                )
            )

        staging.reviewed = True
        staging.committed_document_id = doc.id
        self.session.commit()
        if self.on_change:
            self.on_change()
        self.refresh()

    def _discard_selected(self):
        staging = self._selected_staging()
        if staging is None:
            return
        self.session.delete(staging)
        self.session.commit()
        self.refresh()
