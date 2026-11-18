"""Eigene Flask-Befehle: init-db und seed-demo."""
import click
from flask.cli import with_appcontext

from .extensions import db
from .seed import seed_demo_data


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Legt die Tabellen an. Vorhandene Daten bleiben unverändert."""
    db.create_all()
    click.echo("Datenbank ist initialisiert.")


@click.command("seed-demo")
@with_appcontext
def seed_demo_command():
    """Lädt erfundene Beispieldaten (mehrfaches Ausführen ist unbedenklich)."""
    created = seed_demo_data()
    click.echo(
        "Beispieldaten geladen: "
        f"{created['devices']} Geräte, {created['persons']} Personen, "
        f"{created['loans']} Ausleihen neu angelegt."
    )
