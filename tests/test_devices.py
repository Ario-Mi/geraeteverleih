"""Geräte: Validierung, Archivierung, Suche und Filter."""
import pytest

from app import services

from conftest import TODAY


def test_create_device_trims_and_stores_values(app):
    device = services.create_device("  NB-100 ", " Notebook ", " Notebook ", "   ")

    assert device.inventory_number == "NB-100"
    assert device.name == "Notebook"
    assert device.description is None
    assert device.is_archived is False


def test_required_fields_are_validated(app):
    with pytest.raises(services.ValidationError) as info:
        services.create_device("", "", "", None)

    assert {"inventory_number", "name", "category"} <= set(info.value.errors)


def test_inventory_number_must_be_unique_ignoring_case(make_device):
    make_device("NB-001")

    with pytest.raises(services.ValidationError) as info:
        services.create_device("nb-001", "Anderes Gerät", "Notebook")

    assert "inventory_number" in info.value.errors


def test_update_device_may_keep_its_own_inventory_number(device):
    services.update_device(device, "NB-001", "Neuer Name", "Notebook", "Mit Tasche")

    assert device.name == "Neuer Name"
    assert device.description == "Mit Tasche"


def test_update_device_cannot_take_another_inventory_number(device, make_device):
    make_device("NB-002")

    with pytest.raises(services.ValidationError) as info:
        services.update_device(device, "NB-002", device.name, device.category)

    assert "inventory_number" in info.value.errors


def test_device_with_loan_history_can_be_archived(device, person, make_loan):
    loan = make_loan(device, person)
    services.return_loan(loan, TODAY)

    assert services.archive_device(device) is True

    assert device.is_archived
    assert services.list_available_devices() == []
    assert len(services.list_loans_for_device(device.id)) == 1  # Historie bleibt


def test_device_on_loan_cannot_be_archived(device, person, make_loan):
    make_loan(device, person)

    with pytest.raises(services.ConflictError):
        services.archive_device(device)

    assert not device.is_archived


def test_archiving_twice_changes_nothing(device):
    assert services.archive_device(device) is True
    assert services.archive_device(device) is False


def test_archived_device_can_be_restored(device):
    services.archive_device(device)

    assert services.restore_device(device) is True

    assert [d.id for d in services.list_available_devices()] == [device.id]


def test_search_by_name_and_inventory_number(make_device):
    notebook = make_device("NB-001", "Notebook ThinkPad", "Notebook")
    beamer = make_device("BM-001", "Beamer Epson", "Präsentation")

    assert services.list_devices("think") == [notebook]
    assert services.list_devices("bm-0") == [beamer]
    assert services.list_devices("gibt es nicht") == []


def test_search_treats_wildcards_as_plain_text(make_device):
    make_device("NB-001", "Notebook", "Notebook")

    assert services.list_devices("%") == []
    assert services.list_devices("_") == []


def test_status_filters(make_device, make_person, make_loan):
    person = make_person()
    free = make_device("A-1", "Frei", "Test")
    loaned = make_device("A-2", "Verliehen", "Test")
    archived = make_device("A-3", "Archiviert", "Test")
    make_loan(loaned, person)
    services.archive_device(archived)

    assert services.list_devices(status="alle") == [free, loaned]
    assert services.list_devices(status="verfuegbar") == [free]
    assert services.list_devices(status="ausgeliehen") == [loaned]
    assert services.list_devices(status="archiviert") == [archived]
