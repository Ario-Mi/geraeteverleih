from datetime import date

from flask import Blueprint, render_template

from .. import services

bp = Blueprint("main", __name__)


@bp.get("/")
def dashboard():
    today = date.today()
    return render_template(
        "dashboard.html",
        device_total=services.count_devices(),
        available_count=services.count_available_devices(),
        active_count=services.count_active_loans(),
        overdue_count=services.count_overdue_loans(today),
        overdue_loans=services.list_overdue_loans(today),
    )
