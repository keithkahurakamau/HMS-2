"""billing_lock serialises billing runs: the daily cron and Task 8's console
'Run billing now' button both wrap their work in this lock, so only one
billing run can be touching the database at a time.
"""
from sqlalchemy.orm import sessionmaker

from app.services.subscription_billing import billing_lock


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
    """Once the first run's `with` block exits, a later run can acquire it,
    so one billing run does not permanently starve every run after it."""
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
