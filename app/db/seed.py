"""Seed the database with demo data.

    uv run python -m app.db.seed            # seed if empty (safe to repeat)
    uv run python -m app.db.seed --reset    # DELETE ALL DATA, then seed (dev only)

Every date is relative to a "today" (default: the clinic's real today), so a
freshly seeded demo always has valid, expired and not-yet-valid referrals and
slots in the future. Tests pass a fixed `today`, so their data never changes.
The data does NOT follow the calendar after seeding: re-run with --reset
when a long-lived dev database has gone stale.
"""

import argparse
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import CLINIC_TZ, clinic_date
from app.db.models import Base, Doctor, Patient, Referral, Slot, Specialty
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

# (patient_id, specialty_id, valid_from, valid_until) - the dates are DAY OFFSETS
# from "today" (negative = in the past). One of each situation, so every
# referral rule has demo data to exercise.
REFERRALS = [
    (1, 1, -13, 47),   # valid: Ben, Cardiology
    (2, 2, -13, 47),   # valid: Maya, Dermatology
    (3, 1, -74, -44),  # expired: Omer, Cardiology
    (4, 1, 48, 79),    # not valid YET: Shir, Cardiology
    # patients 5-10 have no referrals at all
]


def reset(session: Session) -> None:
    """Empty EVERY table and restart the id counters. Destroys all data."""
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def seed(session: Session, today: date | None = None) -> bool:
    """Insert the demo data. Returns False if it was already seeded.

    `today` is the clinic-calendar day the offsets are measured from.
    """
    if session.scalar(select(func.count()).select_from(Specialty)):
        return False
    today = today or clinic_date(datetime.now(CLINIC_TZ))

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
        Referral(
            id=i,
            patient_id=p,
            specialty_id=s,
            valid_from=today + timedelta(days=f),
            valid_until=today + timedelta(days=u),
        )
        for i, (p, s, f, u) in enumerate(REFERRALS, start=1)
    )

    # Each doctor: 3 half-hour slots (09:00, 09:30, 10:00) on each of two days,
    # starting the next Monday after `today` (so slots are always in the future),
    # in the CLINIC's time zone (a naive datetime would be a bug: see config.py).
    days_until_monday = (7 - today.weekday()) % 7 or 7  # Monday is weekday 0
    first_day = datetime.combine(
        today + timedelta(days=days_until_monday), time(9, 0), tzinfo=CLINIC_TZ
    )
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
    parser = argparse.ArgumentParser(description="Seed the demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="DELETE ALL DATA first, then seed (development databases only)",
    )
    args = parser.parse_args()
    # .begin() = open a session AND a transaction; commit on success, roll
    # back on error. A half-seeded (or half-reset) database can't happen.
    with SessionLocal.begin() as session:
        if args.reset:
            reset(session)
        print("Seeded." if seed(session) else "Already seeded - nothing to do.")
