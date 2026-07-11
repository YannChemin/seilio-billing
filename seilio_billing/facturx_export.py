"""Generate the quote/invoice/bill PDF and, for invoices, the Factur-X
(hybrid PDF + embedded EN16931/CII XML) e-invoice.

The PDF is built entirely in-app with reportlab's platypus layout engine —
no external LaTeX or other document tool is involved. `render_document_pdf`
produces the visual document (used for quotes, bills, previews, and as the
base PDF for invoices); `generate_facturx_pdf` embeds EN16931 CII XML into
that same PDF via the `factur-x` library so the result is ready to hand to
a Plateforme Agréée once one is wired up (see the Settings tab).
"""
from __future__ import annotations

import datetime as dt
import io

from facturx import generate_cii_xml, generate_from_binary
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    HRFlowable,
)

from seilio_billing.models import Company, Document, DocumentType

VAT_EXEMPTION_TEXT = "TVA non applicable, art. 293 B du CGI"

DOC_TITLES = {
    DocumentType.quote: "DEVIS",
    DocumentType.invoice: "FACTURE",
    DocumentType.bill: "NOTE",
}

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#6b6b6b")
ACCENT = colors.HexColor("#2f5d8a")
RULE = colors.HexColor("#d9d9d9")
HEAD_BG = colors.HexColor("#f2f4f6")


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "company": ParagraphStyle("company", fontName="Helvetica-Bold", fontSize=14, textColor=INK, leading=17),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, textColor=MUTED, leading=12),
        "doctitle": ParagraphStyle(
            "doctitle", fontName="Helvetica-Bold", fontSize=20, textColor=ACCENT, alignment=TA_RIGHT, leading=22
        ),
        "docmeta": ParagraphStyle("docmeta", fontName="Helvetica", fontSize=9, textColor=INK, alignment=TA_RIGHT, leading=13),
        "sectionlabel": ParagraphStyle("sectionlabel", fontName="Helvetica-Bold", fontSize=8.5, textColor=MUTED, leading=11),
        "client": ParagraphStyle("client", fontName="Helvetica-Bold", fontSize=10.5, textColor=INK, leading=13),
        "clientsmall": ParagraphStyle("clientsmall", fontName="Helvetica", fontSize=9, textColor=INK, leading=13),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=9, textColor=INK, leading=12),
        "cellhead": ParagraphStyle("cellhead", fontName="Helvetica-Bold", fontSize=8.5, textColor=MUTED, leading=11),
        "total": ParagraphStyle("total", fontName="Helvetica-Bold", fontSize=11, textColor=INK, alignment=TA_RIGHT),
        "footer": ParagraphStyle("footer", fontName="Helvetica", fontSize=8, textColor=MUTED, leading=11),
    }


def render_document_pdf(company: Company, document: Document) -> bytes:
    """Render a modern, single-page, factual PDF for any document type
    (quote, invoice, bill). Pure in-app layout — no external tool."""
    s = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title=f"{DOC_TITLES.get(document.type, 'DOCUMENT')} {document.number or document.id}",
    )
    story = []

    company_lines = [Paragraph(company.name, s["company"])]
    for line in (
        company.address_line,
        f"{company.postal_code} {company.city}, {company.country}".strip(", "),
        f"SIRET {company.siret}" + (f"  ·  TVA {company.vat_number}" if company.vat_number else ""),
        " · ".join(p for p in (company.email, company.phone) if p),
    ):
        if line and line.strip(" ,·"):
            company_lines.append(Paragraph(line, s["small"]))

    doc_title = DOC_TITLES.get(document.type, "DOCUMENT")
    meta_lines = [Paragraph(doc_title, s["doctitle"])]
    meta_lines.append(Spacer(1, 4))
    meta_lines.append(Paragraph(f"N&deg; {document.number or document.id}", s["docmeta"]))
    meta_lines.append(Paragraph(f"Date : {document.issue_date.isoformat()}", s["docmeta"]))
    if document.title:
        meta_lines.append(Paragraph(document.title, s["docmeta"]))

    header = Table(
        [[company_lines, meta_lines]],
        colWidths=[(doc.width) * 0.55, (doc.width) * 0.45],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header)
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1, color=RULE))
    story.append(Spacer(1, 12))

    client = document.client
    client_block = [Paragraph("DESTINATAIRE", s["sectionlabel"]), Spacer(1, 3)]
    if client:
        client_block.append(Paragraph(client.name, s["client"]))
        for line in (
            client.address_line,
            f"{client.postal_code} {client.city}".strip(),
            client.country,
            f"TVA {client.vat_number}" if client.vat_number else "",
            f"{client.title} {client.contact_name}".strip() if client.contact_name else "",
        ):
            if line and line.strip():
                client_block.append(Paragraph(line, s["clientsmall"]))
    else:
        client_block.append(Paragraph("—", s["clientsmall"]))
    story.append(Table([[client_block]], colWidths=[doc.width]))
    story.append(Spacer(1, 16))

    head = [
        Paragraph("DESCRIPTION", s["cellhead"]),
        Paragraph("QTÉ", s["cellhead"]),
        Paragraph("UNITÉ", s["cellhead"]),
        Paragraph("PRIX UNIT.", s["cellhead"]),
        Paragraph("MONTANT", s["cellhead"]),
    ]
    rows = [head]
    for li in document.line_items:
        rows.append(
            [
                Paragraph(li.description or "", s["cell"]),
                Paragraph(f"{li.quantity:g}", s["cell"]),
                Paragraph(li.unit or "", s["cell"]),
                Paragraph(f"{li.unit_rate:,.2f}".replace(",", " "), s["cell"]),
                Paragraph(f"{li.amount():,.2f}".replace(",", " "), s["cell"]),
            ]
        )
    col_widths = [doc.width * 0.46, doc.width * 0.10, doc.width * 0.12, doc.width * 0.16, doc.width * 0.16]
    line_table = Table(rows, colWidths=col_widths, repeatRows=1)
    line_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
                ("LINEBELOW", (0, 0), (-1, 0), 0.75, RULE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.5, RULE),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(line_table)
    story.append(Spacer(1, 10))

    total = document.total()
    total_table = Table(
        [
            ["Total HT", f"{total:,.2f} {document.currency}".replace(",", " ")],
            ["TVA", "0,00 " + document.currency],
            ["Total TTC", f"{total:,.2f} {document.currency}".replace(",", " ")],
        ],
        colWidths=[doc.width * 0.75, doc.width * 0.25],
    )
    total_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, 1), 9.5),
                ("TEXTCOLOR", (0, 0), (-1, 1), MUTED),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                ("FONTSIZE", (0, 2), (-1, 2), 12),
                ("TEXTCOLOR", (0, 2), (-1, 2), INK),
                ("LINEABOVE", (0, 2), (-1, 2), 0.75, RULE),
                ("TOPPADDING", (0, 2), (-1, 2), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(total_table)
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE))
    story.append(Spacer(1, 8))

    footer_lines = [VAT_EXEMPTION_TEXT]
    if document.type == DocumentType.invoice:
        footer_lines.append("Délai de paiement : 30 jours. Pénalité de retard : taux BCE + 10 points. Indemnité forfaitaire de recouvrement : 40 €.")
    if company.iban:
        footer_lines.append(f"IBAN {company.iban}" + (f"  ·  BIC {company.bic}" if company.bic else "") + (f"  ·  {company.bank_name}" if company.bank_name else ""))
    for line in footer_lines:
        story.append(Paragraph(line, s["footer"]))
        story.append(Spacer(1, 2))

    doc.build(story)
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
    pdf_bytes = render_document_pdf(company, document)
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
