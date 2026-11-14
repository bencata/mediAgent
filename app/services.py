"""Service layer: the business rules.

The service sits between the router (HTTP) and the repository (storage):

    router  ->  service  ->  repository
    "what was    "is this     "store / fetch"
     asked?"      allowed?"

It receives plain Python values (not HTTP requests), applies the rules,
and raises domain errors when a rule is broken.
"""

from collections.abc import Callable
from datetime import date, datetime

from app.config import CLINIC_TZ, clinic_date
from app.errors import (
    ForbiddenError,
    NotFoundError,
    ReferralAmbiguousError,
    ReferralError,
    ReferralExpiredError,
    ReferralMissingError,
    ReferralNotRequiredError,
    ReferralNotYetValidError,
    ReferralUsedError,
    ReferralWrongSpecialtyError,
    SameDayAppointmentError,
    SlotTakenError,
)
from app.repositories import ConstraintViolation, SqlRepository
from app.schemas import Appointment, Referral, Slot, Specialty


# When no referral is usable and the client did not name one, WHICH reason do
# we report? Lower rank wins. Our policy: what the patient most likely means
# is "my referral ran out", then "I already used it", then "I have none".
_PROBLEM_RANK: dict[type[ReferralError], int] = {
    ReferralExpiredError: 0,
    ReferralNotYetValidError: 0,
    ReferralUsedError: 1,
}


def _problem_rank(problem: ReferralError) -> int:
    return _PROBLEM_RANK.get(type(problem), len(_PROBLEM_RANK))


