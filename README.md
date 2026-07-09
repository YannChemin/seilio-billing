# Seilio Billing

A local desktop app for **Seilio Douar E.I.** (Dr. Yann Chemin) to manage
client billing and stay ahead of France's e-invoicing reform, without
handing bookkeeping data to a SaaS vendor.

French law (loi n° 2026-103, art. 123) requires all businesses — including
micro-entrepreneurs/E.I. under the VAT franchise — to be able to **receive**
e-invoices via a DGFiP-accredited *Plateforme Agréée* (PA) from
**1 September 2026**, and to **issue** structured e-invoices (Factur-X/UBL)
plus e-reporting from **1 September 2027**. Separately, auto-entrepreneurs
already must keep a tamper-evident **livre des recettes** (register of
receipts) — a plain spreadsheet doesn't legally qualify.

A purely local app can't itself become a PA (that needs DGFiP
accreditation), so this tool focuses on what it *can* fully own: the livre
de recettes, invoice/quote/bill tracking, Factur-X generation, turnover
declaration help, and a connector seam for whichever PA you register with.

## Features

- **Dashboard** — YTD revenue encaissé, drafts needing action, plafond tracker
- **Clients** / **Documents** — quotes, invoices and bills with line items; marking a document paid records a `Payment`
- **Livre de recettes** — append-only ledger, SHA-256 hash-chained so any edit or deletion after the fact is detectable; CSV/PDF export for audits
- **Import from LaTeX** — best-effort parser for a legacy LaTeX invoice archive, staged for human review before anything becomes a real record
- **Factur-X export** — EN16931-compliant hybrid PDF+XML e-invoices, ready for the 2027 issuance mandate
- **Declarations** — monthly/quarterly revenue encaissé matching the Urssaf micro-entrepreneur CA declaration cadence
- **Settings** — company identity, plus a PA registration checklist and a `PAConnector` abstraction to wire in once you've picked a Plateforme Agréée

## Requirements

- Python ≥ 3.11
- System packages: `python3-pyqt6`, `python3-sqlalchemy`, `python3-lxml`
- `factur-x` and `reportlab` (installed into a local `.venv`, see below — not in Debian repos)

## Quick start

```bash
make venv    # create .venv (--system-site-packages) with factur-x/reportlab installed
make test    # run the test suite
make run     # launch the app
```

## Building the .deb

```bash
make deb           # produce seilio-billing_<version>_<arch>.deb
make install-deb   # sudo apt install it
make uninstall-deb # sudo apt remove it
```

The package vendors the pure-Python runtime deps not available via apt
(`facturx`, `pypdf`, `stdnum`, `reportlab`) under
`/usr/lib/seilio-billing/vendor`; PyQt6/SQLAlchemy/lxml come from apt via
`Depends`. See `Makefile` (`make help`) for the full target list.

## Data

The SQLite database lives at `~/.local/share/seilio-billing/seilio_billing.sqlite3`.
The ledger table (`ledger_entries`) is append-only by convention — the app
never issues `UPDATE`/`DELETE` against it — so its hash chain stays a valid
tamper-evidence proof as long as nothing edits the file out-of-band.

## Not included

This app cannot register you with a Plateforme Agréée or transmit invoices
to the PPF directory — that requires picking an accredited platform
yourself (see the in-app Settings tab for a checklist and the official list
at [impots.gouv.fr](https://www.impots.gouv.fr/je-consulte-la-liste-des-plateformes-agreees)).

## Support

If this tool is useful to you, tips are welcome:

[![Donate with PayPal](https://img.shields.io/badge/Donate-PayPal-00457C?logo=paypal&logoColor=white)](https://www.paypal.com/donate/?business=dr.yann.chemin@gmail.com&currency_code=EUR)

(GitHub also surfaces this via the repo's **Sponsor** button, configured in `.github/FUNDING.yml`.)

## License

[Unlicense](LICENSE) — public domain.
