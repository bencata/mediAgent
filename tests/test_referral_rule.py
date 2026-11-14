"""The referral rule, tested through the service with a frozen clock.

Each test is named after the behaviour it protects. Reading the names top to
bottom is the specification of the rule.
"""

import re
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select, update

from app.db import models as m
from app.errors import (
    ForbiddenError,
    ReferralAmbiguousError,
    ReferralExpiredError,
    ReferralMissingError,
    ReferralNotRequiredError,
    ReferralNotYetValidError,
    ReferralUsedError,
    ReferralWrongSpecialtyError,
    SlotTakenError,
)
from tests.helpers import (
    BEN,
    CARDIO_SLOT_DAY1,
    CARDIO_SLOT_DAY2,
    MAYA,
    NOGA,
    OMER,
    ORTHO_SLOT_DAY1,
    SHIR,
    add_referral,
)


def stored_referral_id(session, appointment_id):
    """What the DATABASE says this appointment consumed (not what the service returned)."""
    return session.scalar(
        select(m.Appointment.referral_id).where(m.Appointment.id == appointment_id)
    )


# ---- the happy paths ------------------------------------------------------


def test_naming_a_valid_referral_books_and_consumes_it(session, make_service):
    appointment = make_service().book_appointment(BEN, CARDIO_SLOT_DAY1, referral_id=1)
    assert stored_referral_id(session, appointment.id) == 1


def test_without_naming_one_the_only_usable_referral_is_picked(session, make_service):
    appointment = make_service().book_appointment(BEN, CARDIO_SLOT_DAY1)
    assert stored_referral_id(session, appointment.id) == 1


def test_specialty_without_referral_requirement_books_without_one(session, make_service):
    appointment = make_service().book_appointment(NOGA, ORTHO_SLOT_DAY1)
    assert stored_referral_id(session, appointment.id) is None


# ---- no referral / wrong referral ----------------------------------------


def test_required_specialty_with_no_referrals_is_rejected(make_service):
    with pytest.raises(ReferralMissingError) as error:
        make_service().book_appointment(NOGA, CARDIO_SLOT_DAY1)
    assert error.value.code == "referral_missing"


def test_referral_for_another_specialty_is_rejected(make_service):
    # Maya's referral 2 is for Dermatology; the slot is Cardiology.
    with pytest.raises(ReferralWrongSpecialtyError):
        make_service().book_appointment(MAYA, CARDIO_SLOT_DAY1, referral_id=2)


def test_sending_a_referral_for_a_specialty_that_needs_none_is_rejected(
    repo, make_service
):
    # Rejected (not ignored) so the client never thinks the referral was consumed.
    with pytest.raises(ReferralNotRequiredError):
        make_service().book_appointment(BEN, ORTHO_SLOT_DAY1, referral_id=1)
    assert repo.list_appointments_for_patient(BEN) == []  # nothing was saved


# ---- ownership: someone else's referral ----------------------------------


def test_someone_elses_referral_is_forbidden(make_service):
    with pytest.raises(ForbiddenError):
        make_service().book_appointment(MAYA, CARDIO_SLOT_DAY1, referral_id=1)


def test_foreign_and_nonexistent_referrals_are_indistinguishable(make_service):
    """Otherwise a caller could probe which referral ids exist."""
    with pytest.raises(ForbiddenError) as foreign:
        make_service().book_appointment(MAYA, CARDIO_SLOT_DAY1, referral_id=1)
    with pytest.raises(ForbiddenError) as nonexistent:
        make_service().book_appointment(MAYA, CARDIO_SLOT_DAY1, referral_id=999)

    def without_ids(text):
        return re.sub(r"\d+", "N", text)

    assert without_ids(foreign.value.message) == without_ids(nonexistent.value.message)


def test_ownership_is_checked_before_specialty(make_service):
    """Ben sends Maya's DERMATOLOGY referral for a cardiology slot. He must hear
    "forbidden", not "wrong specialty" - the latter would leak what her referral is."""
    with pytest.raises(ForbiddenError):
        make_service().book_appointment(BEN, CARDIO_SLOT_DAY1, referral_id=2)


# ---- validity window: expired / not yet valid ----------------------------


@pytest.mark.parametrize("named", [3, None], ids=["named", "auto-picked"])
def test_expired_referral_is_rejected(make_service, named):
    with pytest.raises(ReferralExpiredError):
        make_service().book_appointment(OMER, CARDIO_SLOT_DAY1, referral_id=named)


@pytest.mark.parametrize("named", [4, None], ids=["named", "auto-picked"])
def test_not_yet_valid_referral_is_rejected_with_its_own_reason(make_service, named):
    with pytest.raises(ReferralNotYetValidError) as error:
        make_service().book_appointment(SHIR, CARDIO_SLOT_DAY1, referral_id=named)
    assert error.value.code == "referral_not_yet_valid"  # not "expired"


# "Today" in the tests is 2026-11-14. Both ends of the window are INCLUSIVE.
@pytest.mark.parametrize(
    ("valid_from", "valid_until", "expected_error"),
    [
        pytest.param(date(2026, 11, 14), date(2026, 11, 14), None, id="single-day-today"),
        pytest.param(date(2026, 11, 1), date(2026, 11, 14), None, id="last-day-is-valid"),
        pytest.param(date(2026, 11, 14), date(2026, 12, 31), None, id="first-day-is-valid"),
        pytest.param(date(2026, 11, 1), date(2026, 11, 13), ReferralExpiredError, id="expired-yesterday"),
        pytest.param(date(2026, 11, 15), date(2026, 12, 1), ReferralNotYetValidError, id="starts-tomorrow"),
    ],
)
def test_window_boundaries(session, make_service, valid_from, valid_until, expected_error):
    referral_id = add_referral(session, NOGA, valid_from, valid_until)
    service = make_service()
    if expected_error is None:
        service.book_appointment(NOGA, CARDIO_SLOT_DAY1, referral_id=referral_id)
    else:
        with pytest.raises(expected_error):
            service.book_appointment(NOGA, CARDIO_SLOT_DAY1, referral_id=referral_id)


