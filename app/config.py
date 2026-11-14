"""Settings shared by the app and by Alembic (one source of truth)."""

import os
from datetime import date, datetime
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


def clinic_date(moment: datetime) -> date:
    """The calendar day `moment` falls on, on the CLINIC's calendar.

    The single place that answers "which day is this?". Used for today's date
    (referral validity) and for a slot's date (one booking per specialty per
    day), so the two can never disagree. `moment` must be time-zone aware.
    """
    return moment.astimezone(CLINIC_TZ).date()
