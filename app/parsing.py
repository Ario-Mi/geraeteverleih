"""Kleine Helfer, um Formulartexte in Zahlen und Datumswerte umzuwandeln."""
from datetime import date


def parse_date(value: str | None) -> date | None:
    """Wandelt "JJJJ-MM-TT" (Format von <input type="date">) in ein Datum um.

    Ungültige oder leere Eingaben ergeben None; die Fehlermeldung erzeugt die
    Geschäftslogik, damit sie an einer Stelle steht.
    """
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def parse_id(value: str | None) -> int | None:
    try:
        return int((value or "").strip())
    except ValueError:
        return None
