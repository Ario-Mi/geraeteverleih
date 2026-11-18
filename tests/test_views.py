"""Oberfläche: kompletter Ablauf, Fehlermeldungen, leere Zustände, CSRF."""
import re
from datetime import timedelta

from sqlalchemy import func, select

from app import services
from app.extensions import db
from app.models import Device, Loan, Person

from conftest import TODAY


def html(response):
    return response.get_data(as_text=True)


def test_dashboard_shows_empty_state_with_next_step(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Erstes Gerät anlegen" in html(response)


def test_list_pages_show_empty_states(client):
    assert "Noch keine Geräte" in html(client.get("/geraete/"))
    assert "Noch keine Personen" in html(client.get("/personen/"))
    assert "Keine Ausleihen vorhanden" in html(client.get("/ausleihen/"))
    assert "Kein Gerät verfügbar" in html(client.get("/ausleihen/neu"))


def test_normal_flow_from_device_to_loan_to_return(client):
    # 1. Gerät anlegen
    response = client.post(
        "/geraete/neu",
        data={"inventory_number": "NB-001", "name": "Notebook", "category": "Notebook"},
        follow_redirects=True,
    )
    assert "wurde angelegt" in html(response)
    device = db.session.scalar(select(Device))

    # 2. Person anlegen
    response = client.post(
        "/personen/neu", data={"name": "Anna Becker", "email": ""}, follow_redirects=True
    )
    assert "wurde angelegt" in html(response)
    person = db.session.scalar(select(Person))

    # 3. Gerät ausleihen
    response = client.post(
        "/ausleihen/neu",
        data={
            "device_id": device.id,
            "person_id": person.id,
            "loan_date": TODAY.isoformat(),
            "due_date": (TODAY + timedelta(days=7)).isoformat(),
        },
        follow_redirects=True,
    )
    assert "wurde an Anna Becker ausgeliehen" in html(response)
    assert "Ausgeliehen" in html(client.get(f"/geraete/{device.id}"))
    assert "Notebook" in html(client.get(f"/personen/{person.id}"))
    assert services.count_available_devices() == 0

    # 4. Rückgabe erfassen
    loan = db.session.scalar(select(Loan))
    response = client.post(f"/ausleihen/{loan.id}/rueckgabe", follow_redirects=True)
    assert "Rückgabe von" in html(response)
    db.session.expire_all()
    assert db.session.get(Loan, loan.id).returned_date == TODAY
    assert services.count_available_devices() == 1
    assert "Verfügbar" in html(client.get(f"/geraete/{device.id}"))


def test_repeated_return_submission_keeps_stored_date(client, device, person, make_loan):
    loan = make_loan(device, person, loan_date=TODAY - timedelta(days=5))
    first_date = TODAY - timedelta(days=2)
    services.return_loan(loan, first_date)

    response = client.post(f"/ausleihen/{loan.id}/rueckgabe", follow_redirects=True)

    assert "bereits zurückgegeben" in html(response)
    db.session.expire_all()
    assert db.session.get(Loan, loan.id).returned_date == first_date


def test_double_loan_shows_understandable_message(client, device, person, make_person, make_loan):
    make_loan(device, person)
    other = make_person("Mehmet Yilmaz")

    response = client.post(
        "/ausleihen/neu",
        data={
            "device_id": device.id,
            "person_id": other.id,
            "loan_date": TODAY.isoformat(),
            "due_date": TODAY.isoformat(),
        },
    )

    assert response.status_code == 409
    assert "bereits an Anna Becker ausgeliehen" in html(response)
    assert db.session.scalar(select(func.count()).select_from(Loan)) == 1


def test_invalid_dates_show_error_and_keep_input(client, device, person):
    response = client.post(
        "/ausleihen/neu",
        data={
            "device_id": device.id,
            "person_id": person.id,
            "loan_date": TODAY.isoformat(),
            "due_date": (TODAY - timedelta(days=1)).isoformat(),
        },
    )

    assert response.status_code == 400
    assert "darf nicht vor dem Ausleihdatum liegen" in html(response)
    assert f'value="{TODAY.isoformat()}"' in html(response)
    assert db.session.scalar(select(func.count()).select_from(Loan)) == 0


def test_garbage_date_is_rejected(client, device, person):
    response = client.post(
        "/ausleihen/neu",
        data={
            "device_id": device.id,
            "person_id": person.id,
            "loan_date": "2026-13-45",
            "due_date": "morgen",
        },
    )

    assert response.status_code == 400
    assert "gültiges Ausleihdatum" in html(response)


def test_device_form_shows_field_errors(client):
    response = client.post("/geraete/neu", data={"inventory_number": "", "name": "", "category": ""})

    assert response.status_code == 400
    assert "Bitte eine Inventarnummer angeben." in html(response)
    assert "Bitte eine Bezeichnung angeben." in html(response)


def test_overdue_loan_is_highlighted_with_text(client, device, person, make_loan):
    make_loan(device, person, loan_date=TODAY - timedelta(days=10), due_date=TODAY - timedelta(days=3))

    dashboard = html(client.get("/"))

    assert "überfällig seit 3 Tagen" in dashboard
    assert "row-overdue" in dashboard


def test_archived_device_has_no_loan_button(client, device):
    services.archive_device(device)

    page = html(client.get(f"/geraete/{device.id}"))

    assert "Archiviert" in page
    assert url_loan(device) not in page


def url_loan(device):
    return f"/ausleihen/neu?device_id={device.id}"


def test_unknown_device_returns_404(client):
    assert client.get("/geraete/999").status_code == 404


def test_changes_require_post(client, device):
    assert client.get(f"/geraete/{device.id}/archivieren").status_code == 405
    assert client.get("/ausleihen/1/rueckgabe").status_code == 405


def test_post_without_csrf_token_is_rejected(app_with_csrf):
    client = app_with_csrf.test_client()

    response = client.post("/personen/neu", data={"name": "Anna Becker"})

    assert response.status_code == 400
    assert db.session.scalar(select(func.count()).select_from(Person)) == 0


def test_post_with_csrf_token_is_accepted(app_with_csrf):
    client = app_with_csrf.test_client()
    form_page = html(client.get("/personen/neu"))
    token = re.search(r'name="csrf_token" value="([^"]+)"', form_page).group(1)

    response = client.post("/personen/neu", data={"name": "Anna Becker", "csrf_token": token})

    assert response.status_code == 302
    assert db.session.scalar(select(func.count()).select_from(Person)) == 1
