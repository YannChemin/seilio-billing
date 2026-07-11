"""Deposit finished Factur-X invoices into the local folder Tiime picks up
for accounting submission.

Tiime has no public API for programmatic deposit, so this writes the file
to a plain local folder (configurable in Settings, default
~/Tiime/Factures) that the user points their Tiime desktop sync / import
at. This keeps issuance a one-click, no-manual-file-dialog action.
"""
from __future__ import annotations

from pathlib import Path

from seilio_billing.models import Company

DEFAULT_TIIME_DIR = Path.home() / "Tiime" / "Factures"


def tiime_dir_for(company: Company | None) -> Path:
    if company and company.tiime_export_dir:
        return Path(company.tiime_export_dir).expanduser()
    return DEFAULT_TIIME_DIR


def deposit_to_tiime(pdf_bytes: bytes, filename: str, tiime_dir: Path) -> Path:
    tiime_dir.mkdir(parents=True, exist_ok=True)
    path = tiime_dir / filename
    path.write_bytes(pdf_bytes)
    return path
