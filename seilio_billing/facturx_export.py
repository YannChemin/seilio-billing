"""Generate a Factur-X (hybrid PDF + embedded EN16931/CII XML) invoice.

Renders a plain PDF with reportlab, builds a minimal 'basic' level CII data
dict (line items included, French VAT-franchise exemption noted), and
embeds the XML into the PDF via the `factur-x` library so the result is
ready to hand to a Plateforme Agréée once one is wired up (see the Settings
tab's PA setup panel).
"""
from __future__ import annotations

import datetime as dt
import io

from facturx import generate_cii_xml, generate_from_binary
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from seilio_billing.models import Company, Document

VAT_EXEMPTION_TEXT = "TVA non applicable, art. 293 B du CGI"


def _render_pdf(company: Company, document: Document) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 60

    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, company.name)
    y -= 20
    c.setFont("Helvetica", 9)
    for line in (
        company.address_line,
        f"{company.postal_code} {company.city}, {company.country}",
        f"SIRET: {company.siret}    VAT: {company.vat_number}",
    ):
        c.drawString(40, y, line)
        y -= 13

    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, f"FACTURE {document.number or document.id}")
    y -= 18
    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Date: {document.issue_date.isoformat()}")
    y -= 13
    if document.client:
        client = document.client
        c.drawString(40, y, f"Client: {client.name}")
        y -= 13
        if client.vat_number:
            c.drawString(40, y, f"VAT: {client.vat_number}")
            y -= 13

    y -= 15
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Description")
    c.drawString(300, y, "Qty")
    c.drawString(360, y, "Rate")
    c.drawString(440, y, "Amount")
    y -= 14
    c.setFont("Helvetica", 9)
    for li in document.line_items:
        c.drawString(40, y, (li.description or "")[:45])
        c.drawString(300, y, f"{li.quantity:g}")
        c.drawString(360, y, f"{li.unit_rate:.2f}")
        c.drawString(440, y, f"{li.amount():.2f}")
        y -= 13

    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(360, y, "Total EUR")
    c.drawString(440, y, f"{document.total():.2f}")
    y -= 20
    c.setFont("Helvetica", 8)
    c.drawString(40, y, VAT_EXEMPTION_TEXT)

    c.showPage()
    c.save()
    return buf.getvalue()


def _siret_to_siren(siret: str) -> str:
    digits = "".join(ch for ch in siret if ch.isdigit())
    return digits[:9] if len(digits) >= 9 else digits


def build_cii_data_dict(company: Company, document: Document) -> dict:
    client = document.client
    issue_dt = dt.datetime.combine(document.issue_date, dt.time.min)

    lines_ht = round(document.total(), 2)

    bg25 = []
    for idx, li in enumerate(document.line_items, start=1):
        bg25.append(
            {
                "BT-126": str(idx),
                "BT-153": li.description or f"Line {idx}",
                "BT-146": f"{li.unit_rate:.2f}",
                "BT-129": f"{li.quantity:g}",
                "BT-130": "C62",  # generic "unit" UN/CEFACT code
                "BT-131": f"{li.amount():.2f}",
                "BT-151": "E",  # VAT exempt
                "BT-152": "0.00",
            }
        )

    data_dict = {
        "BT-1": document.number or str(document.id),
        "BT-2": issue_dt,
        "BT-3": "380",  # commercial invoice
        "BT-5": document.currency or "EUR",
        "BT-9": issue_dt,
        "BT-72": issue_dt,  # actual delivery date = issue date (service billed as delivered)
        # Seller BG-4
        "BT-27": company.name,
        "BT-30": _siret_to_siren(company.siret),
        "BT-31": company.vat_number.replace(" ", ""),
        "BT-35": company.address_line,
        "BT-37": company.city,
        "BT-38": company.postal_code,
        "BT-40": "FR",
        "BT-43": company.email,
        # Buyer BG-7
        "BT-44": client.name if client else "",
        "BT-50": client.address_line if client else "",
        "BT-52": client.city if client else "",
        "BT-53": client.postal_code if client else "",
        "BT-55": (client.country if client and client.country else "FR"),
        # VAT breakdown: fully exempt (franchise en base, art. 293 B CGI)
        "BG-23": [
            {
                "BT-116": f"{lines_ht:.2f}",
                "BT-117": "0.00",
                "BT-118": "E",
                "BT-119": "0.00",
                "BT-120": VAT_EXEMPTION_TEXT,
            }
        ],
        "BT-106": f"{lines_ht:.2f}",
        "BT-109": f"{lines_ht:.2f}",
        "BT-110": "0.00",
        "BT-110-1": document.currency or "EUR",
        "BT-112": f"{lines_ht:.2f}",
        "BT-115": f"{lines_ht:.2f}",
        "BG-25": bg25,
    }
    if client and client.vat_number:
        data_dict["BT-48"] = client.vat_number.replace(" ", "")
    return data_dict


def generate_facturx_pdf(company: Company, document: Document, level: str = "en16931") -> bytes:
    """Return the bytes of a Factur-X-compliant PDF for the given invoice."""
    pdf_bytes = _render_pdf(company, document)
    data_dict = build_cii_data_dict(company, document)
    xml_bytes = generate_cii_xml(data_dict, level=level, check_xsd=True)
    facturx_pdf = generate_from_binary(
        pdf_bytes,
        xml_bytes,
        flavor="factur-x",
        level=level,
        check_xsd=True,
    )
    return facturx_pdf
