import threading
import time
from collections.abc import Callable
from typing import Any


class CircuitBreakerOpenError(Exception):
    """
    Raised when the circuit breaker is OPEN and calls
    to the dependency are temporarily blocked.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float,
    ):
        super().__init__(message)

        self.retry_after_seconds = retry_after_seconds


class CircuitBreaker:
    """
    Simple thread-safe circuit breaker.

    States:

        CLOSED
            Normal operation.

        OPEN
            Dependency considered unhealthy.
            Calls fail immediately.

        HALF_OPEN
            Cooldown expired.
            One recovery attempt is allowed.
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 5.0,
    ):
        if failure_threshold < 1:
            raise ValueError(
                "failure_threshold must be at least 1"
            )

        if recovery_timeout_seconds <= 0:
            raise ValueError(
                "recovery_timeout_seconds must be greater than 0"
            )

        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = (
            recovery_timeout_seconds
        )

        self._state = self.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None

        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    def _before_call(self) -> None:
        """
        Decide whether this dependency call is allowed.
        """

        with self._lock:

            if self._state == self.CLOSED:
                return

            if self._state == self.OPEN:

                assert self._opened_at is not None

                elapsed = (
                    time.monotonic()
                    - self._opened_at
                )

                remaining = (
                    self.recovery_timeout_seconds
                    - elapsed
                )

                if remaining > 0:
                    raise CircuitBreakerOpenError(
                        "Circuit breaker is OPEN",
                        retry_after_seconds=remaining,
                    )

                # Cooldown has expired.
                # Allow a recovery probe.
                self._state = self.HALF_OPEN
                return

            # HALF_OPEN means a recovery attempt is already
            # being considered.
            #
            # For this first implementation, allow the call.
            return

    def _record_success(self) -> None:
        """
        Successful call closes the circuit and clears
        previous failure history.
        """

        with self._lock:
            self._state = self.CLOSED
            self._failure_count = 0
            self._opened_at = None

    def _record_failure(self) -> None:
        """
        Record a dependency failure.
        """

        with self._lock:

            # Failure during HALF_OPEN means recovery failed.
            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
                self._failure_count = (
                    self.failure_threshold
                )
                self._opened_at = time.monotonic()
                return

            self._failure_count += 1

            if (
                self._failure_count
                >= self.failure_threshold
            ):
                self._state = self.OPEN
                self._opened_at = time.monotonic()

    def execute(
        self,
        operation: Callable[[], Any],
        *,
        failure_exceptions: tuple[
            type[Exception],
            ...
        ] = (
            ConnectionError,
            TimeoutError,
        ),
    ) -> Any:
        """
        Execute one dependency operation through the
        circuit breaker.

        Only configured dependency failures contribute
        to opening the circuit.
        """

        self._before_call()

        try:
            result = operation()

        except failure_exceptions:
            self._record_failure()
            raise

        except Exception:
            # Business/application exceptions do not
            # automatically mark the dependency unhealthy.
            raise

        self._record_success()

        return result