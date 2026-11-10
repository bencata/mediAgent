"""Dependencies: things FastAPI builds and hands to our endpoints.

An endpoint declares `service: AppointmentService = Depends(get_service)`
and FastAPI calls get_service() for each request, passing the result in.
In tests we can swap any of these (app.dependency_overrides).
"""

from functools import lru_cache

from fastapi import Depends, Header, HTTPException

from app.repositories import InMemoryRepository, build_seeded_repository
from app.services import AppointmentService


@lru_cache
def get_repository() -> InMemoryRepository:
    # lru_cache makes this a singleton: ONE repository for the whole process.
    # Without it every request would get fresh data and bookings would vanish.
    return build_seeded_repository()


def get_service(
    repo: InMemoryRepository = Depends(get_repository),
) -> AppointmentService:
    return AppointmentService(repo)


def get_current_patient_id(x_patient_id: int | None = Header(default=None)) -> int:
    """Who is calling? Stage 1 stand-in for real authentication.

    The client sends a header `X-Patient-Id: 3`. This is NOT secure - anyone
    can claim to be anyone. Stage 6 replaces it with a signed JWT. We keep
    it behind this one function so that swap touches only this file.
    """
    if x_patient_id is None:
        raise HTTPException(status_code=401, detail="Missing X-Patient-Id header")
    return x_patient_id
