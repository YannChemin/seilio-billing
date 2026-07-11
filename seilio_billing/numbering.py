"""Document numbering."""
from __future__ import annotations

import datetime as dt

from seilio_billing.models import Document


def generate_document_number(session, now: dt.datetime | None = None) -> str:
    """SD-YYYY-MM-DOY-HH-MM-SS ("SD" = Seilio Douar), unique per second. On
    the rare chance two documents are saved within the same second, append
    -2, -3, ... until the number is free."""
    now = now or dt.datetime.now()
    base = (
        f"SD-{now.year:04d}-{now.month:02d}-{now.timetuple().tm_yday:03d}"
        f"-{now.hour:02d}-{now.minute:02d}-{now.second:02d}"
    )
    number = base
    suffix = 2
    while session.query(Document).filter(Document.number == number).first() is not None:
        number = f"{base}-{suffix}"
        suffix += 1
    return number
