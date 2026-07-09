"""Best-effort parser for the legacy LaTeX invoice/bill/quote archive.

Writes everything to ImportStaging — nothing here ever touches Document,
LineItem or LedgerEntry directly. A human reviews/edits/commits each row
via the Import tab, since these become legal billing records.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ARCHIVE_ROOT = Path.home() / "Documents" / "LaTex" / "Invoice"
SUBFOLDERS = {"Invoice": "invoice", "Billing": "bill", "Quote": "quote"}

OWN_VAT = "FR48511186132"

FLAG_NAME_PATTERNS = re.compile(r"template|test", re.IGNORECASE)

DATE_TEXT_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}\b"
)
FOLDER_DATE_RE = re.compile(r"^(\d{8})")
TITLE_RE = re.compile(r"\\begin\{center\}\{\\bf\s+(.+?)\}\\end\{center\}", re.DOTALL)
VAT_RE = re.compile(r"VAT[:\s]*(?:Number[:\s]*)?([A-Z]{2}[A-Z0-9]{6,15})")
HOURROW_RE = re.compile(r"\\hourrow\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}")
DAYROW_RE = re.compile(r"\\dayrow\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}")
FEEROW_RE = re.compile(r"\\feerow\{([^}]*)\}\{([^}]*)\}")
TO_BLOCK_RE = re.compile(r"\{\\bf To:\}.*?\\\\\s*\\tab\s+(.+?)\\hfill", re.DOTALL)


@dataclass
class ParsedDocument:
    source_path: str
    doc_type_guess: str
    client_name_guess: str
    date_guess: str
    title_guess: str
    vat_number_guess: str
    line_items: list[dict] = field(default_factory=list)
    confidence: str = "low"
    flagged_reason: str = ""


def _strip_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("%"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _guess_date(text: str, path: Path) -> str:
    m = DATE_TEXT_RE.search(text)
    if m:
        return m.group(0)
    m = FOLDER_DATE_RE.match(path.parent.name)
    if m:
        raw = m.group(1)
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return ""


def _guess_client(text: str) -> str:
    m = TO_BLOCK_RE.search(text)
    if m:
        return re.sub(r"\\\\|\{|\}", "", m.group(1)).strip()
    return ""


def _guess_title(text: str) -> str:
    m = TITLE_RE.search(text)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def _guess_vat(text: str) -> str:
    for candidate in VAT_RE.findall(text):
        if candidate != OWN_VAT.replace(" ", ""):
            return candidate
    return ""


def _guess_line_items(text: str) -> list[dict]:
    items = []
    for desc, qty, rate in HOURROW_RE.findall(text):
        items.append({"description": desc.strip(), "quantity": qty.strip(), "unit": "hour", "rate": rate.strip()})
    for desc, qty, rate in DAYROW_RE.findall(text):
        items.append({"description": desc.strip(), "quantity": qty.strip(), "unit": "day", "rate": rate.strip()})
    for desc, amount in FEEROW_RE.findall(text):
        items.append({"description": desc.strip(), "quantity": "1", "unit": "flat", "rate": amount.strip()})
    return items


def parse_file(path: Path) -> ParsedDocument:
    raw = path.read_text(errors="ignore")
    text = _strip_comments(raw)

    parent_name = path.parent.name
    try:
        top_folder = path.relative_to(ARCHIVE_ROOT).parts[0]
    except ValueError:
        top_folder = None
    doc_type = SUBFOLDERS.get(top_folder, "invoice")
    if path.stem == "quote":
        doc_type = "quote"

    client = _guess_client(text)
    date_guess = _guess_date(text, path)
    title = _guess_title(text)
    vat = _guess_vat(text)
    items = _guess_line_items(text)

    confidence = "high"
    flagged_reason = ""
    if FLAG_NAME_PATTERNS.search(parent_name):
        confidence = "low"
        flagged_reason = "folder name suggests this is a template/test, not a real billing record"
    elif not client or not date_guess:
        confidence = "medium"
        flagged_reason = "could not confidently parse client name and/or date"
    elif not items:
        confidence = "medium"
        flagged_reason = "no line items detected"

    return ParsedDocument(
        source_path=str(path),
        doc_type_guess=doc_type,
        client_name_guess=client,
        date_guess=date_guess,
        title_guess=title,
        vat_number_guess=vat,
        line_items=items,
        confidence=confidence,
        flagged_reason=flagged_reason,
    )


def find_candidate_files() -> list[Path]:
    if not ARCHIVE_ROOT.exists():
        return []
    candidates = []
    for sub in SUBFOLDERS:
        folder = ARCHIVE_ROOT / sub
        if not folder.exists():
            continue
        for tex in folder.rglob("*.tex"):
            if tex.name in ("acronyms.tex",):
                continue
            candidates.append(tex)
    return sorted(candidates)


def to_staging_kwargs(parsed: ParsedDocument) -> dict:
    return dict(
        source_path=parsed.source_path,
        doc_type_guess=parsed.doc_type_guess,
        client_name_guess=parsed.client_name_guess,
        date_guess=parsed.date_guess,
        title_guess=parsed.title_guess,
        vat_number_guess=parsed.vat_number_guess,
        line_items_json=json.dumps(parsed.line_items),
        confidence=parsed.confidence,
        flagged_reason=parsed.flagged_reason,
    )
