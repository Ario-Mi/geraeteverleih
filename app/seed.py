"""Erfundene Beispieldaten. Mehrfaches Ausführen erzeugt keine Duplikate."""
from datetime import date, timedelta

from sqlalchemy import select

from .extensions import db
from .models import Device, Loan, Person

DEMO_DEVICES = [
    # (Inventarnummer, Bezeichnung, Kategorie, Beschreibung, archiviert)
    ("NB-001", "Notebook ThinkPad L14", "Notebook", "Standardgerät für Schulungen.", False),
    ("NB-002", "Notebook ThinkPad L14", "Notebook", None, False),
    ("BM-001", "Beamer Epson EB-W49", "Präsentation", "Inklusive HDMI-Kabel und Tasche.", False),
    ("KM-001", "Digitalkamera Canon EOS 250D", "Foto und Video", "Mit Stativ.", False),
    ("MK-001", "Konferenzmikrofon", "Audio", None, False),
    ("TB-001", "Tablet Samsung Galaxy Tab A8", "Tablet", "Display defekt, ausgemustert.", True),
    ("FC-001", "Flipchart mit Moderationskoffer", "Moderation", None, False),
]

DEMO_PERSONS = [
    # (Name, E-Mail). Die Adressen sind erfunden (.example ist reserviert).
    ("Anna Becker", "anna.becker@beispiel.example"),
    ("Mehmet Yilmaz", "mehmet.yilmaz@beispiel.example"),
    ("Julia Hoffmann", "julia.hoffmann@beispiel.example"),
    ("Thomas Richter", None),
]

DEMO_LOANS = [
    # (Inventarnr., Person, Ausleihe in Tagen ab heute, geplante Rückgabe, tatsächliche Rückgabe)
    ("NB-001", "Anna Becker", -3, 4, None),        # aktiv, pünktlich
    ("NB-002", "Mehmet Yilmaz", -14, -7, None),    # überfällig seit 7 Tagen
    ("BM-001", "Julia Hoffmann", -5, -1, None),    # überfällig seit 1 Tag
    ("KM-001", "Thomas Richter", -20, -13, -14),   # zurückgegeben
    ("TB-001", "Anna Becker", -60, -53, -55),      # Historie des archivierten Geräts
]


def seed_demo_data(today: date | None = None) -> dict[str, int]:
    """Legt fehlende Beispieldaten an und gibt zurück, wie viel neu angelegt wurde.

    Geräte werden über die Inventarnummer, Personen über den Namen erkannt.
    Beispielausleihen entstehen nur für Geräte, die noch keine Ausleihe haben;
    so bleiben Rückgaben, die man selbst erfasst hat, erhalten.
    """
    today = today or date.today()
    created = {"devices": 0, "persons": 0, "loans": 0}

    try:
        devices = {}
        for inventory_number, name, category, description, archived in DEMO_DEVICES:
            device = db.session.scalar(
                select(Device).where(Device.inventory_number == inventory_number)
            )
            if device is None:
                device = Device(
                    inventory_number=inventory_number,
                    name=name,
                    category=category,
                    description=description,
                    is_archived=archived,
                )
                db.session.add(device)
                created["devices"] += 1
            devices[inventory_number] = device

        persons = {}
        for name, email in DEMO_PERSONS:
            person = db.session.scalar(select(Person).where(Person.name == name))
            if person is None:
                person = Person(name=name, email=email)
                db.session.add(person)
                created["persons"] += 1
            persons[name] = person

        db.session.flush()  # vergibt die IDs, bevor die Ausleihen darauf verweisen

        for inventory_number, person_name, loan_offset, due_offset, return_offset in DEMO_LOANS:
            device = devices[inventory_number]
            has_history = db.session.scalar(
                select(Loan.id).where(Loan.device_id == device.id).limit(1)
            )
            if has_history is not None:
                continue
            db.session.add(
                Loan(
                    device_id=device.id,
                    person_id=persons[person_name].id,
                    loan_date=today + timedelta(days=loan_offset),
                    due_date=today + timedelta(days=due_offset),
                    returned_date=(
                        None if return_offset is None else today + timedelta(days=return_offset)
                    ),
                )
            )
            created["loans"] += 1

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return created
