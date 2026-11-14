"""Domain errors: things that go wrong in *business terms*.

These know nothing about HTTP. The service raises them; app/main.py
translates each one into a status code. That keeps the service reusable
- later the LLM agent will call the same service with no HTTP involved.

`code` is a stable, machine-readable reason. Messages are for humans and may
change wording; a client (or the Phase 4 agent) should branch on `code`.
"""


class DomainError(Exception):
    """Base class, so a caller can catch every business error at once."""

    code: str | None = None

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    """The thing you referred to does not exist  -> HTTP 404."""


class ForbiddenError(DomainError):
    """You are not allowed to use that thing -> HTTP 403.

    Also used when the thing does not exist, so a caller cannot probe which
    ids exist by comparing "forbidden" with "not found".
    """


class ConflictError(DomainError):
    """It exists, but its current state forbids this action -> HTTP 409."""


class SlotTakenError(ConflictError):
    """An active appointment already holds this slot."""

    code = "slot_taken"


class SameDayAppointmentError(ConflictError):
    """The patient already has an active appointment for this specialty that day."""

    code = "same_day_appointment"


# ---- referral reasons: all 409, told apart by `code` -------------------


class ReferralError(ConflictError):
    """Base for every "the referral situation forbids this booking" reason."""


class ReferralMissingError(ReferralError):
    """This specialty needs a referral and the patient has none for it."""

    code = "referral_missing"


class ReferralExpiredError(ReferralError):
    """The referral's last valid day (clinic time) has passed."""

    code = "referral_expired"


class ReferralNotYetValidError(ReferralError):
    """The referral's first valid day (clinic time) has not come yet."""

    code = "referral_not_yet_valid"


class ReferralUsedError(ReferralError):
    """An active appointment already consumed this referral."""

    code = "referral_used"


class ReferralWrongSpecialtyError(ReferralError):
    """The referral is for a different specialty than the slot's doctor."""

    code = "referral_wrong_specialty"


class ReferralAmbiguousError(ReferralError):
    """Several referrals are usable and the client did not say which one."""

    code = "referral_ambiguous"


class ReferralNotRequiredError(ReferralError):
    """A referral was sent for a specialty that does not need one."""

    code = "referral_not_required"
