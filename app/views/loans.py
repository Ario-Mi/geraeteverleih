from datetime import date, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from .. import services
from ..extensions import db
from ..models import Loan
from ..parsing import parse_date, parse_id
from .helpers import safe_next_url

bp = Blueprint("loans", __name__, url_prefix="/ausleihen")


def _render_form(values, errors, status=200):
    page = render_template(
        "loans/form.html",
        values=values,
        errors=errors,
        device_options=[
            (d.id, f"{d.name} ({d.inventory_number})") for d in services.list_available_devices()
        ],
        person_options=[(p.id, p.name) for p in services.list_persons()],
    )
    return page, status


@bp.get("/")
def index():
    status = request.args.get("status", "aktiv")
    if status not in services.LOAN_STATUS_FILTERS:
        status = "aktiv"
    return render_template(
        "loans/index.html",
        loans=services.list_loans(status),
        status=status,
        status_filters=services.LOAN_STATUS_FILTERS,
    )


@bp.route("/neu", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        form = request.form
        try:
            loan = services.create_loan(
                parse_id(form.get("device_id")),
                parse_id(form.get("person_id")),
                parse_date(form.get("loan_date")),
                parse_date(form.get("due_date")),
            )
        except services.ValidationError as error:
            return _render_form(form, error.errors, error.status_code)
        flash(
            f"„{loan.device.name}“ wurde an {loan.person.name} ausgeliehen "
            f"(Rückgabe geplant bis {loan.due_date.strftime('%d.%m.%Y')}).",
            "success",
        )
        return redirect(url_for("loans.index"))

    today = date.today()
    values = {
        "device_id": request.args.get("device_id", ""),
        "person_id": request.args.get("person_id", ""),
        "loan_date": today.isoformat(),
        "due_date": (today + timedelta(days=current_app.config["DEFAULT_LOAN_DAYS"])).isoformat(),
    }
    return _render_form(values, {})


@bp.post("/<int:loan_id>/rueckgabe")
def return_loan(loan_id):
    loan = db.get_or_404(Loan, loan_id)
    try:
        newly_returned = services.return_loan(loan)
    except services.ValidationError as error:
        flash(error.errors[services.FORM_ERROR], "error")
    else:
        if newly_returned:
            flash(f"Die Rückgabe von „{loan.device.name}“ wurde erfasst.", "success")
        else:
            flash(
                f"„{loan.device.name}“ wurde bereits zurückgegeben. Es wurde nichts geändert.",
                "info",
            )
    return redirect(safe_next_url(url_for("loans.index")))
