"""A few end-to-end tests through HTTP: routing, status codes, JSON bodies.

The rules themselves are tested in test_referral_rule.py; here we only check
that they reach the client correctly (status code + machine-readable `code`)
and that a successful request is really COMMITTED.
"""

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, engine, get_session
from app.dependencies import get_service
from app.main import app
from app.repositories import SqlRepository
from app.services import AppointmentService
from tests.helpers import (
    BEN,
    CARDIO_SLOT_DAY1,
    MAYA,
    NOGA,
    NOW,
    ORTHO_SLOT_DAY1,
    ORTHO_SLOT_DAY1_LATER,
)


@pytest.fixture
def client(fresh_db):
    # Swap in a service with a frozen clock; everything else is the real app.
    def service_with_frozen_clock(
        db: Session = Depends(get_session, scope="function"),
    ) -> AppointmentService:
        return AppointmentService(SqlRepository(db), clock=lambda: NOW)

    app.dependency_overrides[get_service] = service_with_frozen_clock
    yield TestClient(app)
    app.dependency_overrides.clear()


def book(client, patient_id, slot_id, **body):
    return client.post(
        "/appointments",
        json={"slot_id": slot_id, **body},
        headers={"X-Patient-Id": str(patient_id)},
    )


def test_specialties_tell_the_client_which_need_a_referral(client):
    by_name = {s["name"]: s["referral_required"] for s in client.get("/specialties").json()}
    assert by_name == {"Cardiology": True, "Dermatology": True, "Orthopedics": False}


def test_booking_with_a_valid_referral_returns_201(client):
    response = book(client, BEN, CARDIO_SLOT_DAY1, referral_id=1)
    assert response.status_code == 201
    assert response.json()["slot_id"] == CARDIO_SLOT_DAY1


def test_missing_referral_is_409_with_a_machine_readable_code(client):
    response = book(client, NOGA, CARDIO_SLOT_DAY1)
    assert response.status_code == 409
    assert response.json()["code"] == "referral_missing"
    assert "Cardiology" in response.json()["detail"]


def test_someone_elses_referral_is_403(client):
    response = book(client, MAYA, CARDIO_SLOT_DAY1, referral_id=1)
    assert response.status_code == 403


def test_a_taken_slot_is_409_with_its_own_code(client):
    assert book(client, NOGA, ORTHO_SLOT_DAY1).status_code == 201
    response = book(client, MAYA, ORTHO_SLOT_DAY1)
    assert response.status_code == 409
    assert response.json()["code"] == "slot_taken"


def test_a_second_booking_for_the_same_specialty_and_day_is_409(client):
    assert book(client, NOGA, ORTHO_SLOT_DAY1).status_code == 201
    response = book(client, NOGA, ORTHO_SLOT_DAY1_LATER)
    assert response.status_code == 409
    assert response.json()["code"] == "same_day_appointment"


@pytest.mark.parametrize("bad_id", [0, -3, "abc"])
def test_malformed_referral_id_is_422(client, bad_id):
    assert book(client, BEN, CARDIO_SLOT_DAY1, referral_id=bad_id).status_code == 422


def test_missing_patient_header_is_401(client):
    response = client.post("/appointments", json={"slot_id": CARDIO_SLOT_DAY1})
    assert response.status_code == 401


def test_a_successful_booking_is_committed_not_just_held_in_a_session(client):
    book(client, NOGA, ORTHO_SLOT_DAY1)
    engine.dispose()  # drop every pooled connection: whatever remains is in the DB
    response = client.get("/appointments/me", headers={"X-Patient-Id": str(NOGA)})
    assert [a["slot_id"] for a in response.json()] == [ORTHO_SLOT_DAY1]


def test_a_refused_booking_leaves_nothing_behind(client):
    assert book(client, NOGA, CARDIO_SLOT_DAY1).status_code == 409
    with SessionLocal() as check:
        assert SqlRepository(check).list_appointments_for_patient(NOGA) == []
