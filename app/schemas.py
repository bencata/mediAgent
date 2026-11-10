"""Pydantic schemas: the *shape of the data* that crosses our API boundary.

A schema does two jobs:
  1. Validation - bad input is rejected before our own code runs.
  2. Serialization - Python objects become JSON in the response.

Schemas are NOT the database. In Stage 2 we add separate DB models.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Specialty(BaseModel):
    id: int
    name: str  # e.g. "Cardiology"


class Doctor(BaseModel):
    id: int
    name: str
    specialty_id: int  # points to Specialty.id


class Patient(BaseModel):
    id: int
    name: str


class Slot(BaseModel):
    """One bookable time window with one doctor."""

    id: int
    doctor_id: int
    start_time: datetime
    end_time: datetime
    is_available: bool  # False once someone booked it


class AppointmentCreate(BaseModel):
    """What the CLIENT sends to POST /appointments.

    Only the slot. We do NOT accept a patient_id here: the server decides
    who the caller is, so a client can never book on behalf of someone else.
    """

    # gt=0 means "greater than 0": slot_id=0 or -5 fails validation (HTTP 422).
    slot_id: int = Field(gt=0)


class Appointment(BaseModel):
    """What the SERVER stores and returns."""

    id: int
    slot_id: int
    patient_id: int
    doctor_id: int
    created_at: datetime
