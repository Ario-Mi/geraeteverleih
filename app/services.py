"""Geschäftslogik: alle Regeln und Datenbankabfragen an einer Stelle.

Die Views (Flask-Routen) lesen nur Formulardaten, rufen diese Funktionen auf und
zeigen das Ergebnis an. Dadurch lassen sich die Regeln ohne Browser testen.

Fehlerkonzept: Verletzt eine Eingabe eine Regel, wird ein ValidationError (oder
ein ConflictError bei Konflikten mit dem Datenbankstand) mit Meldungen pro Feld
ausgelöst. Der Schlüssel FORM_ERROR steht für Meldungen, die zum ganzen Formular
gehören.
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from .extensions import db
from .models import Device, Loan, Person

FORM_ERROR = "_form"

DEVICE_STATUS_FILTERS = {
    "alle": "Alle (ohne archivierte)",
    "verfuegbar": "Verfügbar",
    "ausgeliehen": "Ausgeliehen",
    "archiviert": "Archiviert",
}
LOAN_STATUS_FILTERS = {
    "aktiv": "Aktive",
    "ueberfaellig": "Überfällige",
    "zurueckgegeben": "Zurückgegebene",
    "alle": "Alle",
}

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ValidationError(Exception):
    """Eingabe verletzt eine Regel. `errors` ordnet Feldnamen eine Meldung zu."""

    status_code = 400

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(errors.values()))
        self.errors = errors


class ConflictError(ValidationError):
    """Die Eingabe ist für sich gültig, steht aber im Konflikt mit dem Datenbankstand."""

    status_code = 409


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _commit_or_conflict(conflict_errors: dict[str, str]) -> None:
    """Speichert die Transaktion. Bei einem Datenbankkonflikt: Rollback + Meldung."""
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ConflictError(conflict_errors) from exc


# --------------------------------------------------------------------------
# Geräte
# --------------------------------------------------------------------------

def _validate_device_fields(inventory_number, name, category, description, device_id=None):
    inventory_number = _clean(inventory_number)
    name = _clean(name)
    category = _clean(category)
    description = _clean(description)
    errors: dict[str, str] = {}

    if not inventory_number:
        errors["inventory_number"] = "Bitte eine Inventarnummer angeben."
    elif len(inventory_number) > 50:
        errors["inventory_number"] = "Die Inventarnummer darf höchstens 50 Zeichen lang sein."
    else:
        stmt = select(Device.id).where(
            func.lower(Device.inventory_number) == inventory_number.lower()
        )
        if device_id is not None:
            stmt = stmt.where(Device.id != device_id)
        if db.session.scalar(stmt.limit(1)) is not None:
            errors["inventory_number"] = "Diese Inventarnummer ist bereits vergeben."

    if not name:
        errors["name"] = "Bitte eine Bezeichnung angeben."
    elif len(name) > 120:
        errors["name"] = "Die Bezeichnung darf höchstens 120 Zeichen lang sein."

    if not category:
        errors["category"] = "Bitte eine Kategorie angeben."
    elif len(category) > 80:
        errors["category"] = "Die Kategorie darf höchstens 80 Zeichen lang sein."

    if len(description) > 1000:
        errors["description"] = "Die Beschreibung darf höchstens 1000 Zeichen lang sein."

    if errors:
        raise ValidationError(errors)
    return inventory_number, name, category, description or None


def create_device(inventory_number, name, category, description=None) -> Device:
    inventory_number, name, category, description = _validate_device_fields(
        inventory_number, name, category, description
    )
    device = Device(
        inventory_number=inventory_number,
        name=name,
        category=category,
        description=description,
    )
    db.session.add(device)
    # Die Datenbank hat ein UNIQUE auf der Inventarnummer als letzte Sicherung.
    _commit_or_conflict({"inventory_number": "Diese Inventarnummer ist bereits vergeben."})
    return device


def update_device(device: Device, inventory_number, name, category, description=None) -> Device:
    inventory_number, name, category, description = _validate_device_fields(
        inventory_number, name, category, description, device_id=device.id
    )
    device.inventory_number = inventory_number
    device.name = name
    device.category = category
    device.description = description
    _commit_or_conflict({"inventory_number": "Diese Inventarnummer ist bereits vergeben."})
    return device


def archive_device(device: Device) -> bool:
    """Archiviert ein Gerät. Gibt False zurück, wenn es schon archiviert war."""
    if device.is_archived:
        return False
    if find_active_loan(device.id) is not None:
        raise ConflictError(
            {FORM_ERROR: "Das Gerät ist noch ausgeliehen. Bitte zuerst die Rückgabe erfassen."}
        )
    device.is_archived = True
    db.session.commit()
    return True


def restore_device(device: Device) -> bool:
    """Hebt die Archivierung auf. Gibt False zurück, wenn das Gerät nicht archiviert war."""
    if not device.is_archived:
        return False
    device.is_archived = False
    db.session.commit()
    return True


# --------------------------------------------------------------------------
# Personen
# --------------------------------------------------------------------------

def _validate_person_fields(name, email):
    name = _clean(name)
    email = _clean(email)
    errors: dict[str, str] = {}

    if not name:
        errors["name"] = "Bitte einen Namen angeben."
    elif len(name) > 120:
        errors["name"] = "Der Name darf höchstens 120 Zeichen lang sein."

    if email:
        if len(email) > 254 or not EMAIL_PATTERN.match(email):
            errors["email"] = "Bitte eine gültige E-Mail-Adresse angeben oder das Feld leer lassen."

    if errors:
        raise ValidationError(errors)
    return name, email or None


def create_person(name, email=None) -> Person:
    name, email = _validate_person_fields(name, email)
    person = Person(name=name, email=email)
    db.session.add(person)
    db.session.commit()
    return person


def update_person(person: Person, name, email=None) -> Person:
    name, email = _validate_person_fields(name, email)
    person.name = name
    person.email = email
    db.session.commit()
    return person


# --------------------------------------------------------------------------
# Ausleihe und Rückgabe
# --------------------------------------------------------------------------

def find_active_loan(device_id: int) -> Loan | None:
    """Die aktive Ausleihe (ohne Rückgabedatum) eines Geräts oder None."""
    stmt = (
        select(Loan)
        .where(Loan.device_id == device_id, Loan.returned_date.is_(None))
        .options(joinedload(Loan.person))
    )
    return db.session.scalars(stmt).first()


def create_loan(
    device_id: int | None,
    person_id: int | None,
    loan_date: date | None,
    due_date: date | None,
) -> Loan:
    errors: dict[str, str] = {}

    if device_id is None:
        errors["device_id"] = "Bitte ein Gerät auswählen."
    if person_id is None:
        errors["person_id"] = "Bitte eine Person auswählen."
    if loan_date is None:
        errors["loan_date"] = "Bitte ein gültiges Ausleihdatum angeben."
    if due_date is None:
        errors["due_date"] = "Bitte ein gültiges geplantes Rückgabedatum angeben."
    elif loan_date is not None and due_date < loan_date:
        errors["due_date"] = "Das geplante Rückgabedatum darf nicht vor dem Ausleihdatum liegen."

    device = db.session.get(Device, device_id) if device_id is not None else None
    person = db.session.get(Person, person_id) if person_id is not None else None
    if device_id is not None:
        if device is None:
            errors["device_id"] = "Das ausgewählte Gerät existiert nicht."
        elif device.is_archived:
            errors["device_id"] = "Archivierte Geräte können nicht ausgeliehen werden."
    if person_id is not None and person is None:
        errors["person_id"] = "Die ausgewählte Person existiert nicht."

    if errors:
        raise ValidationError(errors)

    # Erste Prüfung für eine verständliche Meldung ...
    active_loan = find_active_loan(device.id)
    if active_loan is not None:
        raise ConflictError(
            {
                "device_id": (
                    f"Dieses Gerät ist bereits an {active_loan.person.name} ausgeliehen. "
                    "Bitte zuerst die Rückgabe erfassen."
                )
            }
        )

    loan = Loan(
        device_id=device.id,
        person_id=person.id,
        loan_date=loan_date,
        due_date=due_date,
    )
    db.session.add(loan)
    # ... und die eigentliche Sicherung: Der partielle eindeutige Index lässt bei
    # gleichzeitigen Anfragen nur eine aktive Ausleihe zu. Die zweite Anfrage
    # scheitert hier mit einem IntegrityError und wird zurückgerollt.
    _commit_or_conflict(
        {
            "device_id": (
                "Dieses Gerät wurde gerade von einer anderen Anfrage ausgeliehen. "
                "Bitte die Seite neu laden."
            )
        }
    )
    return loan


def return_loan(loan: Loan, returned_on: date | None = None) -> bool:
    """Erfasst die Rückgabe. True = jetzt zurückgegeben, False = war schon zurückgegeben.

    Die Funktion ist idempotent: Ein zweiter Aufruf ändert das gespeicherte
    Rückgabedatum nicht. Das stellt auch die Datenbankabfrage sicher: Das UPDATE
    greift nur, solange returned_date noch leer ist.
    """
    returned_on = returned_on or date.today()

    if loan.returned_date is not None:
        return False
    if returned_on < loan.loan_date:
        raise ValidationError(
            {FORM_ERROR: "Das Rückgabedatum darf nicht vor dem Ausleihdatum liegen."}
        )

    result = db.session.execute(
        update(Loan)
        .where(Loan.id == loan.id, Loan.returned_date.is_(None))
        .values(returned_date=returned_on)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 1:
        db.session.commit()  # expire_on_commit lädt das Objekt danach neu
        return True

    # Eine andere Anfrage war schneller: nichts ändern.
    db.session.rollback()
    return False


# --------------------------------------------------------------------------
# Abfragen für Übersicht, Listen und Suche
# --------------------------------------------------------------------------

def _has_active_loan_clause():
    """Teilbedingung: Zum Gerät der äußeren Abfrage existiert eine aktive Ausleihe."""
    return (
        select(Loan.id)
        .where(Loan.device_id == Device.id, Loan.returned_date.is_(None))
        .exists()
    )


def count_devices() -> int:
    return db.session.scalar(select(func.count()).select_from(Device)) or 0


def count_available_devices() -> int:
    """Verfügbar = nicht archiviert und ohne aktive Ausleihe (berechnet, nicht gespeichert)."""
    stmt = (
        select(func.count())
        .select_from(Device)
        .where(Device.is_archived.is_(False), ~_has_active_loan_clause())
    )
    return db.session.scalar(stmt) or 0


def count_active_loans() -> int:
    stmt = select(func.count()).select_from(Loan).where(Loan.returned_date.is_(None))
    return db.session.scalar(stmt) or 0


def count_overdue_loans(today: date | None = None) -> int:
    today = today or date.today()
    stmt = (
        select(func.count())
        .select_from(Loan)
        .where(Loan.returned_date.is_(None), Loan.due_date < today)
    )
    return db.session.scalar(stmt) or 0


def list_overdue_loans(today: date | None = None) -> list[Loan]:
    today = today or date.today()
    stmt = (
        select(Loan)
        .where(Loan.returned_date.is_(None), Loan.due_date < today)
        .options(joinedload(Loan.device), joinedload(Loan.person))
        .order_by(Loan.due_date, Loan.id)
    )
    return list(db.session.scalars(stmt))


def list_devices(query: str = "", status: str = "alle") -> list[Device]:
    stmt = select(Device).order_by(func.lower(Device.name), Device.inventory_number)

    query = _clean(query)
    if query:
        stmt = stmt.where(
            or_(
                Device.name.icontains(query, autoescape=True),
                Device.inventory_number.icontains(query, autoescape=True),
            )
        )

    if status == "archiviert":
        stmt = stmt.where(Device.is_archived.is_(True))
    elif status == "verfuegbar":
        stmt = stmt.where(Device.is_archived.is_(False), ~_has_active_loan_clause())
    elif status == "ausgeliehen":
        stmt = stmt.where(Device.is_archived.is_(False), _has_active_loan_clause())
    else:
        stmt = stmt.where(Device.is_archived.is_(False))

    return list(db.session.scalars(stmt))


def list_available_devices() -> list[Device]:
    return list_devices(status="verfuegbar")


def list_categories() -> list[str]:
    stmt = select(Device.category).distinct().order_by(Device.category)
    return list(db.session.scalars(stmt))


def active_loans_by_device(device_ids: list[int]) -> dict[int, Loan]:
    stmt = (
        select(Loan)
        .where(Loan.returned_date.is_(None), Loan.device_id.in_(device_ids))
        .options(joinedload(Loan.person))
    )
    return {loan.device_id: loan for loan in db.session.scalars(stmt)}


def list_persons() -> list[Person]:
    return list(db.session.scalars(select(Person).order_by(func.lower(Person.name), Person.id)))


def active_loans_by_person() -> dict[int, list[Loan]]:
    stmt = (
        select(Loan)
        .where(Loan.returned_date.is_(None))
        .options(joinedload(Loan.device))
        .order_by(Loan.due_date, Loan.id)
    )
    grouped: dict[int, list[Loan]] = {}
    for loan in db.session.scalars(stmt):
        grouped.setdefault(loan.person_id, []).append(loan)
    return grouped


def list_loans_for_device(device_id: int) -> list[Loan]:
    stmt = (
        select(Loan)
        .where(Loan.device_id == device_id)
        .options(joinedload(Loan.person))
        .order_by(Loan.loan_date.desc(), Loan.id.desc())
    )
    return list(db.session.scalars(stmt))


def list_loans_for_person(person_id: int) -> list[Loan]:
    stmt = (
        select(Loan)
        .where(Loan.person_id == person_id)
        .options(joinedload(Loan.device))
        .order_by(Loan.loan_date.desc(), Loan.id.desc())
    )
    return list(db.session.scalars(stmt))


def list_loans(status: str = "aktiv", today: date | None = None) -> list[Loan]:
    today = today or date.today()
    stmt = select(Loan).options(joinedload(Loan.device), joinedload(Loan.person))

    if status == "ueberfaellig":
        stmt = stmt.where(Loan.returned_date.is_(None), Loan.due_date < today)
        stmt = stmt.order_by(Loan.due_date, Loan.id)
    elif status == "zurueckgegeben":
        stmt = stmt.where(Loan.returned_date.is_not(None))
        stmt = stmt.order_by(Loan.returned_date.desc(), Loan.id.desc())
    elif status == "alle":
        stmt = stmt.order_by(Loan.loan_date.desc(), Loan.id.desc())
    else:
        stmt = stmt.where(Loan.returned_date.is_(None)).order_by(Loan.due_date, Loan.id)

    return list(db.session.scalars(stmt))
