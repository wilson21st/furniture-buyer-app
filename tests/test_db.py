from sqlmodel import Session

from app import db
from app.models import Customer


def test_engine_is_cached():
    db.reset_engine()
    engine = db.get_engine()
    assert engine is db.get_engine()


def test_reset_engine_rebuilds():
    first = db.get_engine()
    db.reset_engine()
    assert db.get_engine() is not first


def test_init_db_creates_tables_and_persists(initialized_db):
    with Session(initialized_db) as session:
        session.add(Customer(user_id="u001", name="Asha", local_balance=2500.0))
        session.commit()
    with Session(initialized_db) as session:
        loaded = session.get(Customer, "u001")
        assert loaded is not None
        assert loaded.name == "Asha"


def test_get_session_dependency_yields_session(initialized_db):
    gen = db.get_session()
    session = next(gen)
    try:
        assert isinstance(session, Session)
    finally:
        gen.close()


def test_check_connection_ok(initialized_db):
    assert db.check_connection() is True


def test_check_connection_false_on_broken_engine(monkeypatch):
    monkeypatch.setattr(db, "get_engine", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert db.check_connection() is False
