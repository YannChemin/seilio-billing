"""Database engine/session setup. Single SQLite file under ~/.local/share."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from seilio_billing.models import Base

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "seilio-billing"
DB_PATH = DATA_DIR / "seilio_billing.sqlite3"

_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine(db_path: Path | None = None):
    global _engine
    if _engine is None:
        path = db_path or DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{path}", future=True)
    return _engine


def get_session_factory(db_path: Path | None = None) -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(db_path), expire_on_commit=False)
    return _SessionLocal


def _migrate_schema(engine) -> None:
    """Add columns introduced after a table already existed. SQLite's
    `CREATE TABLE IF NOT EXISTS` (what create_all uses) won't add columns to
    an existing table, so new Mapped fields need an explicit ALTER TABLE."""
    inspector = inspect(engine)
    if "clients" not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns("clients")}
    new_columns = {
        "title": "VARCHAR",
        "contact_name": "VARCHAR",
        "position": "VARCHAR",
        "phone_fixed": "VARCHAR",
        "phone_mobile": "VARCHAR",
        "website": "VARCHAR",
        "notes": "VARCHAR",
    }
    with engine.begin() as conn:
        for column, col_type in new_columns.items():
            if column not in existing_columns:
                conn.execute(text(f"ALTER TABLE clients ADD COLUMN {column} {col_type} DEFAULT ''"))

    if "company" in inspector.get_table_names():
        company_columns = {col["name"] for col in inspector.get_columns("company")}
        with engine.begin() as conn:
            if "tiime_export_dir" not in company_columns:
                conn.execute(text("ALTER TABLE company ADD COLUMN tiime_export_dir VARCHAR DEFAULT ''"))

    if "documents" in inspector.get_table_names():
        doc_columns = {col["name"] for col in inspector.get_columns("documents")}
        doc_new_columns = {
            "issued_at": "DATETIME",
            "pdf_export_path": "VARCHAR",
            "facturx_export_path": "VARCHAR",
            "tiime_deposited_at": "DATETIME",
        }
        with engine.begin() as conn:
            for column, col_type in doc_new_columns.items():
                if column not in doc_columns:
                    conn.execute(text(f"ALTER TABLE documents ADD COLUMN {column} {col_type}"))


def init_db(db_path: Path | None = None) -> None:
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    _migrate_schema(engine)


def new_session(db_path: Path | None = None) -> Session:
    return get_session_factory(db_path)()
