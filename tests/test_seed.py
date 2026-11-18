"""Beispieldaten und Befehle: init-db und seed-demo."""
from sqlalchemy import func, select

from app import services
from app.extensions import db
from app.models import Device, Loan, Person
from app.seed import seed_demo_data

from conftest import TODAY


def counts():
    return tuple(
        db.session.scalar(select(func.count()).select_from(model)) for model in (Device, Person, Loan)
    )


def test_seed_creates_data_including_overdue_loans(app):
    created = seed_demo_data()

    assert created == {"devices": 7, "persons": 4, "loans": 5}
    assert services.count_overdue_loans(TODAY) == 2
    assert services.count_available_devices() > 0


def test_seeding_twice_creates_no_duplicates(app):
    seed_demo_data()
    before = counts()

    second = seed_demo_data()

    assert second == {"devices": 0, "persons": 0, "loans": 0}
    assert counts() == before


def test_reseeding_keeps_returns_made_by_the_user(app):
    seed_demo_data()
    loan = services.find_active_loan(db.session.scalar(select(Device.id).where(Device.inventory_number == "NB-001")))
    services.return_loan(loan, TODAY)

    seed_demo_data()

    assert services.count_active_loans() == 2  # die zurückgegebene Ausleihe kommt nicht wieder


def test_cli_commands_run_and_are_repeatable(app):
    runner = app.test_cli_runner()

    init_result = runner.invoke(args=["init-db"])
    first = runner.invoke(args=["seed-demo"])
    second = runner.invoke(args=["seed-demo"])

    assert init_result.exit_code == 0
    assert "initialisiert" in init_result.output
    assert "7 Geräte, 4 Personen, 5 Ausleihen neu angelegt" in first.output
    assert "0 Geräte, 0 Personen, 0 Ausleihen neu angelegt" in second.output
