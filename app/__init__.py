"""Geräteverleih: kleine Flask-Anwendung zur Verwaltung von Geräteausleihen."""
import os
from datetime import date

from flask import Flask, render_template
from flask_wtf.csrf import CSRFError

from .config import Config
from .extensions import csrf, db


def create_app(test_config: dict | None = None) -> Flask:
    """Application Factory: erzeugt eine frische App (wichtig für isolierte Tests)."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)

    from . import models  # noqa: F401  (registriert die Tabellen an db.metadata)
    from .cli import init_db_command, seed_demo_command
    from .views import devices, loans, main, persons

    for module in (main, devices, persons, loans):
        app.register_blueprint(module.bp)

    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)

    @app.template_filter("datum")
    def format_date(value: date | None) -> str:
        return value.strftime("%d.%m.%Y") if value else "–"

    @app.context_processor
    def inject_today():
        return {"today": date.today()}

    @app.errorhandler(404)
    def not_found(error):
        return (
            render_template(
                "error.html",
                title="Seite nicht gefunden",
                message="Diese Seite oder dieser Eintrag existiert nicht.",
            ),
            404,
        )

    @app.errorhandler(CSRFError)
    def csrf_failed(error):
        return (
            render_template(
                "error.html",
                title="Sicherheitsprüfung fehlgeschlagen",
                message=(
                    "Das Formular konnte nicht bestätigt werden, vermutlich weil die Seite "
                    "zu lange offen war. Bitte laden Sie die Seite neu und versuchen Sie es erneut."
                ),
            ),
            400,
        )

    return app
