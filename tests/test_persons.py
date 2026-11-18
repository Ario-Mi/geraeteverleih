"""Personen: Validierung und Übersicht der aktuell ausgeliehenen Geräte."""
import pytest

from app import services

from conftest import TODAY


def test_person_without_email_is_allowed(app):
    person = services.create_person("Anna Becker", "  ")

    assert person.email is None


def test_name_is_required(app):
    with pytest.raises(services.ValidationError) as info:
        services.create_person("  ", None)

    assert "name" in info.value.errors


@pytest.mark.parametrize("email", ["keine-adresse", "a@b", "a b@c.de", "@c.de"])
def test_invalid_email_is_rejected(app, email):
    with pytest.raises(services.ValidationError) as info:
        services.create_person("Anna Becker", email)

    assert "email" in info.value.errors


def test_person_can_be_updated(person):
    services.update_person(person, "Anna Schmidt", "")

    assert person.name == "Anna Schmidt"
    assert person.email is None


def test_overview_shows_only_current_loans_of_a_person(
    person, make_person, make_device, make_loan
):
    other = make_person("Mehmet Yilmaz")
    first = make_device()
    second = make_device()
    third = make_device()
    returned = make_loan(first, person)
    services.return_loan(returned, TODAY)
    current = make_loan(second, person)
    make_loan(third, other)

    grouped = services.active_loans_by_person()

    assert [loan.id for loan in grouped[person.id]] == [current.id]
    assert len(grouped[other.id]) == 1
