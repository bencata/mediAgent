"""Engine and sessions: how the app talks to PostgreSQL.

  Engine  - owns the pool of connections to the database (one per process).
  Session - one conversation with the DB: it tracks the objects you loaded or
            added, and wraps your work in ONE transaction.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL

# pool_pre_ping: test a pooled connection before using it, so a connection the
# database closed (restart, idle timeout) is replaced instead of failing a request.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# A factory for sessions. expire_on_commit=False keeps objects readable after
# commit (otherwise SQLAlchemy would re-query them on next attribute access).
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """One session = one transaction = one HTTP request.

    FastAPI runs the code up to `yield`, hands the session to the endpoint's
    dependencies, and runs the rest after the endpoint finishes:
      - no exception  -> commit  (everything the request did becomes permanent)
      - any exception -> rollback (nothing it did is kept)

    TRAP (verified on our FastAPI version): by default the code after `yield`
    runs AFTER the response was sent. If the commit fails there, the client
    has already received "201 Created" for a booking that was never saved.
    So endpoints must use `Depends(get_session, scope="function")`, which
    runs the cleanup right after the endpoint returns and BEFORE the response
    is sent (a failed commit then becomes a 500).
    """
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
