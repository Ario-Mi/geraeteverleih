"""Überfällige Ausleihen: geplantes Rückgabedatum vor heute und noch nicht zurückgegeben."""
from datetime import timedelta

from app import services

from conftest import TODAY


def test_loan_with_past_due_date_is_overdue(device, person, make_loan):
    loan = make_loan(
        device, person, loan_date=TODAY - timedelta(days=10), due_date=TODAY - timedelta(days=3)
    )

    assert loan.is_overdue(TODAY)
    assert loan.days_overdue(TODAY) == 3
    assert services.count_overdue_loans(TODAY) == 1
    assert [entry.id for entry in services.list_overdue_loans(TODAY)] == [loan.id]


def test_loan_due_today_is_not_overdue(device, person, make_loan):
    loan = make_loan(device, person, due_date=TODAY)

    assert not loan.is_overdue(TODAY)
    assert services.count_overdue_loans(TODAY) == 0


def test_loan_due_in_future_is_not_overdue(device, person, make_loan):
    make_loan(device, person, due_date=TODAY + timedelta(days=1))

    assert services.count_overdue_loans(TODAY) == 0


def test_returned_loan_is_not_overdue(device, person, make_loan):
    loan = make_loan(
        device, person, loan_date=TODAY - timedelta(days=10), due_date=TODAY - timedelta(days=3)
    )
    services.return_loan(loan, TODAY)

    assert not loan.is_overdue(TODAY)
    assert services.count_overdue_loans(TODAY) == 0


def test_overdue_depends_on_the_given_day(device, person, make_loan):
    make_loan(device, person, due_date=TODAY)

    assert services.count_overdue_loans(TODAY) == 0
    assert services.count_overdue_loans(TODAY + timedelta(days=1)) == 1


def test_dashboard_counts_are_calculated_from_loans(make_device, make_person, make_loan):
    person = make_person()
    overdue_device = make_device()
    active_device = make_device()
    make_device()  # bleibt verfügbar
    archived = make_device()
    services.archive_device(archived)
    make_loan(
        overdue_device, person, loan_date=TODAY - timedelta(days=9), due_date=TODAY - timedelta(days=2)
    )
    make_loan(active_device, person, due_date=TODAY + timedelta(days=5))

    assert services.count_available_devices() == 1  # archivierte zählen nicht
    assert services.count_active_loans() == 2
    assert services.count_overdue_loans(TODAY) == 1
