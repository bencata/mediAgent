"""Constants and helpers shared by the tests.

The ids below come from the demo seed (app/db/seed.py). Keeping them named
here means a test reads "CARDIO_SLOT_DAY1", not a mysterious "1".
"""

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.config import CLINIC_TZ
from app.db import models as m

# "Now" for every test unless it says otherwise: 14 Nov 2026, noon, clinic time.
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=CLINIC_TZ)

# Specialties
CARDIOLOGY, DERMATOLOGY, ORTHOPEDICS = 1, 2, 3  # first two need a referral

# Patients (seeded referrals in brackets)
BEN = 1  # valid Cardiology referral (id 1, valid 2026-11-01 .. 2026-12-31)
MAYA = 2  # valid Dermatology referral (id 2)
OMER = 3  # EXPIRED Cardiology referral (id 3)
SHIR = 4  # NOT-YET-VALID Cardiology referral (id 4)
NOGA = 5  # no referrals at all
YAEL = 6  # no referrals at all

# Slots. Each doctor has 3 slots on each of two days (16 and 17 Nov 2026).
CARDIO_SLOT_DAY1 = 1  # Dr. Levi, 16 Nov 09:00
CARDIO_SLOT_DAY1_LATER = 2  # Dr. Levi, 16 Nov 09:30 (same day as above)
CARDIO_SLOT_DAY2 = 4  # Dr. Levi, 17 Nov 09:00
DERM_SLOT = 13
ORTHO_SLOT_DAY1 = 25  # the only specialty that needs no referral
ORTHO_SLOT_DAY1_LATER = 26
ORTHO_SLOT_DAY2 = 28


def add_referral(
    session: Session,
    patient_id: int,
    valid_from: date,
    valid_until: date,
    specialty_id: int = CARDIOLOGY,
) -> int:
    """Insert one extra referral for a scenario; returns its id."""
    referral = m.Referral(
        patient_id=patient_id,
        specialty_id=specialty_id,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    session.add(referral)
    session.flush()  # sends the INSERT now, so the id is assigned
    return referral.id
