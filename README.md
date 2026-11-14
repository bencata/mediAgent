# MediAgent

A backend for booking doctor appointments. Eventually a patient will chat with
an LLM agent that books for them; the backend, not the model, makes every decision.

**Current status: Stage 2 - business rules and database (PostgreSQL, no AI yet).**

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
docker compose up -d --wait            # start PostgreSQL
uv run alembic upgrade head            # create the schema
uv run python -m app.db.seed           # load the demo data (safe to repeat)
uv run uvicorn app.main:app --reload   # start the API
```

- API: http://127.0.0.1:8000
- Interactive docs (try requests in the browser): http://127.0.0.1:8000/docs

Data lives in PostgreSQL and survives restarts. The database URL comes from
`DATABASE_URL` and defaults to the local Docker Compose database.

## Demo data

3 specialties, 5 doctors, 10 patients (ids 1-10), 30 slots (ids 1-30; half-hour slots on
the two days starting the next Monday). **Every date is relative to the day you seed**, so
a fresh demo always has referrals in each situation and slots in the future.

| Specialty | Needs a referral? | Doctors | Slots |
|---|---|---|---|
| 1 Cardiology | yes | 1, 2 | 1-12 |
| 2 Dermatology | yes | 3, 4 | 13-24 |
| 3 Orthopedics | no | 5 | 25-30 |

| Patient | Referral |
|---|---|
| 1 Ben | id 1: Cardiology, **valid** |
| 2 Maya | id 2: Dermatology, **valid** |
| 3 Omer | id 3: Cardiology, **expired** |
| 4 Shir | id 4: Cardiology, **not valid yet** |
| 5-10 | none |

The data does not follow the calendar after seeding. When a long-lived dev database has
gone stale, rebuild it (**this deletes all data**):

```bash
uv run python -m app.db.seed --reset
```

## Endpoints

| Method | Path | Description | Auth header |
|---|---|---|---|
| GET | `/health` | Liveness check | no |
| GET | `/specialties` | List specialties (with `referral_required`) | no |
| GET | `/appointments/slots?specialty_id=1` | Available slots (filter optional) | no |
| GET | `/appointments/me` | The caller's active appointments | `X-Patient-Id` |
| POST | `/appointments` | Book a slot: `{"slot_id": 1, "referral_id": 1}` | `X-Patient-Id` |

`referral_id` is optional; see the rules below. Times are shown in the clinic's time zone.

`X-Patient-Id` is a **stand-in for authentication** and is not secure. It is replaced
by a signed token in a later stage.

## Booking rules

The service checks these in order and stops at the first that fails:

1. The patient and the slot exist.
2. The slot is not already taken.
3. The patient has no active appointment for the same specialty on the same **clinic day**.
4. The referral rule:
   - A specialty without `referral_required` needs none; **sending one is rejected**, so
     the client never believes a referral was consumed when it was not.
   - If the client sends `referral_id`, exactly that referral is judged: it must belong to
     the caller, match the specialty, be inside its validity window and not be used yet.
   - If the client sends none, the patient's only usable referral is used. If several are
     usable the request is refused (`referral_ambiguous`): the server never guesses which
     one a patient meant.

Decisions behind them:

- **A referral is valid on the booking date**, both end dates inclusive; the appointment
  itself may be later. "Today" is the clinic's calendar day, never UTC and never the
  server's.
- **A referral is used** while an *active* appointment holds it; cancelling frees it.
- **The clinic's time zone** is `Asia/Jerusalem` (`app/config.py`). "Same day" in rule 3
  is the slot's date in that zone.
- **Someone else's referral and a nonexistent one both answer 403**, so referral ids
  cannot be probed.

## Status codes

Every refusal that has a stable reason carries a machine-readable `code` next to the
human-readable `detail`. Clients (and the future agent) should branch on `code`.

| Code | When | `code` |
|---|---|---|
| 200 | Successful read | |
| 201 | Appointment created | |
| 401 | `X-Patient-Id` header missing | |
| 403 | The referral is not the caller's (or does not exist) | |
| 404 | Slot, patient or specialty does not exist | |
| 409 | Slot already booked | `slot_taken` |
| 409 | Same specialty already booked that day | `same_day_appointment` |
| 409 | Referral rule refused the booking | `referral_missing`, `referral_expired`, `referral_not_yet_valid`, `referral_used`, `referral_wrong_specialty`, `referral_ambiguous`, `referral_not_required` |
| 422 | Malformed input (e.g. `slot_id` is `0`, `referral_id` is `"abc"`) | |

Example: `{"detail":"Cardiology requires a referral and you have none for it","code":"referral_missing"}`

All refusals about *state* are **409, not 400/403/422**: the request is well-formed and the
caller is known, but it conflicts with the current state of the system. 403 is kept for the
one case that is about *whose* resource it is.

## Example requests

```bash
curl http://127.0.0.1:8000/specialties
curl "http://127.0.0.1:8000/appointments/slots?specialty_id=1"
curl http://127.0.0.1:8000/appointments/me -H "X-Patient-Id: 1"
```

Book slot 1 (Cardiology) as patient 1 with their referral:

```bash
curl -X POST http://127.0.0.1:8000/appointments \
  -H "X-Patient-Id: 1" -H "Content-Type: application/json" \
  -d '{"slot_id": 1, "referral_id": 1}'