# The same UTC instant can be two different calendar days. The rule must use
# the CLINIC's day (Asia/Jerusalem is UTC+2 in winter), never the UTC day.
@pytest.mark.parametrize(
    ("valid_from", "valid_until", "now_utc", "expected_error"),
    [
        pytest.param(
            date(2026, 1, 1), date(2026, 12, 31),
            datetime(2026, 12, 31, 21, 30, tzinfo=timezone.utc),  # 23:30 on Dec 31 in clinic
            None, id="still-last-day-at-clinic",
        ),
        pytest.param(
            date(2026, 1, 1), date(2026, 12, 31),
            datetime(2026, 12, 31, 22, 30, tzinfo=timezone.utc),  # 00:30 on Jan 1 in clinic
            ReferralExpiredError, id="expired-at-clinic-though-still-dec-31-in-utc",
        ),
        pytest.param(
            date(2026, 12, 1), date(2027, 1, 31),
            datetime(2026, 11, 30, 22, 30, tzinfo=timezone.utc),  # 00:30 on Dec 1 in clinic
            None, id="valid-at-clinic-though-still-nov-30-in-utc",
        ),
        pytest.param(
            date(2026, 12, 1), date(2027, 1, 31),
            datetime(2026, 11, 30, 21, 30, tzinfo=timezone.utc),  # 23:30 on Nov 30 in clinic
            ReferralNotYetValidError, id="not-yet-valid-at-clinic",
        ),
    ],
)
def test_validity_uses_the_clinic_calendar_not_utc(
    session, make_service, valid_from, valid_until, now_utc, expected_error
):
    referral_id = add_referral(session, NOGA, valid_from, valid_until)
    service = make_service(now=now_utc)
    if expected_error is None:
        service.book_appointment(NOGA, CARDIO_SLOT_DAY1, referral_id=referral_id)
    else:
        with pytest.raises(expected_error):
            service.book_appointment(NOGA, CARDIO_SLOT_DAY1, referral_id=referral_id)


# ---- used referrals -------------------------------------------------------


def test_a_referral_cannot_be_used_twice(make_service):
    service = make_service()
    service.book_appointment(BEN, CARDIO_SLOT_DAY1, referral_id=1)
    # A different day, so only the referral (not the per-day rule) can object.
    with pytest.raises(ReferralUsedError):
        service.book_appointment(BEN, CARDIO_SLOT_DAY2, referral_id=1)
    with pytest.raises(ReferralUsedError):  # same reason when nothing is named
        service.book_appointment(BEN, CARDIO_SLOT_DAY2)


def test_cancelling_an_appointment_frees_its_referral(session, make_service):
    service = make_service()
    first = service.book_appointment(BEN, CARDIO_SLOT_DAY1, referral_id=1)
    session.execute(
        update(m.Appointment)
        .where(m.Appointment.id == first.id)
        .values(status=m.AppointmentStatus.CANCELLED)
    )
    second = service.book_appointment(BEN, CARDIO_SLOT_DAY2, referral_id=1)
    assert stored_referral_id(session, second.id) == 1


# ---- several referrals: ambiguity and which reason is reported -------------


def test_two_usable_referrals_and_none_named_is_ambiguous(session, make_service):
    add_referral(session, BEN, date(2026, 11, 10), date(2027, 1, 31))
    with pytest.raises(ReferralAmbiguousError) as error:
        make_service().book_appointment(BEN, CARDIO_SLOT_DAY1)
    assert error.value.code == "referral_ambiguous"


def test_naming_one_of_two_usable_referrals_resolves_the_ambiguity(session, make_service):
    second = add_referral(session, BEN, date(2026, 11, 10), date(2027, 1, 31))
    appointment = make_service().book_appointment(BEN, CARDIO_SLOT_DAY1, referral_id=second)
    assert stored_referral_id(session, appointment.id) == second


def test_expired_outranks_used_when_nothing_is_usable(session, make_service):
    service = make_service()
    service.book_appointment(BEN, CARDIO_SLOT_DAY1, referral_id=1)  # referral 1 is now used
    add_referral(session, BEN, date(2026, 1, 1), date(2026, 10, 15))  # and one has expired
    with pytest.raises(ReferralExpiredError):
        service.book_appointment(BEN, CARDIO_SLOT_DAY2)


def test_among_expired_referrals_the_most_recent_is_reported(session, make_service):
    older = add_referral(session, NOGA, date(2026, 7, 1), date(2026, 9, 1))
    newer = add_referral(session, NOGA, date(2026, 9, 2), date(2026, 10, 1))
    with pytest.raises(ReferralExpiredError) as error:
        make_service().book_appointment(NOGA, CARDIO_SLOT_DAY1)
    assert f"Referral {newer} " in error.value.message
    assert f"Referral {older} " not in error.value.message


# ---- unaffected rules still hold ------------------------------------------


def test_a_taken_slot_is_reported_before_referral_problems(make_service):
    service = make_service()
    service.book_appointment(BEN, CARDIO_SLOT_DAY1, referral_id=1)
    with pytest.raises(SlotTakenError) as error:
        # Omer's referral is expired too, but the slot problem is reported first.
        service.book_appointment(OMER, CARDIO_SLOT_DAY1)
    assert error.value.code == "slot_taken"
