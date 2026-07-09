from __future__ import annotations

import datetime as dt
from collections import defaultdict

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QHeaderView,
    QComboBox,
)

from seilio_billing.models import LedgerEntry

# 2026 micro-entrepreneur turnover ceilings (services / BIC-BNC prestations de services)
# https://www.economie.gouv.fr - update yearly if the plafond changes.
PLAFOND_SERVICES = 77_700.0

COLUMNS = ["Period", "Revenue encaissé (EUR)"]


class DeclarationsTab(QWidget):
    def __init__(self, session_factory):
        super().__init__()
        self.session_factory = session_factory
        self.session = session_factory()

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Monthly", "Quarterly"])
        self.mode_combo.currentIndexChanged.connect(self.refresh)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        top_row.addWidget(QLabel("Group by"))
        top_row.addWidget(self.mode_combo)
        top_row.addWidget(refresh_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        self.ytd_label = QLabel("")
        layout.addWidget(self.ytd_label)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.refresh()

    def _period_key(self, date: dt.date, quarterly: bool) -> str:
        if quarterly:
            q = (date.month - 1) // 3 + 1
            return f"{date.year}-Q{q}"
        return f"{date.year}-{date.month:02d}"

    def refresh(self):
        quarterly = self.mode_combo.currentText() == "Quarterly"
        entries = self.session.query(LedgerEntry).all()
        totals: dict[str, float] = defaultdict(float)
        for e in entries:
            totals[self._period_key(e.date, quarterly)] += e.amount

        rows = sorted(totals.items())
        self.table.setRowCount(len(rows))
        for row, (period, amount) in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(period))
            self.table.setItem(row, 1, QTableWidgetItem(f"{amount:.2f}"))

        current_year = dt.date.today().year
        ytd = sum(e.amount for e in entries if e.date.year == current_year)
        pct = (ytd / PLAFOND_SERVICES) * 100 if PLAFOND_SERVICES else 0
        self.ytd_label.setText(
            f"YTD {current_year}: {ytd:.2f} EUR encaissé — "
            f"{pct:.1f}% of the {PLAFOND_SERVICES:.0f} EUR micro-entrepreneur services ceiling "
            f"(verify current plafond on economie.gouv.fr)"
        )
