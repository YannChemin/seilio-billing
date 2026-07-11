"""SQLAlchemy models for the Seilio Douar E.I. billing app.

Document unifies quotes/invoices/bills. LedgerEntry is the append-only
livre de recettes: rows are chained with a SHA-256 hash over the previous
row's hash, so any edit or deletion after the fact is detectable.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    Enum,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DocumentType(str, enum.Enum):
    quote = "quote"
    invoice = "invoice"
    bill = "bill"


class DocumentStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    paid = "paid"
    cancelled = "cancelled"


class Company(Base):
    """Single-row table: the issuer identity used on generated documents."""

    __tablename__ = "company"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(default="")
    address_line: Mapped[str] = mapped_column(default="")
    postal_code: Mapped[str] = mapped_column(default="")
    city: Mapped[str] = mapped_column(default="")
    country: Mapped[str] = mapped_column(default="France")
    siret: Mapped[str] = mapped_column(default="")
    vat_number: Mapped[str] = mapped_column(default="")
    email: Mapped[str] = mapped_column(default="")
    phone: Mapped[str] = mapped_column(default="")
    iban: Mapped[str] = mapped_column(default="")
    bic: Mapped[str] = mapped_column(default="")
    bank_name: Mapped[str] = mapped_column(default="")
    tiime_export_dir: Mapped[str] = mapped_column(default="")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(index=True)
    address_line: Mapped[str] = mapped_column(default="")
    postal_code: Mapped[str] = mapped_column(default="")
    city: Mapped[str] = mapped_column(default="")
    country: Mapped[str] = mapped_column(default="")
    vat_number: Mapped[str] = mapped_column(default="")
    contact_email: Mapped[str] = mapped_column(default="")

    # Contact person at the client, distinct from the client/company name itself.
    title: Mapped[str] = mapped_column(default="")  # Mr, Ms, Mrs, Dr, Prof...
    contact_name: Mapped[str] = mapped_column(default="")
    position: Mapped[str] = mapped_column(default="")  # job title / role
    phone_fixed: Mapped[str] = mapped_column(default="")
    phone_mobile: Mapped[str] = mapped_column(default="")
    website: Mapped[str] = mapped_column(default="")
    notes: Mapped[str] = mapped_column(default="")

    documents: Mapped[list["Document"]] = relationship(back_populates="client")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[DocumentType] = mapped_column(Enum(DocumentType))
    number: Mapped[str] = mapped_column(default="")
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"))
    issue_date: Mapped[dt.date] = mapped_column(default=dt.date.today)
    title: Mapped[str] = mapped_column(default="")
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.draft
    )
    currency: Mapped[str] = mapped_column(default="EUR")
    source_path: Mapped[str | None] = mapped_column(default=None)

    issued_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    pdf_export_path: Mapped[str | None] = mapped_column(default=None)
    facturx_export_path: Mapped[str | None] = mapped_column(default=None)
    tiime_deposited_at: Mapped[dt.datetime | None] = mapped_column(default=None)

    client: Mapped[Client | None] = relationship(back_populates="documents")
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    def total(self) -> float:
        return sum(li.amount() for li in self.line_items)


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    description: Mapped[str] = mapped_column(default="")
    quantity: Mapped[float] = mapped_column(default=1.0)
    unit: Mapped[str] = mapped_column(default="")
    unit_rate: Mapped[float] = mapped_column(default=0.0)
    vat_rate: Mapped[float] = mapped_column(default=0.0)

    document: Mapped[Document] = relationship(back_populates="line_items")

    def amount(self) -> float:
        return round(self.quantity * self.unit_rate, 2)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    paid_date: Mapped[dt.date] = mapped_column(default=dt.date.today)
    amount: Mapped[float] = mapped_column(default=0.0)
    method: Mapped[str] = mapped_column(default="")

    document: Mapped[Document] = relationship(back_populates="payments")
    ledger_entry: Mapped["LedgerEntry"] = relationship(
        back_populates="payment", uselist=False
    )


class LedgerEntry(Base):
    """The livre de recettes. Append-only: never UPDATE or DELETE a row.

    `hash` = SHA-256(prev_hash + canonical fields). Recomputing the chain
    and comparing to stored hashes reveals any tampering.
    """

    __tablename__ = "ledger_entries"
    __table_args__ = (UniqueConstraint("payment_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(unique=True)
    date: Mapped[dt.date] = mapped_column()
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"))
    amount: Mapped[float] = mapped_column()
    nature: Mapped[str] = mapped_column(default="")
    prev_hash: Mapped[str] = mapped_column(default="")
    hash: Mapped[str] = mapped_column()
    created_at: Mapped[dt.datetime] = mapped_column(
        default=lambda: dt.datetime.now(dt.timezone.utc)
    )

    payment: Mapped[Payment] = relationship(back_populates="ledger_entry")


class ImportStaging(Base):
    """Best-effort parsed rows from the legacy LaTeX archive, awaiting review."""

    __tablename__ = "import_staging"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_path: Mapped[str] = mapped_column()
    doc_type_guess: Mapped[str] = mapped_column(default="")
    client_name_guess: Mapped[str] = mapped_column(default="")
    date_guess: Mapped[str] = mapped_column(default="")
    title_guess: Mapped[str] = mapped_column(default="")
    vat_number_guess: Mapped[str] = mapped_column(default="")
    line_items_json: Mapped[str] = mapped_column(default="[]")
    confidence: Mapped[str] = mapped_column(default="low")  # low|medium|high
    flagged_reason: Mapped[str] = mapped_column(default="")
    reviewed: Mapped[bool] = mapped_column(default=False)
    committed_document_id: Mapped[int | None] = mapped_column(default=None)
