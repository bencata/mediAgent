"""SQLAlchemy models: Python classes that describe database TABLES.

Don't confuse these with app/schemas.py:
  - schemas.py = shape of data crossing the API (Pydantic)
  - models.py  = shape of data stored in PostgreSQL (SQLAlchemy)
"""

import enum
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    false,
    func,
    text,
    true,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ExcludeConstraint
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
        ForeignKey("specialties.id", ondelete="RESTRICT"), index=True
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


class Slot(Base):
    """One bookable time window with one doctor.

    Note what is NOT here: no is_available column. A slot is free when no
    ACTIVE appointment points at it (we derive it, we don't store it).
    """

    __tablename__ = "slots"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_slots_end_after_start"),
        # EXCLUSION constraint: no two rows may have
        #   the same doctor_id   (operator "=")   AND
        #   overlapping time ranges (operator "&&" means "overlaps").
        # tstzrange(start, end) is half-open [start, end): a slot ending at
        # 09:30 does NOT overlap one starting at 09:30, so back-to-back slots
        # are allowed. Two slots with the same start always overlap, so this
        # also replaces the old unique (doctor_id, start_time) rule.
        # Needs the PostgreSQL extension btree_gist (we add it in the migration).
        ExcludeConstraint(
            ("doctor_id", "="),
            (text("tstzrange(start_time, end_time)"), "&&"),
            using="gist",
            name="ex_slots_no_overlap",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="RESTRICT"))
    # TRAP: plain Mapped[datetime] means TIMESTAMP *without* time zone.
    # We must ask for timezone=True explicitly to get timestamptz.
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AppointmentStatus(str, enum.Enum):
    """Python-side enum. 'active' = the slot is taken; 'cancelled' = history only."""

    ACTIVE = "active"
    CANCELLED = "cancelled"


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        # The three race-proof rules. Each is a UNIQUE index that only looks at
        # rows where status = 'active' (a "partial" index), so cancelled rows
        # never block anyone. The database checks them atomically on INSERT.
        #   1. one active appointment per slot
        Index(
            "uq_appointments_active_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        #   2. a referral is consumed by at most one active appointment
        #      (NULL referral_ids are never equal to each other in PostgreSQL,
        #       so many referral-free appointments don't collide)
        Index(
            "uq_appointments_active_referral",
            "referral_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        #   3. demo policy: one active appointment per patient, specialty, day
        Index(
            "uq_appointments_active_patient_specialty_day",
            "patient_id",
            "specialty_id",
            "appointment_date",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id", ondelete="RESTRICT"))
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), index=True
    )
    # Optional: only specialties with referral_required need one. `| None`
    # makes the column nullable.
    referral_id: Mapped[int | None] = mapped_column(
        ForeignKey("referrals.id", ondelete="RESTRICT")
    )

    # SNAPSHOT columns: copied ONCE at booking time and never updated. They
    # exist so the database can enforce rule 3 by itself (an index can only
    # see columns of its own table).
    specialty_id: Mapped[int] = mapped_column(
        ForeignKey("specialties.id", ondelete="RESTRICT")
    )
    appointment_date: Mapped[date]  # the slot's date in the CLINIC's time zone

    # TRAP: by default SQLAlchemy stores the enum member NAMES ("ACTIVE").
    # values_callable makes it store the VALUES ("active") - which is what
    # the partial indexes above compare against.
    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(
            AppointmentStatus,
            name="appointment_status",
            values_callable=lambda e: [member.value for member in e],
        ),
        server_default="active",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
