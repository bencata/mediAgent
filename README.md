# MediAgent

A backend for booking doctor appointments. Eventually a patient will chat with
an LLM agent that books for them; the backend, not the model, makes every decision.

**Current status: Stage 1 - Core API (no AI, in-memory data).**

## Run it

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv run uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive docs (try requests in the browser): http://127.0.0.1:8000/docs

Data lives in memory and resets on every restart.

## Endpoints

| Method | Path | Description | Auth header |
|---|---|---|---|
| GET | `/health` | Liveness check | no |
| GET | `/specialties` | List specialties | no |
| GET | `/appointments/slots?specialty_id=1` | Available slots (filter optional) | no |
| GET | `/appointments/me` | The caller's appointments | `X-Patient-Id` |
| POST | `/appointments` | Book a slot | `X-Patient-Id` |

`X-Patient-Id` is a **Stage 1 stand-in for authentication** and is not secure.
It is replaced by a signed token in a later stage.

Demo data: 3 specialties, 5 doctors, 10 patients (ids 1-10), 30 slots (ids 1-30).

## Example requests

List specialties:

```bash
curl http://127.0.0.1:8000/specialties
```

Available slots for specialty 1 (Cardiology):

```bash
curl "http://127.0.0.1:8000/appointments/slots?specialty_id=1"
```

Book slot 1 as patient 1:

```bash
curl -X POST http://127.0.0.1:8000/appointments \
  -H "X-Patient-Id: 1" -H "Content-Type: application/json" \
  -d '{"slot_id": 1}'
```

Show patient 1's appointments:

```bash
curl http://127.0.0.1:8000/appointments/me -H "X-Patient-Id: 1"
```

## Status codes

| Code | When | Example response |
|---|---|---|
| 200 | Successful read | the list |
| 201 | Appointment created | the appointment |
| 401 | `X-Patient-Id` header missing | `{"detail":"Missing X-Patient-Id header"}` |
| 404 | Slot, patient or specialty does not exist | `{"detail":"Slot 99999 does not exist"}` |
| 409 | Slot exists but is already booked | `{"detail":"Slot 1 is already booked"}` |
| 422 | Malformed input (e.g. `slot_id` is `0` or `"abc"`) | validation details |

Booking a taken slot is **409, not 400**: the request is valid, but it conflicts
with the current state of the slot. A client should pick a different slot.

## Architecture

```
router  ->  service  ->  repository
HTTP        rules        storage
```

| Layer | Files | Responsibility |
|---|---|---|
| Routers | `app/routers/` | Parse the request, call the service, return the response. No rules. |
| Service | `app/services.py` | Business rules; raises domain errors. Knows nothing about HTTP. |
| Repository | `app/repositories.py` | Store and fetch data. No rules. |
| Schemas | `app/schemas.py` | Shape and validation of data crossing the API. |
| Errors | `app/errors.py`, `app/main.py` | Domain errors, mapped to HTTP codes in one place. |

## Known limitations (fixed in later stages)

- **Race condition:** booking is "check, then act". Two simultaneous requests can both
  pass the availability check and double-book a slot. Fixed with database constraints
  (Stage 2) and Redis holds (Stage 3).
- **Fake authentication:** `X-Patient-Id` can be forged (Stage 6).
- **In-memory data:** nothing survives a restart (Stage 2).
