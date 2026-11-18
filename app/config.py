"""Konfiguration der Anwendung.

Werte können über Umgebungsvariablen überschrieben werden. Die Standardwerte
sind für die lokale Einzelbenutzerversion gedacht.
"""
import os


class Config:
    # Relative SQLite-Pfade legt Flask-SQLAlchemy im Ordner "instance/" ab.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///geraeteverleih.db")
    # Für den lokalen Betrieb reicht der Standardwert. Wird die Anwendung auf
    # einem Server betrieben, muss SECRET_KEY als Umgebungsvariable gesetzt werden.
    SECRET_KEY = os.environ.get("SECRET_KEY", "nur-fuer-lokale-entwicklung")
    # Vorschlag im Ausleihformular: geplante Rückgabe nach so vielen Tagen.
    DEFAULT_LOAN_DAYS = 7
