"""Gemeinsame Testausstattung.

Jeder Test bekommt eine eigene, frische SQLite-Datei in einem temporären Ordner.
Die echte Datenbank der Anwendung wird dadurch nie berührt.
"""
import itertools
from datetime import date, timedelta

import pytest

from app import create_app, services
from app.extensions import db

TODAY = date.today()


def _build_app(tmp_path, **overrides):
    config = {
        "TESTING": True,
        "SECRET_KEY": "test",
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
    }
    config.update(overrides)
    return create_app(config)


@pytest.fixture
def app(tmp_path):
    app = _build_app(tmp_path)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def app_with_csrf(tmp_path):
    app = _build_app(tmp_path, WTF_CSRF_ENABLED=True)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_device(app):
    counter = itertools.count(1)

    def _make(inventory_number=None, name="Notebook", category="Notebook", description=None):
        number = inventory_number or f"INV-{next(counter):03d}"
        return services.create_device(number, name, category, description)

    return _make


@pytest.fixture
def make_person(app):
    def _make(name="Anna Becker", email=None):
        return services.create_person(name, email)

    return _make


@pytest.fixture
def make_loan(app):
    def _make(device, person, loan_date=None, due_date=None):
        loan_date = loan_date or TODAY
        due_date = due_date or loan_date + timedelta(days=7)
        return services.create_loan(device.id, person.id, loan_date, due_date)

    return _make


@pytest.fixture
def device(make_device):
    return make_device("NB-001", "Notebook ThinkPad", "Notebook")


@pytest.fixture
def person(make_person):
    return make_person("Anna Becker", "anna@beispiel.example")
