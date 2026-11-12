"""SQLAlchemy models: Python classes that describe database TABLES.

Don't confuse these with app/schemas.py:
  - schemas.py = shape of data crossing the API (Pydantic)
  - models.py  = shape of data stored in PostgreSQL (SQLAlchemy)
"""

from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, String, false, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Every model inherits from this. It collects them into one catalog
    (Base.metadata) that Alembic will read in the next step."""


class Specialty(Base):
    __tablename__ = "specialties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    referral_required: Mapped[bool] = mapped_column(server_default=false())


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    specialty_id: Mapped[int] = mapped_column(
        ForeignKey("specialties.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(server_default=true())

    # Not a column! A Python-side shortcut: doctor.specialty gives the
    # Specialty object, so we don't write the join by hand.
    specialty: Mapped[Specialty] = relationship()


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    # No unique=True: many people share a name (see the Moshe Cohen discussion).
    name: Mapped[str] = mapped_column(String(100))


class Referral(Base):
    """A doctor's referral letter: lets ONE patient book ONE specialty,
    between valid_from and valid_until."""

    __tablename__ = "referrals"
    __table_args__ = (
        # A CHECK sees only this row's own columns - exactly this rule's case.
        # The explicit name matters: a violation error and future migrations
        # refer to the constraint by name.
        CheckConstraint("valid_until >= valid_from", name="ck_referrals_valid_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), index=True
    )
    specialty_id: Mapped[int] = mapped_column(
        ForeignKey("specialties.id", ondelete="RESTRICT")
    )
    valid_from: Mapped[date]  # a calendar date, no time of day
    valid_until: Mapped[date]
