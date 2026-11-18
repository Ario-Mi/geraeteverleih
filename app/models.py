"""Datenmodell: Geräte, Personen und Ausleihen.

Die Verfügbarkeit eines Geräts wird bewusst NICHT als Spalte gespeichert,
sondern aus den Ausleihen berechnet: Ein Gerät ist ausgeliehen, solange es
eine Ausleihe ohne Rückgabedatum gibt.
"""
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


class Device(db.Model):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_number: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(default=False, server_default=text("0"))

    loans: Mapped[list["Loan"]] = relationship(
        back_populates="device",
        order_by="Loan.loan_date.desc(), Loan.id.desc()",
    )

    def __repr__(self) -> str:
        return f"<Device {self.inventory_number}>"


class Person(db.Model):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254))

    loans: Mapped[list["Loan"]] = relationship(
        back_populates="person",
        order_by="Loan.loan_date.desc(), Loan.id.desc()",
    )

    def __repr__(self) -> str:
        return f"<Person {self.name}>"


class Loan(db.Model):
    __tablename__ = "loans"
    __table_args__ = (
        # Regel 1: Rückgabe nicht vor Ausleihe (auch ohne Anwendung gültig).
        CheckConstraint("due_date >= loan_date", name="ck_loans_due_not_before_loan"),
        CheckConstraint(
            "returned_date IS NULL OR returned_date >= loan_date",
            name="ck_loans_returned_not_before_loan",
        ),
        # Regel 2: Höchstens eine aktive Ausleihe pro Gerät. Ein partieller
        # eindeutiger Index gilt nur für Zeilen ohne Rückgabedatum. Dadurch kann
        # auch bei gleichzeitigen Anfragen nie eine zweite aktive Ausleihe
        # entstehen: die Datenbank lehnt sie ab.
        Index(
            "uq_loans_one_active_per_device",
            "device_id",
            unique=True,
            sqlite_where=text("returned_date IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), index=True)
    loan_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    returned_date: Mapped[date | None] = mapped_column(Date)

    device: Mapped[Device] = relationship(back_populates="loans")
    person: Mapped[Person] = relationship(back_populates="loans")

    @property
    def is_active(self) -> bool:
        return self.returned_date is None

    def is_overdue(self, today: date) -> bool:
        """Überfällig: geplantes Rückgabedatum liegt vor heute, keine Rückgabe."""
        return self.is_active and self.due_date < today

    def days_overdue(self, today: date) -> int:
        return (today - self.due_date).days if self.is_overdue(today) else 0

    def __repr__(self) -> str:
        return f"<Loan device={self.device_id} person={self.person_id}>"
