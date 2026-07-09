"""Livre de recettes: append-only ledger with a SHA-256 hash chain.

Each entry's hash covers the previous entry's hash plus its own canonical
fields, so altering or deleting a past row breaks the chain from that point
forward. The app must never UPDATE or DELETE a LedgerEntry row.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from seilio_billing.models import LedgerEntry, Payment

GENESIS_HASH = "0" * 64


def _canonical(seq: int, date_iso: str, payment_id: int, amount: float, nature: str, prev_hash: str) -> str:
    return f"{seq}|{date_iso}|{payment_id}|{amount:.2f}|{nature}|{prev_hash}"


def _row_hash(seq: int, date_iso: str, payment_id: int, amount: float, nature: str, prev_hash: str) -> str:
    payload = _canonical(seq, date_iso, payment_id, amount, nature, prev_hash)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_ledger_entry(session: Session, payment: Payment, nature: str = "") -> LedgerEntry:
    """Create the next LedgerEntry chained onto the last one, for a Payment
    that was just recorded. Call this once per Payment."""
    last = session.query(LedgerEntry).order_by(LedgerEntry.seq.desc()).first()
    seq = (last.seq + 1) if last else 1
    prev_hash = last.hash if last else GENESIS_HASH
    date_iso = payment.paid_date.isoformat()
    row_hash = _row_hash(seq, date_iso, payment.id, payment.amount, nature, prev_hash)

    entry = LedgerEntry(
        seq=seq,
        date=payment.paid_date,
        payment_id=payment.id,
        amount=payment.amount,
        nature=nature,
        prev_hash=prev_hash,
        hash=row_hash,
    )
    session.add(entry)
    session.commit()
    return entry


@dataclass
class IntegrityResult:
    ok: bool
    checked: int
    first_break_seq: int | None
    detail: str


def check_integrity(session: Session) -> IntegrityResult:
    entries = session.query(LedgerEntry).order_by(LedgerEntry.seq.asc()).all()
    expected_prev = GENESIS_HASH
    for entry in entries:
        if entry.prev_hash != expected_prev:
            return IntegrityResult(
                ok=False,
                checked=entry.seq,
                first_break_seq=entry.seq,
                detail=f"seq {entry.seq}: prev_hash does not match preceding entry's hash",
            )
        recomputed = _row_hash(
            entry.seq, entry.date.isoformat(), entry.payment_id, entry.amount, entry.nature, entry.prev_hash
        )
        if recomputed != entry.hash:
            return IntegrityResult(
                ok=False,
                checked=entry.seq,
                first_break_seq=entry.seq,
                detail=f"seq {entry.seq}: stored hash does not match recomputed hash (row was modified)",
            )
        expected_prev = entry.hash
    return IntegrityResult(ok=True, checked=len(entries), first_break_seq=None, detail="chain intact")
