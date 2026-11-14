"""Settings shared by the app and by Alembic (one source of truth)."""

import os
from zoneinfo import ZoneInfo

# Defaults match docker-compose.yml: local development credentials only.
# "+psycopg" selects the psycopg 3 driver.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://mediagent:mediagent@localhost:5432/mediagent",
)

# The clinic's time zone. "What day is it?" is only meaningful relative to a
# time zone, and our business rules (referral validity, one booking per
# patient per day) are defined in the CLINIC's local calendar - not UTC and
# not the patient's. Always an IANA name via zoneinfo, never a fixed "+02:00"
# offset: the real offset changes with daylight saving time.
CLINIC_TZ = ZoneInfo("Asia/Jerusalem")
