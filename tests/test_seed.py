"""The demo seed: idempotent, and its dates follow the day it is given."""

from datetime import date, datetime

import pytest
from sqlalchemy import func, select

from app.config import CLINIC_TZ
from app.db import models as m
from app.db.seed import reset, seed
from app.db.session import SessionLocal
from app.errors import ReferralExpiredError, ReferralNotYetValidError
from app.repositories import SqlRepository
from app.services import AppointmentService
from tests.helpers import BEN, NOW, OMER, SHIR


def test_seeding_twice_does_nothing_the_second_time(fresh_db):
    with SessionLocal.begin() as session:
        assert seed(session, today=NOW.date()) is False


def test_reset_empties_every_table(fresh_db):
    with SessionLocal.begin() as session:
        reset(session)
    with SessionLocal() as session:
        for model in (m.Specialty, m.Doctor, m.Patient, m.Referral, m.Slot, m.Appointment):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_seed_dates_follow_the_day_it_is_given(fresh_db):
    """Seeded in mid-2027, the demo is just as usable: nothing is stale."""
    today = date(2027, 6, 1)  # a Tuesday
    with SessionLocal.begin() as session:
        reset(session)
        seed(session, today=today)

    with SessionLocal() as session:
        repo = SqlRepository(session)
        service = AppointmentService(
            repo, clock=lambda: datetime(2027, 6, 1, 12, 0, tzinfo=CLINIC_TZ)
        )
        first_slot = repo.get_slot(1).start_time
        assert first_slot.date() == date(2027, 6, 7)  # the next Monday, in the future
        assert (first_slot.weekday(), first_slot.hour) == (0, 9)

        service.book_appointment(BEN, 1, referral_id=1)  # still valid
        with pytest.raises(ReferralExpiredError):
            service.book_appointment(OMER, 2)  # still expired
        with pytest.raises(ReferralNotYetValidError):
            service.book_appointment(SHIR, 3)  # still not yet valid


@pytest.mark.parametrize(
    ("today", "expected_first_monday"),
    [
        (date(2026, 11, 14), date(2026, 11, 16)),  # Saturday -> two days later
        (date(2026, 11, 15), date(2026, 11, 16)),  # Sunday -> next day
        (date(2026, 11, 16), date(2026, 11, 23)),  # Monday -> a WEEK later, never "today"
    ],
)
def test_slots_start_on_the_next_monday_after_today(fresh_db, today, expected_first_monday):
    with SessionLocal.begin() as session:
        reset(session)
        seed(session, today=today)
    with SessionLocal() as session:
        assert SqlRepository(session).get_slot(1).start_time.date() == expected_first_monday
