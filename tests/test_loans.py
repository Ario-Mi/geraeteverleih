"""Ausleihe: Datumsregeln, doppelte Ausleihe, archivierte Geräte."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import services
from app.extensions import db
from app.models import Loan

from conftest import TODAY


def loan_count():
    return db.session.scalar(select(func.count()).select_from(Loan))


def test_available_device_can_be_loaned(device, person):
    loan = services.create_loan(device.id, person.id, TODAY, TODAY + timedelta(days=7))

    assert loan.id is not None
    assert loan.is_active
    assert services.find_active_loan(device.id).person_id == person.id
    assert services.count_available_devices() == 0


def test_due_date_before_loan_date_is_rejected(device, person):
    with pytest.raises(services.ValidationError) as info:
        services.create_loan(device.id, person.id, TODAY, TODAY - timedelta(days=1))

    assert "due_date" in info.value.errors
    assert loan_count() == 0


def test_due_date_on_loan_date_is_allowed(device, person):
    services.create_loan(device.id, person.id, TODAY, TODAY)
    assert loan_count() == 1


@pytest.mark.parametrize(
    "loan_date, due_date, expected_field",
    [
        (None, TODAY, "loan_date"),
        (TODAY, None, "due_date"),
    ],
)
def test_missing_dates_are_rejected(device, person, loan_date, due_date, expected_field):
    with pytest.raises(services.ValidationError) as info:
        services.create_loan(device.id, person.id, loan_date, due_date)

    assert expected_field in info.value.errors
    assert loan_count() == 0


def test_missing_device_and_person_are_rejected(app):
    with pytest.raises(services.ValidationError) as info:
        services.create_loan(None, None, TODAY, TODAY)

    assert {"device_id", "person_id"} <= set(info.value.errors)


def test_unknown_device_is_rejected(person):
    with pytest.raises(services.ValidationError) as info:
        services.create_loan(9999, person.id, TODAY, TODAY)

    assert "device_id" in info.value.errors


def test_device_cannot_be_loaned_twice(device, person, make_person):
    services.create_loan(device.id, person.id, TODAY, TODAY + timedelta(days=7))
    other = make_person("Mehmet Yilmaz")

    with pytest.raises(services.ConflictError) as info:
        services.create_loan(device.id, other.id, TODAY, TODAY + timedelta(days=7))

    assert "Anna Becker" in info.value.errors["device_id"]
    assert loan_count() == 1


def test_database_itself_rejects_second_active_loan(device, person):
    """Die Regel gilt auch, wenn die Geschäftslogik umgangen wird."""
    db.session.add(Loan(device_id=device.id, person_id=person.id, loan_date=TODAY, due_date=TODAY))
    db.session.commit()

    db.session.add(Loan(device_id=device.id, person_id=person.id, loan_date=TODAY, due_date=TODAY))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    assert loan_count() == 1


def test_database_allows_new_loan_after_return(device, person):
    first = Loan(
        device_id=device.id, person_id=person.id, loan_date=TODAY, due_date=TODAY, returned_date=TODAY
    )
    second = Loan(device_id=device.id, person_id=person.id, loan_date=TODAY, due_date=TODAY)
    db.session.add_all([first, second])
    db.session.commit()

    assert loan_count() == 2


def test_database_rejects_due_date_before_loan_date(device, person):
    db.session.add(
        Loan(
            device_id=device.id,
            person_id=person.id,
            loan_date=TODAY,
            due_date=TODAY - timedelta(days=1),
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_conflict_during_commit_is_rolled_back_with_clear_message(
    monkeypatch, device, person, make_person
):
    """Simuliert eine gleichzeitige Anfrage: Die Vorabprüfung sieht noch keine
    Ausleihe, erst der Datenbankindex greift."""
    services.create_loan(device.id, person.id, TODAY, TODAY + timedelta(days=7))
    other = make_person("Mehmet Yilmaz")
    monkeypatch.setattr(services, "find_active_loan", lambda device_id: None)

    with pytest.raises(services.ConflictError) as info:
        services.create_loan(device.id, other.id, TODAY, TODAY + timedelta(days=7))

    assert "device_id" in info.value.errors
    assert loan_count() == 1
    assert services.count_active_loans() == 1  # Session ist nach dem Rollback weiter nutzbar


def test_archived_device_cannot_be_loaned(device, person):
    services.archive_device(device)

    with pytest.raises(services.ValidationError) as info:
        services.create_loan(device.id, person.id, TODAY, TODAY)

    assert "Archivierte" in info.value.errors["device_id"]
    assert loan_count() == 0


def test_device_can_be_loaned_again_after_return(device, person, make_person, make_loan):
    loan = make_loan(device, person)
    services.return_loan(loan)
    other = make_person("Mehmet Yilmaz")

    second = make_loan(device, other)

    assert second.id != loan.id
    assert services.find_active_loan(device.id).person_id == other.id
