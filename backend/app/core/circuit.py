"""Minimal thread-safe circuit breaker.

CACHE-002: outbound calls to the Pay Hero aggregator (and legacy Daraja
shim) had timeouts but no breaker. When the upstream degrades, every call
holds a worker thread + a DB pool slot for the full timeout window. The
breaker trips after N consecutive failures and fast-fails subsequent calls
with ``CircuitBreakerOpen`` for ``recovery_seconds``; one probe call is
allowed in HALF_OPEN to test the upstream before resuming full traffic.

No new dependency — kept dependency surface small and auditable.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitBreakerOpen(RuntimeError):
    """Raised by ``CircuitBreaker.call`` while the breaker is open."""


class CircuitBreaker:
    CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"

    def __init__(
        self,
        *,
        name: str,
        failure_threshold: int = 5,
        recovery_seconds: float = 30.0,
        expected_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        self.name = name
        self._lock = threading.Lock()
        self._state = self.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._expected = expected_exceptions

    @property
    def state(self) -> str:
        return self._state

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            if self._state == self.OPEN:
                if (time.monotonic() - self._opened_at) >= self._recovery_seconds:
                    self._state = self.HALF_OPEN
                    logger.info("Circuit '%s' entering HALF_OPEN — allowing probe call.", self.name)
                else:
                    raise CircuitBreakerOpen(f"Circuit '{self.name}' is open")
        try:
            result = fn(*args, **kwargs)
        except self._expected as exc:
            self._record_failure(exc)
            raise
        else:
            self._record_success()
            return result

    def _record_success(self) -> None:
        with self._lock:
            if self._state != self.CLOSED:
                logger.info("Circuit '%s' recovered — CLOSED.", self.name)
            self._state = self.CLOSED
            self._failures = 0
            self._opened_at = 0.0

    def _record_failure(self, exc: BaseException) -> None:
        with self._lock:
            self._failures += 1
            if self._state == self.HALF_OPEN or self._failures >= self._failure_threshold:
                self._state = self.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "Circuit '%s' OPEN after %d failures (last: %s)",
                    self.name, self._failures, exc.__class__.__name__,
                )


# Shared breakers — instantiated once at import time so all callers see the
# same state across the process.
payhero_breaker = CircuitBreaker(name="payhero", failure_threshold=5, recovery_seconds=30.0)
daraja_breaker = CircuitBreaker(name="daraja", failure_threshold=5, recovery_seconds=30.0)
