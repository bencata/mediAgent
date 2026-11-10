"""Demo data: 3 specialties, 5 doctors, 10 patients, 30 slots.

Fixed dates (no datetime.now()) so the data is identical on every run -
that makes manual testing and, later, automated tests predictable.
"""

from datetime import datetime, timedelta

from app.schemas import Doctor, Patient, Slot, Specialty


def seed_specialties() -> list[Specialty]:
    return [
        Specialty(id=1, name="Cardiology"),
        Specialty(id=2, name="Dermatology"),
        Specialty(id=3, name="Orthopedics"),
    ]


def seed_doctors() -> list[Doctor]:
    return [
        Doctor(id=1, name="Dr. Noa Levi", specialty_id=1),
        Doctor(id=2, name="Dr. Amit Cohen", specialty_id=1),
        Doctor(id=3, name="Dr. Tamar Shapira", specialty_id=2),
        Doctor(id=4, name="Dr. Yoav Mizrahi", specialty_id=2),
        Doctor(id=5, name="Dr. Dana Peretz", specialty_id=3),
    ]


def seed_patients() -> list[Patient]:
    names = [
        "Ben Catalan", "Maya Katz", "Omer Ben-David", "Shir Azulay",
        "Eitan Golan", "Lior Friedman", "Yael Avraham", "Itai Dahan",
        "Roni Biton", "Noga Hadad",
    ]
    return [Patient(id=i, name=name) for i, name in enumerate(names, start=1)]


def seed_slots() -> list[Slot]:
    """Each doctor gets 6 slots of 30 minutes: 3 on each of two days."""
    first_day = datetime(2026, 11, 16, 9, 0)  # a Monday, 09:00
    slots: list[Slot] = []
    slot_id = 1
    for doctor in seed_doctors():
        for day_offset in (0, 1):
            for slot_index in range(3):  # 09:00, 09:30, 10:00
                start = first_day + timedelta(days=day_offset, minutes=30 * slot_index)
                slots.append(
                    Slot(
                        id=slot_id,
                        doctor_id=doctor.id,
                        start_time=start,
                        end_time=start + timedelta(minutes=30),
                        is_available=True,
                    )
                )
                slot_id += 1
    return slots
