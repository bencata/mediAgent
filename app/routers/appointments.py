from fastapi import APIRouter, Depends

from app.dependencies import get_current_patient_id, get_service
from app.schemas import Appointment, AppointmentCreate, Slot
from app.services import AppointmentService

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("/slots", response_model=list[Slot])
def list_slots(
    specialty_id: int | None = None,  # optional query param: /slots?specialty_id=1
    service: AppointmentService = Depends(get_service),
):
    return service.list_available_slots(specialty_id)


@router.get("/me", response_model=list[Appointment])
def my_appointments(
    patient_id: int = Depends(get_current_patient_id),
    service: AppointmentService = Depends(get_service),
):
    return service.list_my_appointments(patient_id)


@router.post("", response_model=Appointment, status_code=201)
def book_appointment(
    body: AppointmentCreate,  # FastAPI parses + validates the JSON body here
    patient_id: int = Depends(get_current_patient_id),  # from the server, NOT the body
    service: AppointmentService = Depends(get_service),
):
    return service.book_appointment(patient_id, body.slot_id, body.referral_id)
