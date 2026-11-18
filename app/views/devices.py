from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import services
from ..extensions import db
from ..models import Device

bp = Blueprint("devices", __name__, url_prefix="/geraete")


def _render_form(device, values, errors, status=200):
    page = render_template(
        "devices/form.html",
        device=device,
        values=values,
        errors=errors,
        categories=services.list_categories(),
    )
    return page, status


@bp.get("/")
def index():
    query = request.args.get("q", "").strip()
    status = request.args.get("status", "alle")
    if status not in services.DEVICE_STATUS_FILTERS:
        status = "alle"
    devices = services.list_devices(query, status)
    return render_template(
        "devices/index.html",
        devices=devices,
        active_loans=services.active_loans_by_device([d.id for d in devices]),
        query=query,
        status=status,
        status_filters=services.DEVICE_STATUS_FILTERS,
        device_total=services.count_devices(),
    )


@bp.route("/neu", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        form = request.form
        try:
            device = services.create_device(
                form.get("inventory_number"),
                form.get("name"),
                form.get("category"),
                form.get("description"),
            )
        except services.ValidationError as error:
            return _render_form(None, form, error.errors, error.status_code)
        flash(f"Das Gerät „{device.name}“ wurde angelegt.", "success")
        return redirect(url_for("devices.detail", device_id=device.id))
    return _render_form(None, {}, {})


@bp.get("/<int:device_id>")
def detail(device_id):
    device = db.get_or_404(Device, device_id)
    history = services.list_loans_for_device(device.id)
    active_loan = next((loan for loan in history if loan.is_active), None)
    return render_template(
        "devices/detail.html", device=device, history=history, active_loan=active_loan
    )


@bp.route("/<int:device_id>/bearbeiten", methods=["GET", "POST"])
def edit(device_id):
    device = db.get_or_404(Device, device_id)
    if request.method == "POST":
        form = request.form
        try:
            services.update_device(
                device,
                form.get("inventory_number"),
                form.get("name"),
                form.get("category"),
                form.get("description"),
            )
        except services.ValidationError as error:
            return _render_form(device, form, error.errors, error.status_code)
        flash("Die Änderungen wurden gespeichert.", "success")
        return redirect(url_for("devices.detail", device_id=device.id))
    values = {
        "inventory_number": device.inventory_number,
        "name": device.name,
        "category": device.category,
        "description": device.description or "",
    }
    return _render_form(device, values, {})


@bp.post("/<int:device_id>/archivieren")
def archive(device_id):
    device = db.get_or_404(Device, device_id)
    try:
        changed = services.archive_device(device)
    except services.ValidationError as error:
        flash(error.errors[services.FORM_ERROR], "error")
    else:
        if changed:
            flash(f"Das Gerät „{device.name}“ wurde archiviert.", "success")
        else:
            flash("Das Gerät ist bereits archiviert.", "info")
    return redirect(url_for("devices.detail", device_id=device_id))


@bp.post("/<int:device_id>/reaktivieren")
def restore(device_id):
    device = db.get_or_404(Device, device_id)
    if services.restore_device(device):
        flash(f"Das Gerät „{device.name}“ ist wieder aktiv.", "success")
    else:
        flash("Das Gerät ist nicht archiviert.", "info")
    return redirect(url_for("devices.detail", device_id=device_id))
