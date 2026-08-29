"""billing_lock serialises billing runs: the daily cron and Task 8's console
'Run billing now' button both wrap their work in this lock, so only one
billing run can be touching the database at a time.
"""
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.services.subscription_billing import BILLING_LOCK_KEY, billing_lock


def test_second_acquisition_fails_while_the_first_is_held(engine):
    """Two separate sessions: the second must not acquire the lock while
    the first still holds it, proving the lock is real (server-side,
    session-level) rather than a no-op or a Python-side lock."""
    Session = sessionmaker(bind=engine)
    first = Session()
    second = Session()
    try:
        with billing_lock(first) as first_acquired:
            assert first_acquired is True
            with billing_lock(second) as second_acquired:
                assert second_acquired is False
    finally:
        first.close()
        second.close()


def test_lock_is_released_once_the_holder_exits(engine):
    """Once the first run's `with` block exits, a later run can acquire it.

    This is the regression guard for the stranded-lock bug. billing_lock holds
    a dedicated connection for the whole run, because a billing run commits
    once per subscription and SQLAlchemy returns the Session's connection to
    the pool on commit. The earlier implementation locked on the Session, so
    the later pg_advisory_unlock could run on a different connection, return
    false, and leave the lock held forever on an idle pooled connection. Every
    later run would then report "already in progress" while the cron exited 0,
    and no hospital would ever be invoiced again.

    HONEST LIMITATION: this asserts the invariant (no advisory lock survives
    the block) but it does NOT reproduce the original bug on demand. Stranding
    required a commit inside the lock AND the pool handing the unlock a
    different physical connection, and that coincidence cannot be forced
    deterministically here: reverting billing_lock to lock on the Session
    still passes this test, because in an isolated run the unlock lands on the
    same connection that took the lock. The fix itself was verified by
    inspection instead: billing_lock holds its own connection across every
    commit and closes it in a finally, and Postgres always drops a backend's
    advisory locks on disconnect, so closure releases the lock even if the
    explicit unlock never runs. Treat this test as a guard on the release
    path, not as proof the pool race cannot return.
    """
    Session = sessionmaker(bind=engine)
    first = Session()
    second = Session()
    try:
        with billing_lock(first) as acquired:
            assert acquired is True

        with billing_lock(second) as acquired:
            assert acquired is True
    finally:
        first.close()
        second.close()
