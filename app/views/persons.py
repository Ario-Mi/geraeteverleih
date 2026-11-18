from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import services
from ..extensions import db
from ..models import Person

bp = Blueprint("persons", __name__, url_prefix="/personen")


def _render_form(person, values, errors, status=200):
    page = render_template("persons/form.html", person=person, values=values, errors=errors)
    return page, status


@bp.get("/")
def index():
    return render_template(
        "persons/index.html",
        persons=services.list_persons(),
        active_loans=services.active_loans_by_person(),
    )


@bp.route("/neu", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        form = request.form
        try:
            person = services.create_person(form.get("name"), form.get("email"))
        except services.ValidationError as error:
            return _render_form(None, form, error.errors, error.status_code)
        flash(f"Die Person „{person.name}“ wurde angelegt.", "success")
        return redirect(url_for("persons.detail", person_id=person.id))
    return _render_form(None, {}, {})


@bp.get("/<int:person_id>")
def detail(person_id):
    person = db.get_or_404(Person, person_id)
    history = services.list_loans_for_person(person.id)
    return render_template(
        "persons/detail.html",
        person=person,
        current_loans=[loan for loan in history if loan.is_active],
        past_loans=[loan for loan in history if not loan.is_active],
    )


@bp.route("/<int:person_id>/bearbeiten", methods=["GET", "POST"])
def edit(person_id):
    person = db.get_or_404(Person, person_id)
    if request.method == "POST":
        form = request.form
        try:
            services.update_person(person, form.get("name"), form.get("email"))
        except services.ValidationError as error:
            return _render_form(person, form, error.errors, error.status_code)
        flash("Die Änderungen wurden gespeichert.", "success")
        return redirect(url_for("persons.detail", person_id=person.id))
    values = {"name": person.name, "email": person.email or ""}
    return _render_form(person, values, {})
