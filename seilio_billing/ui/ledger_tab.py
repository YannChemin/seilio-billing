from __future__ import annotations

import csv

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QHeaderView,
    QFileDialog,
    QMessageBox,
)

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from seilio_billing.models import LedgerEntry
from seilio_billing.ledger import check_integrity

COLUMNS = ["Seq", "Date", "Amount (EUR)", "Nature", "Hash"]


class LedgerTab(QWidget):
    def __init__(self, session_factory):
        super().__init__()
        self.session_factory = session_factory
        self.session = session_factory()

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.integrity_label = QLabel("")
        check_btn = QPushButton("Check chain integrity")
        check_btn.clicked.connect(self._check_integrity)
        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self._export_csv)
        export_pdf_btn = QPushButton("Export PDF")
        export_pdf_btn.clicked.connect(self._export_pdf)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        top_row.addWidget(check_btn)
        top_row.addWidget(export_csv_btn)
        top_row.addWidget(export_pdf_btn)
        top_row.addWidget(refresh_btn)
        top_row.addStretch()
        layout.addLayout(top_row)
        layout.addWidget(self.integrity_label)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.refresh()

    def _entries(self):
        return self.session.query(LedgerEntry).order_by(LedgerEntry.seq.asc()).all()

    def refresh(self):
        entries = self._entries()
        self.table.setRowCount(len(entries))
        for row, e in enumerate(entries):
            values = [str(e.seq), e.date.isoformat(), f"{e.amount:.2f}", e.nature, e.hash[:16] + "…"]
            for col, val in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(val))

    def _check_integrity(self):
        result = check_integrity(self.session)
        if result.ok:
            self.integrity_label.setText(f"✔ Chain intact — {result.checked} entries verified.")
        else:
            self.integrity_label.setText(f"✘ TAMPERING DETECTED — {result.detail}")

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export livre de recettes (CSV)", "livre_de_recettes.csv", "CSV (*.csv)")
        if not path:
            return
        entries = self._entries()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Seq", "Date", "Amount (EUR)", "Nature", "Hash", "Prev hash"])
            for e in entries:
                writer.writerow([e.seq, e.date.isoformat(), f"{e.amount:.2f}", e.nature, e.hash, e.prev_hash])
        QMessageBox.information(self, "Exported", f"Livre de recettes exported to {path}")

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export livre de recettes (PDF)", "livre_de_recettes.pdf", "PDF (*.pdf)")
        if not path:
            return
        entries = self._entries()
        c = canvas.Canvas(path, pagesize=A4)
        width, height = A4
        y = height - 50
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, y, "Livre de recettes — Seilio Douar E.I.")
        y -= 30
        c.setFont("Helvetica-Bold", 9)
        c.drawString(40, y, "Seq")
        c.drawString(80, y, "Date")
        c.drawString(150, y, "Montant (EUR)")
        c.drawString(260, y, "Nature")
        c.drawString(430, y, "Hash")
        y -= 15
        c.setFont("Helvetica", 8)
        for e in entries:
            if y < 50:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", 8)
            c.drawString(40, y, str(e.seq))
            c.drawString(80, y, e.date.isoformat())
            c.drawString(150, y, f"{e.amount:.2f}")
            c.drawString(260, y, (e.nature or "")[:28])
            c.drawString(430, y, e.hash[:20] + "…")
            y -= 13
        c.save()
        QMessageBox.information(self, "Exported", f"Livre de recettes exported to {path}")
