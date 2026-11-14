"""Dependencies: things FastAPI builds and hands to our endpoints.

An endpoint declares `service: AppointmentService = Depends(get_service)`
and FastAPI calls get_service() for each request, passing the result in.
In tests we can swap any of these (app.dependency_overrides).
"""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.repositories import SqlRepository
from app.services import AppointmentService


def get_repository(
    # scope="function": commit/rollback runs right after the endpoint returns,
    # BEFORE the response is sent (see the TRAP in app/db/session.py).
    session: Session = Depends(get_session, scope="function"),
) -> SqlRepository:
    # A NEW repository per request, around that request's own session
    # (the old in-memory version had to be one shared singleton).
    return SqlRepository(session)


def get_service(
    repo: SqlRepository = Depends(get_repository),
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
