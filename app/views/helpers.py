from flask import request


def safe_next_url(default: str) -> str:
    """Rücksprungziel aus dem Formular, aber nur, wenn es ein interner Pfad ist.

    So kann ein manipuliertes Formular niemanden auf eine fremde Seite umleiten.
    """
    target = request.form.get("next", "")
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return default
