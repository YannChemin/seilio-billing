"""One-off enrichment: scan the whole legacy LaTeX archive, extract full
client "To:" blocks (name, street, postcode/city, country, VAT, phone if
present), split a personal contact (title/name/position) out from the
company name where the "To:" line names a person rather than an
organisation, merge duplicates by normalized name across all their
invoices/quotes/bills, and upsert into the real Client table so each client
has a filled-in card.

Read-only against the LaTeX files; writes only to the Client table (never
touches Document/LedgerEntry). Safe to re-run: matching tries, in order, the
parsed company name, a substring match against the existing name, and (when
a title/contact split happened) a substring match on the contact's name --
that last one is what lets a re-run correct an existing row whose `name`
was previously "Dr. Firstname Lastname" into the real company name without
creating a duplicate. Fields are only overwritten when the existing value is
blank or the newly parsed value is longer/more specific.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seilio_billing.db import get_session_factory, init_db
from seilio_billing.importer import ARCHIVE_ROOT, FLAG_NAME_PATTERNS, SUBFOLDERS, _strip_comments
from seilio_billing.models import Client

INLINE_COMMENT_RE = re.compile(r"(?<!\\)%.*")

COUNTRIES = [
    "France", "Italy", "Belgium", "Thailand", "Pakistan", "India", "Nepal",
    "Sri Lanka", "Netherlands", "Germany", "Spain", "United Kingdom", "UK",
    "USA", "United States", "Switzerland", "Portugal", "Morocco", "Tunisia",
    "Senegal", "Vietnam", "Cambodia", "Laos", "Indonesia", "Philippines",
    "China", "Japan", "Kenya", "Ivory Coast", "Cote d'Ivoire", "Madagascar",
    "Reunion", "Réunion",
]
COUNTRY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in COUNTRIES) + r")\b", re.IGNORECASE
)
POSTAL_RE = re.compile(r"\b\d{4,6}\b")
VAT_RE = re.compile(r"(?:VAT|TVA|NTN)[^:]*:?\s*([A-Z]{0,2}[\d\-]{6,20})")
PHONE_RE = re.compile(r"(\+?\d[\d\-\s()]{6,}\d)")
PLACEHOLDER_RE = re.compile(r"^-+$")

TITLE_RE = re.compile(r"^(Mr|Mrs|Ms|Dr|Prof)\.?\s+(.+)$", re.IGNORECASE)
POSITION_KEYWORDS = (
    "manager", "director", "officer", "assistant", "registrar", "coordinator",
    "consultant", "engineer", "professor", "chief", "ceo", "cto", "president",
    "secretary", "human resources", " hr", "dean", "department", "dept",
    "office", "head of",
)

ACCENT_RE = re.compile(r"\\['`\"^~c](\{?)([a-zA-Z])\}?")
ACCENT_MAP = {
    "'e": "é", "'a": "á", "'i": "í", "'o": "ó", "'u": "ú", "'E": "É",
    "`e": "è", "`a": "à", "`u": "ù", "`E": "È",
    "^e": "ê", "^a": "â", "^o": "ô", "^i": "î", "^u": "û",
    '"o': "ö", '"u': "ü", '"a': "ä",
    "~n": "ñ",
    "cc": "ç",
}


def _unescape_accents(text: str) -> str:
    def repl(m: re.Match) -> str:
        accent_char = m.group(0)[1]
        letter = m.group(2)
        return ACCENT_MAP.get(accent_char + letter, letter)

    return ACCENT_RE.sub(repl, text)


TO_BLOCK_START_RE = re.compile(r"\{\\bf\s+To:\}")
BLOCK_END_MARKERS = (r"\begin{center}", r"\begin{invoiceTable}", r"\bigskip", r"{\bf Summary")

REQUESTER_RE = re.compile(
    r"\\textbf\{Requester:\}\s*([^\\]+?)\s*Email\s*:\s*\\href\{mailto:[^}]*\}\{([^<]+)<([^>]+)>\}"
)


def _clean_fragment(text: str, keep_hfill: bool = False) -> str:
    text = INLINE_COMMENT_RE.sub("", text)  # strip trailing %-comments, but not escaped \%
    if not keep_hfill:
        text = re.sub(r"\\hfill.*", "", text)
    else:
        text = text.replace("\\hfill", " | ")
    text = re.sub(r"\\tab", "", text)
    text = re.sub(r"\\\\$", "", text)
    text = _unescape_accents(text)
    text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r" \1 ", text)  # unwrap \cmd{...}, spaced to avoid gluing
    text = re.sub(r"\\[a-zA-Z]+", " ", text)  # drop bare stray commands (\scriptsize, \bfseries...)
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\s+", " ", text).strip(" ,")
    return text


def _is_position_line(line: str) -> bool:
    lower = line.lower()
    return any(kw in lower for kw in POSITION_KEYWORDS)


@dataclass
class ClientCard:
    name: str = ""
    address_line: str = ""
    postal_code: str = ""
    city: str = ""
    country: str = ""
    vat_number: str = ""
    contact_email: str = ""
    title: str = ""
    contact_name: str = ""
    position: str = ""
    phone_fixed: str = ""
    notes: str = ""
    sources: list = field(default_factory=list)

    def score(self) -> int:
        return sum(
            bool(v)
            for v in (
                self.address_line, self.postal_code, self.city, self.country,
                self.vat_number, self.contact_email, self.title, self.contact_name,
                self.position, self.phone_fixed,
            )
        )


def extract_to_block_lines(text: str) -> tuple[list[str], list[str]]:
    """Return (left_column_lines, right_column_fragments). The right column
    (after \\hfill on each line) often carries the client's own VAT/
    registration number and phone, not just seller boilerplate."""
    m = TO_BLOCK_START_RE.search(text)
    if not m:
        return [], []
    rest = text[m.end():]
    end_positions = [rest.find(marker) for marker in BLOCK_END_MARKERS if rest.find(marker) != -1]
    if end_positions:
        rest = rest[: min(end_positions)]
    raw_lines = [ln for ln in rest.split("\\\\") if ln.strip()]

    left_lines = [_clean_fragment(ln) for ln in raw_lines]
    left_lines = [ln for ln in left_lines if ln]

    right_fragments = []
    for ln in raw_lines:
        if "\\hfill" in ln:
            right_part = ln.split("\\hfill", 1)[1]
            cleaned = _clean_fragment(right_part)
            if cleaned:
                right_fragments.append(cleaned)
    return left_lines, right_fragments


def _extract_vat_and_phone(fragments: list[str]) -> tuple[str, str]:
    vat_number, phone = "", ""
    for frag in fragments:
        if not vat_number:
            m = VAT_RE.search(frag)
            if m and not PLACEHOLDER_RE.match(m.group(1)):
                vat_number = m.group(1).strip()
        if not phone and ("contact" in frag.lower() or "tel" in frag.lower() or "phone" in frag.lower()):
            m = PHONE_RE.search(frag)
            if m:
                phone = m.group(1).strip()
    return vat_number, phone


def _parse_requester_fallback(text: str, path: Path) -> ClientCard | None:
    m = REQUESTER_RE.search(text)
    if not m:
        return None
    person_and_org, _person_name_dup, email = m.groups()
    parts = [p.strip() for p in person_and_org.split(",") if p.strip()]
    if len(parts) < 3:
        return None
    country = parts[-1]
    city = parts[-2]
    company = parts[-3]

    title, contact_name = "", parts[0]
    title_match = TITLE_RE.match(parts[0])
    if title_match:
        title, contact_name = title_match.group(1), title_match.group(2)
    position = parts[1] if len(parts) >= 4 else ""

    return ClientCard(
        name=company,
        city=city,
        country=country,
        contact_email=email.strip(),
        title=title,
        contact_name=contact_name,
        position=position,
        sources=[str(path)],
    )


def parse_client_card(path: Path) -> ClientCard | None:
    raw = path.read_text(errors="ignore")
    text = _strip_comments(raw)
    left_lines, right_fragments = extract_to_block_lines(text)
    if not left_lines:
        # "template.tex" report drafts list a technical point of contact under
        # "Requester:", not the actual billing client — the comma-split
        # heuristic below misreads that structure, so skip it there.
        if path.stem == "template":
            return None
        return _parse_requester_fallback(text, path)

    name_line = left_lines[0].strip(" ,")
    if not name_line:
        return None

    card = ClientCard(sources=[str(path)])
    title_match = TITLE_RE.match(name_line)
    if title_match:
        card.title, card.contact_name = title_match.group(1).title(), title_match.group(2).strip()
    else:
        card.name = name_line

    body_lines = left_lines[1:]

    remaining_for_vat = " | ".join(body_lines)
    vat_match = VAT_RE.search(remaining_for_vat)
    if vat_match and not PLACEHOLDER_RE.match(vat_match.group(1)):
        card.vat_number = vat_match.group(1).strip()
    right_vat, right_phone = _extract_vat_and_phone(right_fragments)
    if right_vat and not card.vat_number:
        card.vat_number = right_vat
    if right_phone:
        card.phone_fixed = right_phone

    street_parts = []
    position_parts = []
    for line in body_lines:
        if VAT_RE.search(line) or "registration no" in line.lower() or "contact:" in line.lower():
            continue
        country_match = COUNTRY_RE.search(line)
        postal_match = POSTAL_RE.search(line)
        if country_match:
            card.country = country_match.group(1)
            remainder = (line[: country_match.start()] + line[country_match.end():]).strip(" ,")
            if postal_match:
                card.postal_code = postal_match.group(0)
                remainder = remainder.replace(postal_match.group(0), "").strip(" ,")
            if remainder:
                card.city = remainder
        elif postal_match:
            card.postal_code = postal_match.group(0)
            remainder = line.replace(postal_match.group(0), "").strip(" ,")
            if remainder:
                card.city = remainder
        elif _is_position_line(line):
            position_parts.append(line)
        else:
            street_parts.append(line)

    if title_match:
        # The "To:" line named a person, not an org: the first street-like
        # line is the actual client company, if we found one.
        if street_parts:
            card.name = street_parts.pop(0)
        else:
            card.name = f"{card.title} {card.contact_name}".strip()
            card.notes = "Company name not found in source document — verify manually."
        card.position = ", ".join(position_parts)
    elif position_parts:
        # No title split, but position-like lines still exist (rare) — keep
        # them out of the address.
        pass

    card.address_line = ", ".join(street_parts)
    return card


def normalize_name(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r"^(mr|mrs|ms|dr|prof)\.?\s+", "", n)
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    return n


FIELDS_TO_MERGE = (
    "address_line", "postal_code", "city", "country", "vat_number",
    "contact_email", "title", "contact_name", "position", "phone_fixed", "notes",
)


def merge(cards: list[ClientCard]) -> ClientCard:
    best = max(cards, key=lambda c: c.score())
    merged = ClientCard(name=best.name, sources=[s for c in cards for s in c.sources])
    for field_name in FIELDS_TO_MERGE:
        setattr(merged, field_name, getattr(best, field_name))
    for c in cards:
        for field_name in FIELDS_TO_MERGE:
            current = getattr(merged, field_name)
            candidate = getattr(c, field_name)
            if candidate and (not current or len(candidate) > len(current)):
                setattr(merged, field_name, candidate)
    return merged


def find_all_files() -> list[Path]:
    files = []
    for sub in SUBFOLDERS:
        folder = ARCHIVE_ROOT / sub
        if folder.exists():
            files.extend(sorted(folder.rglob("*.tex")))
    return [
        f
        for f in files
        if f.name != "acronyms.tex" and not FLAG_NAME_PATTERNS.search(f.parent.name)
    ]


def find_existing_client(session, merged: ClientCard) -> Client | None:
    existing = session.query(Client).filter(Client.name.ilike(merged.name)).first()
    if existing is not None:
        return existing
    existing = session.query(Client).filter(Client.name.ilike(f"%{merged.name}%")).first()
    if existing is not None:
        return existing
    if merged.contact_name:
        # Catches a previous run's row whose name was "Title Contact Name"
        # before this run split it into the real company name.
        existing = session.query(Client).filter(Client.name.ilike(f"%{merged.contact_name}%")).first()
    return existing


def main() -> None:
    files = find_all_files()
    parsed = []
    unparsed = []
    for f in files:
        card = parse_client_card(f)
        if card:
            parsed.append(card)
        else:
            unparsed.append(f)

    groups: dict[str, list[ClientCard]] = {}
    for card in parsed:
        key = normalize_name(card.contact_name or card.name)
        groups.setdefault(key, []).append(card)

    init_db()
    session = get_session_factory()()

    created, updated = 0, 0
    for key, cards in groups.items():
        merged = merge(cards)
        existing = find_existing_client(session, merged)

        if existing is None:
            client = Client(name=merged.name)
            for f_ in FIELDS_TO_MERGE:
                setattr(client, f_, getattr(merged, f_))
            session.add(client)
            created += 1
        else:
            if existing.name != merged.name and merged.name:
                existing.name = merged.name
            for f_ in FIELDS_TO_MERGE:
                current = getattr(existing, f_)
                candidate = getattr(merged, f_)
                if candidate and (not current or len(candidate) > len(current)):
                    setattr(existing, f_, candidate)
            updated += 1
        print(
            f"[{'NEW' if existing is None else 'UPD'}] {merged.name!r} "
            f"(title={merged.title!r} contact={merged.contact_name!r} position={merged.position!r}): "
            f"addr={merged.address_line!r} postal={merged.postal_code!r} city={merged.city!r} "
            f"country={merged.country!r} vat={merged.vat_number!r} phone={merged.phone_fixed!r} "
            f"email={merged.contact_email!r} notes={merged.notes!r}  (from {len(cards)} doc(s))"
        )

    session.commit()

    print()
    print(f"Client cards created: {created}, updated: {updated}")
    if unparsed:
        print(f"\n{len(unparsed)} file(s) had no parseable 'To:' block (need manual entry):")
        for f in unparsed:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