class AppointmentService:
    def __init__(
        self,
        repository: SqlRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        # The repository is passed IN rather than created here
        # ("dependency injection"), so tests can hand in a fresh one.
        self._repo = repository
        # The clock is injected for the same reason: a test can pass
        # `lambda: datetime(2026, 12, 5, 0, 30, tzinfo=CLINIC_TZ)` and the
        # referral rules become deterministic. Production uses the real time.
        self._now = clock or (lambda: datetime.now(CLINIC_TZ))

    def _today(self) -> date:
        """Today's date on the CLINIC's calendar.

        Not `date.today()`: that uses the SERVER's time zone (the NY/LA bug).
        astimezone() also makes this correct if a test's clock is in another zone.
        """
        return clinic_date(self._now())

    def list_specialties(self) -> list[Specialty]:
        return self._repo.list_specialties()

    def list_available_slots(self, specialty_id: int | None = None) -> list[Slot]:
        # A filter for a specialty that doesn't exist is a mistake the caller
        # should hear about, not an empty list that looks like "fully booked".
        if specialty_id is not None and not any(
            s.id == specialty_id for s in self._repo.list_specialties()
        ):
            raise NotFoundError(f"Specialty {specialty_id} does not exist")
        return self._repo.list_slots(specialty_id=specialty_id, only_available=True)

    def list_my_appointments(self, patient_id: int) -> list[Appointment]:
        self._require_patient(patient_id)
        return self._repo.list_appointments_for_patient(patient_id)

    def book_appointment(
        self, patient_id: int, slot_id: int, referral_id: int | None = None
    ) -> Appointment:
        self._require_patient(patient_id)

        slot = self._repo.get_slot(slot_id)
        if slot is None:
            raise NotFoundError(f"Slot {slot_id} does not exist")  # 404

        if not slot.is_available:
            raise SlotTakenError(f"Slot {slot_id} is already booked")  # 409

        specialty = self._repo.get_specialty_for_slot(slot_id)  # exists: FK

        # One active appointment per patient, specialty and clinic day. This
        # comes BEFORE the referral rule on purpose: if the patient's only
        # referral was consumed by the earlier same-day appointment, the useful
        # message is "you already have one that day", not "referral used".
        day = clinic_date(slot.start_time)
        if self._repo.has_active_appointment_on_day(patient_id, specialty.id, day):
            raise SameDayAppointmentError(
                f"You already have a {specialty.name} appointment on {day}"
            )

        referral_id_to_use = self._resolve_referral(patient_id, specialty, referral_id)

        # The check above gives a friendly message in the common case, but it is
        # still "check, then act": another request can book the slot between the
        # check and the save. The DATABASE is the real guard - it refuses the
        # second INSERT atomically - and we translate its refusal here.
        try:
            return self._repo.save_appointment(slot, patient_id, referral_id_to_use)
        except ConstraintViolation as violation:
            raise self._to_conflict(violation, slot_id) from violation

    # ---- the referral rule -------------------------------------------

    def _resolve_referral(
        self, patient_id: int, specialty: Specialty, referral_id: int | None
    ) -> int | None:
        """Which referral does this booking consume? None = none is needed.

        Raises a ReferralError (409) / ForbiddenError (403) when booking is
        not allowed. Like the slot check, this is "check, then act": the
        database's uq_appointments_active_referral index is the real guard.
        """
        if not specialty.referral_required:
            if referral_id is not None:
                # Reject, don't ignore: the client must not believe a referral
                # was consumed when it wasn't.
                raise ReferralNotRequiredError(
                    f"{specialty.name} does not need a referral"
                )
            return None

        if referral_id is not None:  # the client named one: judge exactly that one
            referral = self._repo.get_referral_of_patient(referral_id, patient_id)
            if referral is None:
                # Missing and "belongs to someone else" are deliberately the
                # same answer, so ids cannot be probed.
                raise ForbiddenError(f"Referral {referral_id} cannot be used")
            problem = self._referral_problem(referral, specialty)
            if problem is not None:
                raise problem
            return referral.id

        # The client named none: look at all of this patient's referrals for
        # the specialty and only proceed if the choice is unambiguous.
        referrals = self._repo.list_referrals_of_patient(patient_id, specialty.id)
        if not referrals:
            raise ReferralMissingError(
                f"{specialty.name} requires a referral and you have none for it"
            )
        usable: list[Referral] = []
        problems: list[ReferralError] = []
        for referral in referrals:
            problem = self._referral_problem(referral, specialty)
            if problem is None:
                usable.append(referral)
            else:
                problems.append(problem)

        if len(usable) == 1:
            return usable[0].id
        if len(usable) > 1:
            ids = ", ".join(str(r.id) for r in usable)
            raise ReferralAmbiguousError(
                f"Several referrals can be used (ids {ids}); "
                "say which one with referral_id"
            )
        # None usable. `referrals` is sorted by valid_until, so reversing puts
        # the most recent first: among equally ranked reasons we report the
        # one about the newest referral.
        raise min(reversed(problems), key=_problem_rank)

    def _referral_problem(
        self, referral: Referral, specialty: Specialty
    ) -> ReferralError | None:
        """Why this one referral cannot be used right now (None = it can).

        RETURNS the error instead of raising it, so the caller decides: raise
        it (the client named this referral) or weigh it against the others.
        Cheap checks first; the database query for "used" comes last.
        """
        if referral.specialty_id != specialty.id:
            return ReferralWrongSpecialtyError(
                f"Referral {referral.id} is not for {specialty.name}"
            )
        today = self._today()  # the clinic's calendar day, see _today()
        if today < referral.valid_from:
            return ReferralNotYetValidError(
                f"Referral {referral.id} is valid from {referral.valid_from}"
            )
        if today > referral.valid_until:
            return ReferralExpiredError(
                f"Referral {referral.id} expired on {referral.valid_until}"
            )
        if self._repo.is_referral_used(referral.id):
            return ReferralUsedError(f"Referral {referral.id} was already used")
        return None

    @staticmethod
    def _to_conflict(violation: ConstraintViolation, slot_id: int) -> Exception:
        """Which constraint fired? That tells us which business rule was broken."""
        if violation.constraint == "uq_appointments_active_slot":
            return SlotTakenError(f"Slot {slot_id} is already booked")
        if violation.constraint == "uq_appointments_active_patient_specialty_day":
            return SameDayAppointmentError(
                "You already have an appointment for this specialty on that day"
            )
        if violation.constraint == "uq_appointments_active_referral":
            # Lost a race for the SAME referral (two requests used it at once).
            return ReferralUsedError("This referral was just used by another booking")
        return violation  # unknown constraint: a bug, let it be a 500

    def _require_patient(self, patient_id: int) -> None:
        if self._repo.get_patient(patient_id) is None:
            raise NotFoundError(f"Patient {patient_id} does not exist")
