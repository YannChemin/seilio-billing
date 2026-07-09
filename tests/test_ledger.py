import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from seilio_billing.models import Base, Client, Document, DocumentType, Payment
from seilio_billing.ledger import append_ledger_entry, check_integrity, LedgerEntry


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def make_payment(session, amount=100.0):
    client = Client(name="Test Client")
    session.add(client)
    session.flush()
    doc = Document(type=DocumentType.invoice, client_id=client.id, issue_date=dt.date.today())
    session.add(doc)
    session.flush()
    payment = Payment(document_id=doc.id, paid_date=dt.date.today(), amount=amount, method="virement")
    session.add(payment)
    session.commit()
    return payment


def test_chain_grows_and_is_valid():
    session = make_session()
    for amount in (100.0, 250.5, 75.0):
        payment = make_payment(session, amount)
        append_ledger_entry(session, payment, nature="invoice payment")

    result = check_integrity(session)
    assert result.ok
    assert result.checked == 3


def test_tamper_detected_on_amount_change():
    session = make_session()
    payment = make_payment(session, 100.0)
    append_ledger_entry(session, payment, nature="invoice payment")
    payment2 = make_payment(session, 200.0)
    append_ledger_entry(session, payment2, nature="invoice payment")

    entry = session.query(LedgerEntry).filter_by(seq=1).one()
    entry.amount = 999.0  # simulate tampering directly on the row
    session.commit()

    result = check_integrity(session)
    assert not result.ok
    assert result.first_break_seq == 1


def test_tamper_detected_on_deleted_middle_entry():
    session = make_session()
    for amount in (10.0, 20.0, 30.0):
        payment = make_payment(session, amount)
        append_ledger_entry(session, payment, nature="invoice payment")

    middle = session.query(LedgerEntry).filter_by(seq=2).one()
    session.delete(middle)
    session.commit()

    result = check_integrity(session)
    assert not result.ok
