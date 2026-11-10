"""Repository layer: the ONLY code that knows where data lives.

Today the data lives in Python dicts (in memory). In Stage 2 we replace this
class with one that talks to PostgreSQL - and the service layer above it
won't need to change, because it only calls these methods.

Rule for this layer: store and fetch. NO business rules here
(e.g. "is this slot bookable?" belongs in the service, not here).
"""

from datetime import datetime

from app.schemas import Appointment, Doctor, Patient, Slot, Specialty


class InMemoryRepository:
    def __init__(
        self,
        specialties: list[Specialty],
        doctors: list[Doctor],
        patients: list[Patient],
        slots: list[Slot],
    ) -> None:
        # dict keyed by id -> O(1) lookup, like a primary-key index.
        self._specialties = {s.id: s for s in specialties}
        self._doctors = {d.id: d for d in doctors}
        self._patients = {p.id: p for p in patients}
        self._slots = {s.id: s for s in slots}
        self._appointments: dict[int, Appointment] = {}
        self._next_appointment_id = 1

    # ---- reads -------------------------------------------------------

    def list_specialties(self) -> list[Specialty]:
        return list(self._specialties.values())

    def get_doctor(self, doctor_id: int) -> Doctor | None:
        return self._doctors.get(doctor_id)  # None if missing, never raises

    def get_patient(self, patient_id: int) -> Patient | None:
        return self._patients.get(patient_id)

    def get_slot(self, slot_id: int) -> Slot | None:
        return self._slots.get(slot_id)

    def list_slots(
        self,
        specialty_id: int | None = None,
        only_available: bool = True,
    ) -> list[Slot]:
        """Slots sorted by time, optionally filtered by specialty."""
        result = []
        for slot in self._slots.values():
            if only_available and not slot.is_available:
                continue
            if specialty_id is not None:
                doctor = self._doctors[slot.doctor_id]
                if doctor.specialty_id != specialty_id:
                    continue
            result.append(slot)
        return sorted(result, key=lambda s: (s.start_time, s.id))

    def list_appointments_for_patient(self, patient_id: int) -> list[Appointment]:
        return [a for a in self._appointments.values() if a.patient_id == patient_id]

    # ---- writes ------------------------------------------------------

    def save_appointment(self, slot: Slot, patient_id: int) -> Appointment:
        """Persist a booking and mark the slot as taken.

        The repository does not check availability - the service must
        have done that already. It only records the result.
        """
        appointment = Appointment(
            id=self._next_appointment_id,
            slot_id=slot.id,
            patient_id=patient_id,
            doctor_id=slot.doctor_id,
            created_at=datetime.now(),
        )
        self._appointments[appointment.id] = appointment
        self._next_appointment_id += 1
        slot.is_available = False
        return appointment


def build_seeded_repository() -> InMemoryRepository:
    """A fresh repository filled with the demo data (new instance each call)."""
    from app import seed

    return InMemoryRepository(
        specialties=seed.seed_specialties(),
        doctors=seed.seed_doctors(),
        patients=seed.seed_patients(),
        slots=seed.seed_slots(),
    )
