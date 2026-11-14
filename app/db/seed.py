"""Seed the database with demo data:  uv run python -m app.db.seed

Idempotent: if the data is already there it does nothing, so it is safe to
run again. Dates are fixed (no "now") so the demo is the same every time.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import CLINIC_TZ
from app.db.models import Doctor, Patient, Referral, Slot, Specialty
from app.db.session import SessionLocal

# (name, referral_required)
SPECIALTIES = [
    ("Cardiology", True),
    ("Dermatology", True),
    ("Orthopedics", False),  # open access: no referral needed
]

# (name, specialty_id)
DOCTORS = [
    ("Dr. Noa Levi", 1),
    ("Dr. Amit Cohen", 1),
    ("Dr. Tamar Shapira", 2),
    ("Dr. Yoav Mizrahi", 2),
    ("Dr. Dana Peretz", 3),
]

PATIENTS = [
    "Ben Catalan", "Maya Katz", "Omer Ben-David", "Shir Azulay",
    "Eitan Golan", "Lior Friedman", "Yael Avraham", "Itai Dahan",
    "Roni Biton", "Noga Hadad",
]

# (patient_id, specialty_id, valid_from, valid_until): one of each situation,
# so every referral rule has demo data to exercise.
REFERRALS = [
    (1, 1, date(2026, 11, 1), date(2026, 12, 31)),   # valid: Ben, Cardiology
    (2, 2, date(2026, 11, 1), date(2026, 12, 31)),   # valid: Maya, Dermatology
    (3, 1, date(2026, 9, 1), date(2026, 10, 1)),     # expired: Omer, Cardiology
    (4, 1, date(2027, 1, 1), date(2027, 2, 1)),      # not valid YET: Shir, Cardiology
    # patients 5-10 have no referrals at all
]


def seed(session: Session) -> bool:
    """Insert the demo data. Returns False if it was already seeded."""
    if session.scalar(select(func.count()).select_from(Specialty)):
        return False

    # Explicit ids keep the demo identical to Stage 1 (slot 1, patient 1, ...).
    session.add_all(
        Specialty(id=i, name=name, referral_required=req)
        for i, (name, req) in enumerate(SPECIALTIES, start=1)
    )
    session.flush()  # specialties must exist before doctors point at them
    session.add_all(
        Doctor(id=i, name=name, specialty_id=sid)
        for i, (name, sid) in enumerate(DOCTORS, start=1)
    )
    session.add_all(Patient(id=i, name=n) for i, n in enumerate(PATIENTS, start=1))
    session.flush()
    session.add_all(
        Referral(id=i, patient_id=p, specialty_id=s, valid_from=f, valid_until=u)
        for i, (p, s, f, u) in enumerate(REFERRALS, start=1)
    )

    # Each doctor: 3 half-hour slots (09:00, 09:30, 10:00) on each of two days,
    # in the CLINIC's time zone (a naive datetime would be a bug: see config.py).
    first_day = datetime(2026, 11, 16, 9, 0, tzinfo=CLINIC_TZ)  # a Monday
    slot_id = 1
    for doctor_id in range(1, len(DOCTORS) + 1):
        for day_offset in (0, 1):
            for slot_index in range(3):
                start = first_day + timedelta(days=day_offset, minutes=30 * slot_index)
                session.add(
                    Slot(
                        id=slot_id,
                        doctor_id=doctor_id,
                        start_time=start,
                        end_time=start + timedelta(minutes=30),
                    )
                )
                slot_id += 1
    session.flush()

    # TRAP: we gave explicit ids, so PostgreSQL's id counters (sequences) never
    # moved. The next row inserted WITHOUT an id would get id 1 and collide.
    # Move each counter up to the highest id in use.
    for model in (Specialty, Doctor, Patient, Referral, Slot):
        table = model.__tablename__  # our own constant, not user input
        session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"(SELECT max(id) FROM {table}))"
            )
        )
    return True


if __name__ == "__main__":
    # .begin() = open a session AND a transaction; commit on success, roll
    # back on error. A half-seeded database can't happen.
    with SessionLocal.begin() as session:
        print("Seeded." if seed(session) else "Already seeded - nothing to do.")
