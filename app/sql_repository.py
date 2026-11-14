"""SQL repository: the same job as InMemoryRepository, but data lives in PostgreSQL.

Two naming worlds meet here, so we keep them apart:
    m.Slot       = SQLAlchemy MODEL (a table row, app/db/models.py)
    schemas.Slot = Pydantic SCHEMA  (what the service and the API speak)
Every method takes/returns schemas, so the service layer stays storage-ignorant.

Rule for this layer is unchanged: store and fetch, no business rules.
The one thing it MUST do is translate low-level database errors into a
storage-level error the service can understand (see ConstraintViolation).
"""

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import schemas
from app.config import CLINIC_TZ
from app.db import models as m


class ConstraintViolation(Exception):
    """The database refused a write because a constraint would be broken.

    Deliberately NOT a DomainError: it carries a storage detail (the constraint
    name). The service decides what it means in business terms. If the service
    forgets to handle one, it surfaces as a 500 instead of a wrong 4xx.
    """

    def __init__(self, constraint: str | None) -> None:
        super().__init__(f"Constraint violated: {constraint}")
        self.constraint = constraint


class SqlRepository:
    def __init__(self, session: Session) -> None:
        # The session is passed in (not created here): it belongs to the
        # request, so everything in one request shares ONE transaction.
        self._session = session

    # ---- reads -------------------------------------------------------

    def list_specialties(self) -> list[schemas.Specialty]:
        rows = self._session.scalars(select(m.Specialty).order_by(m.Specialty.id))
        return [schemas.Specialty(id=r.id, name=r.name) for r in rows]

    def get_patient(self, patient_id: int) -> schemas.Patient | None:
        row = self._session.get(m.Patient, patient_id)  # None if missing
        return schemas.Patient(id=row.id, name=row.name) if row else None

    def get_slot(self, slot_id: int) -> schemas.Slot | None:
        row = self._session.execute(
            self._slots_query().where(m.Slot.id == slot_id)
        ).first()
        return _to_slot(*row) if row else None

    def list_slots(
        self,
        specialty_id: int | None = None,
        only_available: bool = True,
    ) -> list[schemas.Slot]:
        """Slots sorted by time, optionally filtered by specialty."""
        query = self._slots_query()
        if specialty_id is not None:
            query = query.join(m.Doctor, m.Doctor.id == m.Slot.doctor_id).where(
                m.Doctor.specialty_id == specialty_id
            )
        if only_available:
            query = query.where(~_is_taken())
        rows = self._session.execute(query.order_by(m.Slot.start_time, m.Slot.id))
        return [_to_slot(slot, taken) for slot, taken in rows]

    def list_appointments_for_patient(self, patient_id: int) -> list[schemas.Appointment]:
        # Only ACTIVE ones: cancelled rows are history, not "my appointments".
        rows = self._session.execute(
            select(m.Appointment, m.Slot.doctor_id)
            .join(m.Slot, m.Slot.id == m.Appointment.slot_id)
            .where(
                m.Appointment.patient_id == patient_id,
                m.Appointment.status == m.AppointmentStatus.ACTIVE,
            )
            .order_by(m.Appointment.id)
        )
        return [_to_appointment(appt, doctor_id) for appt, doctor_id in rows]

    # ---- writes ------------------------------------------------------

    def save_appointment(
        self, slot: schemas.Slot, patient_id: int
    ) -> schemas.Appointment:
        """Insert the booking. Raises ConstraintViolation if the DB refuses it.

        The repository does not decide whether booking is allowed (that is the
        service's job); it only records the result and reports a refusal.
        """
        doctor = self._session.get(m.Doctor, slot.doctor_id)
        row = m.Appointment(
            slot_id=slot.id,
            patient_id=patient_id,
            # Snapshot columns (see models.py): copied once, at booking time.
            specialty_id=doctor.specialty_id,
            # The slot's date on the CLINIC's calendar, not UTC's.
            appointment_date=slot.start_time.astimezone(CLINIC_TZ).date(),
        )
        try:
            # begin_nested() = a SAVEPOINT: if the INSERT fails, only this tiny
            # step is undone and the request's transaction stays usable.
            with self._session.begin_nested():
                self._session.add(row)
                # flush() sends the INSERT to the database NOW. Without it the
                # INSERT would wait until commit, after the service has already
                # returned, and the service could never catch the violation.
                self._session.flush()
        except IntegrityError as error:
            raise ConstraintViolation(_constraint_name(error)) from error
        return _to_appointment(row, slot.doctor_id)

    # ---- helpers -----------------------------------------------------

    @staticmethod
    def _slots_query():
        """SELECT slot, is-it-taken FROM slots  (is_available is DERIVED)."""
        return select(m.Slot, _is_taken().label("taken"))


def _is_taken():
    """SQL: EXISTS (an ACTIVE appointment points at this slot)."""
    return exists().where(
        m.Appointment.slot_id == m.Slot.id,
        m.Appointment.status == m.AppointmentStatus.ACTIVE,
    )


def _constraint_name(error: IntegrityError) -> str | None:
    # psycopg exposes PostgreSQL's error fields under .diag
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


def _to_slot(row: m.Slot, taken: bool) -> schemas.Slot:
    return schemas.Slot(
        id=row.id,
        doctor_id=row.doctor_id,
        # Stored as UTC; shown in clinic time (still unambiguous: it has an offset).
        start_time=row.start_time.astimezone(CLINIC_TZ),
        end_time=row.end_time.astimezone(CLINIC_TZ),
        is_available=not taken,
    )


def _to_appointment(row: m.Appointment, doctor_id: int) -> schemas.Appointment:
    return schemas.Appointment(
        id=row.id,
        slot_id=row.slot_id,
        patient_id=row.patient_id,
        doctor_id=doctor_id,
        created_at=row.created_at,
    )
