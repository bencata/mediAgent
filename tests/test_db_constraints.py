"""The DATABASE as the last line of defence.

The service checks are the friendly first line ("slot already booked"). But
"check, then act" is not atomic, so the database must refuse the bad write
itself. These tests fool the service's checks on purpose, then show the
database still says no - and that the service turns that into the right error.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import CLINIC_TZ
from app.db import models as m
from app.errors import ConflictError, ReferralUsedError
from app.services import AppointmentService
from tests.helpers import (
    BEN,
    CARDIO_SLOT_DAY1,
    CARDIO_SLOT_DAY2,
    NOGA,
    NOW,
    ORTHO_SLOT_DAY1,
    ORTHO_SLOT_DAY1_LATER,
    ORTHO_SLOT_DAY2,
    YAEL,
)

# ---- appointments: simulating a lost race --------------------------------


def test_database_refuses_a_double_booking_when_the_service_check_is_fooled(
    repo, make_service, monkeypatch
):
    service = make_service()
    service.book_appointment(NOGA, ORTHO_SLOT_DAY1)

    # Simulate the race: the second request read the slot BEFORE the first
    # request booked it, so it still believes the slot is free.
    real_get_slot = repo.get_slot
    monkeypatch.setattr(
        repo,
        "get_slot",
        lambda slot_id: real_get_slot(slot_id).model_copy(update={"is_available": True}),
    )
    with pytest.raises(ConflictError) as error:
        service.book_appointment(YAEL, ORTHO_SLOT_DAY1)
    assert "already booked" in error.value.message
    # The failed attempt left nothing behind, and the session is still usable.
    assert repo.list_appointments_for_patient(YAEL) == []


def test_database_refuses_a_second_use_of_a_referral_when_the_service_check_is_fooled(
    repo, make_service, monkeypatch
):
    service = make_service()
    service.book_appointment(BEN, CARDIO_SLOT_DAY1, referral_id=1)

    monkeypatch.setattr(repo, "is_referral_used", lambda referral_id: False)  # fooled
    with pytest.raises(ReferralUsedError) as error:
        service.book_appointment(BEN, CARDIO_SLOT_DAY2, referral_id=1)
    assert error.value.code == "referral_used"
    assert "just used" in error.value.message  # produced by the DB path, not the pre-check


def test_one_active_appointment_per_patient_specialty_and_day(repo, make_service):
    service = make_service()
    service.book_appointment(NOGA, ORTHO_SLOT_DAY1)
    with pytest.raises(ConflictError) as error:  # same specialty, same clinic day
        service.book_appointment(NOGA, ORTHO_SLOT_DAY1_LATER)
    assert "that day" in error.value.message
    service.book_appointment(NOGA, ORTHO_SLOT_DAY2)  # the next day is fine
    assert len(repo.list_appointments_for_patient(NOGA)) == 2


def test_cancelling_frees_the_day_and_the_slot(session, repo, make_service):
    service = make_service()
    first = service.book_appointment(NOGA, ORTHO_SLOT_DAY1)
    session.query(m.Appointment).filter_by(id=first.id).update(
        {"status": m.AppointmentStatus.CANCELLED}
    )
    service.book_appointment(NOGA, ORTHO_SLOT_DAY1_LATER)  # same day: allowed again
    service.book_appointment(YAEL, ORTHO_SLOT_DAY1)  # the cancelled slot: free again


# ---- slots: constraints that live only in the database ---------------------


def test_slot_cannot_end_before_it_starts(session):
    start = datetime(2026, 12, 1, 10, 0, tzinfo=CLINIC_TZ)
    session.add(m.Slot(doctor_id=1, start_time=start, end_time=start - timedelta(hours=1)))
    with pytest.raises(IntegrityError) as error:
        session.flush()
    assert "ck_slots_end_after_start" in str(error.value)


def test_a_doctors_slots_cannot_overlap(session):
    start = datetime(2026, 12, 1, 10, 0, tzinfo=CLINIC_TZ)
    session.add(m.Slot(doctor_id=1, start_time=start, end_time=start + timedelta(minutes=30)))
    session.flush()
    session.add(
        m.Slot(
            doctor_id=1,
            start_time=start + timedelta(minutes=15),
            end_time=start + timedelta(minutes=45),
        )
    )
    with pytest.raises(IntegrityError) as error:
        session.flush()
    assert "ex_slots_no_overlap" in str(error.value)


def test_back_to_back_slots_and_other_doctors_are_allowed(session):
    start = datetime(2026, 12, 1, 10, 0, tzinfo=CLINIC_TZ)
    half_hour = timedelta(minutes=30)
    session.add_all(
        [
            m.Slot(doctor_id=1, start_time=start, end_time=start + half_hour),
            # starts exactly when the previous one ends: the range is half-open
            m.Slot(doctor_id=1, start_time=start + half_hour, end_time=start + 2 * half_hour),
            # same time, different doctor: no conflict
            m.Slot(doctor_id=2, start_time=start, end_time=start + half_hour),
        ]
    )
    session.flush()  # must not raise


def test_referral_dates_must_be_in_order(session):
    session.add(
        m.Referral(
            patient_id=1,
            specialty_id=1,
            valid_from=NOW.date() + timedelta(days=5),
            valid_until=NOW.date(),
        )
    )
    with pytest.raises(IntegrityError) as error:
        session.flush()
    assert "ck_referrals_valid_range" in str(error.value)
