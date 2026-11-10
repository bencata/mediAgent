"""Service layer: the business rules.

The service sits between the router (HTTP) and the repository (storage):

    router  ->  service  ->  repository
    "what was    "is this     "store / fetch"
     asked?"      allowed?"

It receives plain Python values (not HTTP requests), applies the rules,
and raises domain errors when a rule is broken.
"""

from app.errors import ConflictError, NotFoundError
from app.repositories import InMemoryRepository
from app.schemas import Appointment, Slot, Specialty


class AppointmentService:
    def __init__(self, repository: InMemoryRepository) -> None:
        # The repository is passed IN rather than created here
        # ("dependency injection"), so tests can hand in a fresh one.
        self._repo = repository

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

    def book_appointment(self, patient_id: int, slot_id: int) -> Appointment:
        self._require_patient(patient_id)

        slot = self._repo.get_slot(slot_id)
        if slot is None:
            raise NotFoundError(f"Slot {slot_id} does not exist")  # 404

        # --- the rule ---
        if not slot.is_available:
            raise ConflictError(f"Slot {slot_id} is already booked")  # 409

        # NOTE: "check, then act". Between the line above and the save below,
        # another request could book the same slot. We fix that in Stages 2-3.
        return self._repo.save_appointment(slot, patient_id)

    def _require_patient(self, patient_id: int) -> None:
        if self._repo.get_patient(patient_id) is None:
            raise NotFoundError(f"Patient {patient_id} does not exist")
