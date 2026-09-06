import time
from collections.abc import Callable
from typing import Any


class RetryExhaustedError(Exception):
    """
    Raised when a transient operation continues failing
    after all configured attempts have been exhausted.
    """

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_exception: Exception,
    ):
        super().__init__(message)

        self.attempts = attempts
        self.last_exception = last_exception


def execute_with_retry(
    operation: Callable[[], Any],
    *,
    max_attempts: int = 3,
    initial_delay_seconds: float = 0.25,
    backoff_multiplier: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
    ),
    on_retry: Callable[
        [int, Exception, float],
        None,
    ]
    | None = None,
) -> Any:
    """
    Execute an operation with bounded retry.

    Example with default settings:

        attempt 1
            failure
            wait 0.25 sec

        attempt 2
            failure
            wait 0.50 sec

        attempt 3
            success

    Only configured transient exception types are retried.

    Non-retryable exceptions fail immediately.
    """

    if max_attempts < 1:
        raise ValueError(
            "max_attempts must be at least 1"
        )

    delay = initial_delay_seconds

    last_exception: Exception | None = None

    for attempt in range(
        1,
        max_attempts + 1,
    ):

        try:
            return operation()

        except retryable_exceptions as exc:

            last_exception = exc

            # No retries remain.
            if attempt >= max_attempts:
                break

            if on_retry is not None:
                on_retry(
                    attempt,
                    exc,
                    delay,
                )

            time.sleep(
                delay
            )

            delay *= backoff_multiplier

    assert last_exception is not None

    raise RetryExhaustedError(
        (
            "Operation failed after "
            f"{max_attempts} attempts"
        ),
        attempts=max_attempts,
        last_exception=last_exception,
    )