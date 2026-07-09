"""Seed the single Company row, reading identity fields from the legacy
LaTeX invoice header when available, falling back to known defaults.
"""
from __future__ import annotations

import re
from pathlib import Path

from seilio_billing.db import new_session
from seilio_billing.models import Company

LEGACY_INVOICE_TEX = Path.home() / "Documents" / "LaTex" / "Invoice" / "Invoice" / "invoice.tex"

DEFAULTS = dict(
    name="Seilio Douar E.I. (Dr. Yann Chemin)",
    address_line="4, rue du Guern",
    postal_code="56400",
    city="Sainte-Anne d'Auray",
    country="France",
    siret="511 186 132 00029",
    vat_number="FR48511186132",
    email="ychemin@gmail.com",
    phone="+33 (0)7 83 85 52 34",
    iban="FR76 1600 6020 2100 8117 8489 328",
    bic="AGRIFRPP860",
    bank_name="CREDIT AGRICOLE DU MORBIHAN",
)


def parse_company_from_tex(path: Path) -> dict:
    """Best-effort scrape of the header block of invoice.tex. Falls back to
    DEFAULTS for any field it can't confidently find."""
    fields = dict(DEFAULTS)
    if not path.exists():
        return fields
    text = path.read_text(errors="ignore")

    m = re.search(r"SIRET Tax Number:\s*([0-9 ]+)", text)
    if m:
        fields["siret"] = m.group(1).strip()
    m = re.search(r"VAT Number:\s*([A-Z0-9]+)", text)
    if m:
        fields["vat_number"] = m.group(1).strip()
    m = re.search(r"([\w.+-]+@[\w.-]+)", text)
    if m:
        fields["email"] = m.group(1).strip()
    m = re.search(r"(\+33[\d() .]+)", text)
    if m:
        fields["phone"] = m.group(1).strip()
    return fields


def seed_company(db_path=None) -> None:
    session = new_session(db_path)
    try:
        existing = session.query(Company).first()
        if existing is not None:
            return
        fields = parse_company_from_tex(LEGACY_INVOICE_TEX)
        session.add(Company(**fields))
        session.commit()
    finally:
        session.close()
