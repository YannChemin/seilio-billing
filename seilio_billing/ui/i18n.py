"""Display-label translations for the (English-valued) internal enums.

The enum members themselves (DocumentType.quote = "quote", ...) stay in
English since they are the stored/DB representation; only what is shown to
the user is translated here, via the app-wide string catalog in
`seilio_billing.i18n`.
"""
from __future__ import annotations

from seilio_billing.i18n import tr
from seilio_billing.models import DocumentType, DocumentStatus

_TYPE_KEYS = {
    DocumentType.quote: "doctype.quote",
    DocumentType.invoice: "doctype.invoice",
    DocumentType.bill: "doctype.bill",
}

_STATUS_KEYS = {
    DocumentStatus.draft: "docstatus.draft",
    DocumentStatus.sent: "docstatus.sent",
    DocumentStatus.paid: "docstatus.paid",
    DocumentStatus.cancelled: "docstatus.cancelled",
}


def type_label(t: DocumentType) -> str:
    return tr(_TYPE_KEYS.get(t, "doctype.quote"))


def status_label(s: DocumentStatus) -> str:
    return tr(_STATUS_KEYS.get(s, "docstatus.draft"))


def type_labels() -> dict[str, DocumentType]:
    """label -> DocumentType, in enum order, for combo boxes."""
    return {type_label(t): t for t in DocumentType}


def status_labels() -> dict[str, DocumentStatus]:
    """label -> DocumentStatus, in enum order, for combo boxes."""
    return {status_label(s): s for s in DocumentStatus}
