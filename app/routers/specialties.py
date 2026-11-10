from fastapi import APIRouter, Depends

from app.dependencies import get_service
from app.schemas import Specialty
from app.services import AppointmentService

router = APIRouter(prefix="/specialties", tags=["specialties"])


@router.get("", response_model=list[Specialty])
def list_specialties(service: AppointmentService = Depends(get_service)):
    # A router stays THIN: take the request, call the service, return.
    # No business rules here.
    return service.list_specialties()
