"""Rückgabe: Verfügbarkeit, Historie, Wiederholung."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import services
from app.extensions import db
from app.models import Loan

from conftest import TODAY


def test_return_stores_date_and_frees_device(device, person, make_loan):
    loan = make_loan(device, person)
    assert services.count_available_devices() == 0

    assert services.return_loan(loan, TODAY) is True

    assert loan.returned_date == TODAY
    assert services.find_active_loan(device.id) is None
    assert services.count_available_devices() == 1
    assert services.count_active_loans() == 0


def test_history_is_kept_after_return(device, person, make_loan):
    loan = make_loan(device, person)
    services.return_loan(loan, TODAY)

    history = services.list_loans_for_device(device.id)

    assert [entry.id for entry in history] == [loan.id]
    assert history[0].returned_date == TODAY


def test_repeated_return_does_not_change_stored_data(device, person, make_loan):
    loan = make_loan(device, person, loan_date=TODAY - timedelta(days=5))
    first_date = TODAY - timedelta(days=2)

    assert services.return_loan(loan, first_date) is True
    assert services.return_loan(loan, TODAY) is False

    db.session.expire_all()
    assert db.session.get(Loan, loan.id).returned_date == first_date
    assert db.session.scalar(select(func.count()).select_from(Loan)) == 1


def test_return_is_safe_if_another_request_returned_first(app, device, person, make_loan):
    """Das Objekt im Speicher ist veraltet (noch ohne Rückgabe), in der Datenbank
    steht die Rückgabe schon. Das bedingte UPDATE darf nichts überschreiben."""
    import sqlite3

    loan = make_loan(device, person, loan_date=TODAY - timedelta(days=5))
    assert loan.returned_date is None  # lädt das Objekt, jetzt ist es "veraltet"
    earlier = TODAY - timedelta(days=3)

    other_connection = sqlite3.connect(db.engine.url.database)
    other_connection.execute(
        "UPDATE loans SET returned_date = ? WHERE id = ?", (earlier.isoformat(), loan.id)
    )
    other_connection.commit()
    other_connection.close()

    assert services.return_loan(loan, TODAY) is False

    db.session.refresh(loan)
    assert loan.returned_date == earlier


def test_return_before_loan_date_is_rejected(device, person, make_loan):
    loan = make_loan(device, person, loan_date=TODAY)

    with pytest.raises(services.ValidationError):
        services.return_loan(loan, TODAY - timedelta(days=1))

    assert loan.returned_date is None
