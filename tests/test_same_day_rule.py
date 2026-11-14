"""The rule "one active appointment per patient, specialty and CLINIC day".

The friendly service check is tested here; the database backstop (the check
fooled on purpose) is in test_db_constraints.py.
"""

from datetime import date, datetime

import pytest

from app.config import CLINIC_TZ
from app.errors import ReferralUsedError, SameDayAppointmentError
from tests.helpers import (
    BEN,
    CARDIO_SLOT_DAY1,
    CARDIO_SLOT_DAY1_LATER,
    CARDIO_SLOT_DAY2,
    NOGA,
    ORTHO_SLOT_DAY1,
    ORTHO_SLOT_DAY1_LATER,
    ORTHO_SLOT_DAY2,
    add_referral,
    add_slot,
)

ORTHO_DOCTOR = 5


def test_second_booking_for_the_same_specialty_and_day_is_refused(repo, make_service):
    service = make_service()
    service.book_appointment(NOGA, ORTHO_SLOT_DAY1)
    with pytest.raises(SameDayAppointmentError) as error:
        service.book_appointment(NOGA, ORTHO_SLOT_DAY1_LATER)
    assert error.value.code == "same_day_appointment"
    assert "2026-11-16" in error.value.message  # says WHICH day
    assert len(repo.list_appointments_for_patient(NOGA)) == 1


def test_the_next_day_is_fine(repo, make_service):
    service = make_service()
    service.book_appointment(NOGA, ORTHO_SLOT_DAY1)
    service.book_appointment(NOGA, ORTHO_SLOT_DAY2)
    assert len(repo.list_appointments_for_patient(NOGA)) == 2


def test_the_rule_is_per_specialty_not_per_doctor(session, make_service):
    """Two different cardiologists, same day: still one cardiology booking per day."""
    second_referral = add_referral(session, BEN, date(2026, 11, 10), date(2027, 1, 31))
    service = make_service()
    service.book_appointment(BEN, CARDIO_SLOT_DAY1, referral_id=1)
    other_doctor_same_day = 7  # Dr. Cohen (cardiology), 16 Nov 09:00
    with pytest.raises(SameDayAppointmentError):
        service.book_appointment(BEN, other_doctor_same_day, referral_id=second_referral)


def test_a_different_specialty_on_the_same_day_is_fine(repo, make_service):
    service = make_service()
    service.book_appointment(BEN, ORTHO_SLOT_DAY1_LATER)  # orthopedics 09:30
    service.book_appointment(BEN, CARDIO_SLOT_DAY1, referral_id=1)  # cardiology 09:00
    assert len(repo.list_appointments_for_patient(BEN)) == 2


def test_the_day_conflict_is_reported_before_a_used_referral(make_service):
    """Ben's only referral was consumed by his first appointment that day. The
    useful answer for a second same-day booking is the DAY conflict, not
    "referral used" (which is true but hides the real reason)."""
    service = make_service()
    service.book_appointment(BEN, CARDIO_SLOT_DAY1, referral_id=1)
    with pytest.raises(SameDayAppointmentError):
        service.book_appointment(BEN, CARDIO_SLOT_DAY1_LATER)
    # ...whereas on another day the referral is the only thing in the way.
    with pytest.raises(ReferralUsedError):
        service.book_appointment(BEN, CARDIO_SLOT_DAY2)


# "Day" means the CLINIC's day. Asia/Jerusalem is UTC+2 in December, so a slot
# at 00:30 clinic time is 22:30 UTC on the PREVIOUS day. Using the UTC date
# would get both of these wrong, in opposite directions.


def test_slots_on_different_clinic_days_are_allowed_even_if_same_utc_day(session, make_service):
    evening = add_slot(session, ORTHO_DOCTOR, datetime(2026, 12, 1, 23, 30, tzinfo=CLINIC_TZ))
    after_midnight = add_slot(session, ORTHO_DOCTOR, datetime(2026, 12, 2, 0, 30, tzinfo=CLINIC_TZ))
    service = make_service()
    service.book_appointment(NOGA, evening)  # Dec 1 clinic day (21:30 UTC, Dec 1)
    service.book_appointment(NOGA, after_midnight)  # Dec 2 clinic day (22:30 UTC, Dec 1)


def test_slots_on_the_same_clinic_day_are_refused_even_if_different_utc_days(session, make_service):
    after_midnight = add_slot(session, ORTHO_DOCTOR, datetime(2026, 12, 2, 0, 30, tzinfo=CLINIC_TZ))
    morning = add_slot(session, ORTHO_DOCTOR, datetime(2026, 12, 2, 9, 0, tzinfo=CLINIC_TZ))
    service = make_service()
    service.book_appointment(NOGA, after_midnight)  # 22:30 UTC, Dec 1
    with pytest.raises(SameDayAppointmentError):
        service.book_appointment(NOGA, morning)  # 07:00 UTC, Dec 2
