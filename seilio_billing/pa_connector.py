"""Plateforme Agréée (PA, formerly PDP) connector abstraction.

A local app cannot itself become a PA -- that requires DGFiP accreditation.
Reception (from 1 Sept 2026) and issuance (from 1 Sept 2027) of e-invoices
must go through a registered PA's infrastructure. This module defines the
integration point: once Yann has picked and registered with a specific PA
and has API credentials, a subclass of PAConnector wired to that PA's API
plugs in here. Until then, ManualPAConnector is the default: it just drops
Factur-X files into a local folder for manual upload to whatever portal is
in use.

See the Settings tab for the registration checklist.
"""
from __future__ import annotations

import abc
from pathlib import Path


class PAConnector(abc.ABC):
    """Base class for a Plateforme Agréée integration."""

    @abc.abstractmethod
    def send_invoice(self, facturx_pdf_bytes: bytes, filename: str) -> None:
        """Submit a generated Factur-X invoice to the PA for delivery."""

    @abc.abstractmethod
    def fetch_received_invoices(self) -> list[bytes]:
        """Retrieve e-invoices received from suppliers via the PA."""


class ManualPAConnector(PAConnector):
    """Default no-API-yet connector: writes Factur-X files to a watched
    export folder for the user to upload by hand to their chosen PA's web
    portal, and reads any files placed in an import folder as 'received'.
    """

    def __init__(self, export_dir: Path, import_dir: Path):
        self.export_dir = export_dir
        self.import_dir = import_dir
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.import_dir.mkdir(parents=True, exist_ok=True)

    def send_invoice(self, facturx_pdf_bytes: bytes, filename: str) -> None:
        (self.export_dir / filename).write_bytes(facturx_pdf_bytes)

    def fetch_received_invoices(self) -> list[bytes]:
        return [p.read_bytes() for p in sorted(self.import_dir.glob("*.pdf"))]


PA_REGISTRATION_CHECKLIST = [
    "Consult the official list of accredited platforms (Plateformes Agréées) "
    "at https://www.impots.gouv.fr/je-consulte-la-liste-des-plateformes-agreees",
    "Pick one that fits (several, e.g. Tiime, offer a free tier for micro-entrepreneurs) "
    "and register before 1 September 2026 to be ready for e-invoice reception.",
    "During registration you will get an 'adresse de facturation électronique' "
    "and, if you want programmatic access, API credentials.",
    "Once you have API credentials, implement a PAConnector subclass for that "
    "PA in seilio_billing/pa_connector.py and wire it into Settings in place of "
    "ManualPAConnector.",
    "Until then, use the Factur-X export tab to generate compliant invoices and "
    "the ManualPAConnector export folder to hand them to your chosen PA manually.",
]