```

Book slot 25 (Orthopedics, no referral needed) as patient 5:

```bash
curl -X POST http://127.0.0.1:8000/appointments \
  -H "X-Patient-Id: 5" -H "Content-Type: application/json" \
  -d '{"slot_id": 25}'
```

## Architecture

```
router  ->  service  ->  repository  ->  PostgreSQL
HTTP        rules        storage          constraints
```

| Layer | Files | Responsibility |
|---|---|---|
| Routers | `app/routers/` | Parse the request, call the service, return the response. No rules. |
| Service | `app/services.py` | Business rules; raises domain errors. Knows nothing about HTTP or SQL. |
| Repository | `app/repositories.py` | Store and fetch; translates a refused write into `ConstraintViolation`. No rules. |
| Models | `app/db/models.py` | The tables and their constraints (SQLAlchemy). |
| Schemas | `app/schemas.py` | Shape and validation of data crossing the API (Pydantic). |
| Errors | `app/errors.py`, `app/main.py` | Domain errors, mapped to HTTP codes in one place. |
| Config | `app/config.py` | Database URL, the clinic time zone, `clinic_date()`. |

**Two lines of defence.** The service checks each rule first, to give a precise message.
But "check, then act" is not atomic: two simultaneous requests can both pass the check.
So the **database enforces the same rules itself**, and the service turns a refused write
into the same error:

| Rule | Database guard |
|---|---|
| One active appointment per slot | partial unique index `uq_appointments_active_slot` |
| One active appointment per patient, specialty, day | partial unique index `uq_appointments_active_patient_specialty_day` |
| A referral is consumed by at most one active appointment | partial unique index `uq_appointments_active_referral` |
| A doctor's slots never overlap | exclusion constraint `ex_slots_no_overlap` (needs `btree_gist`) |
| Slot ends after it starts; referral dates in order | CHECK constraints |

Each request runs in **one transaction**: committed when the endpoint succeeds, rolled back
on any error. The commit happens *before* the response is sent (`scope="function"` on the
session dependency): by default FastAPI would send the response first, and a failed commit
would leave the client holding a "201 Created" for a booking that was never saved.

## Migrations

The schema is managed with [Alembic](https://alembic.sqlalchemy.org/).

```bash
uv run alembic upgrade head       # create / update the schema
uv run alembic downgrade base     # drop everything again
uv run alembic check              # fail if models and migrations have drifted apart
```

After changing `app/db/models.py`, generate a migration with
`uv run alembic revision --autogenerate -m "describe the change"` and **read it before
committing**: autogenerate cannot detect extensions (e.g. `btree_gist`) or enum cleanup.

## Tests

```bash
uv run pytest
```

Tests run against a **real PostgreSQL** database named `mediagent_test` (created and migrated
automatically; wiped and re-seeded before every test; the suite refuses to run against a
database whose name does not end in `_test`). A real database is used on purpose: the
guarantees above are enforced *by the database*, which a fake could never prove. The clock is
injected and frozen, so no test depends on today's date.

| File | What it proves |
|---|---|
| `tests/test_referral_rule.py` | The referral rule, including window boundaries and clinic-vs-UTC days |
| `tests/test_same_day_rule.py` | One booking per specialty and clinic day |
| `tests/test_db_constraints.py` | The database refuses bad writes even when the service's checks are fooled |
| `tests/test_api.py` | Status codes, JSON bodies, and that successful bookings are committed |
| `tests/test_seed.py` | The seed is idempotent and its dates follow the day it is given |

## Known limitations (fixed in later stages)

- **No holds:** a patient cannot reserve a slot while deciding; that is Stage 3 (Redis holds,
  confirmation with an idempotency key). Double booking itself is already impossible.
- **Fake authentication:** `X-Patient-Id` can be forged (Stage 6).
- **Not yet enforced:** booking a slot in the past; overlapping appointments of one patient
  across different specialties; there is no cancel endpoint yet.
- **Seed dates go stale:** see `--reset` above.
