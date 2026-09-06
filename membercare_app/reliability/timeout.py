import concurrent.futures
from collections.abc import Callable
from contextvars import copy_context
from typing import Any


class OperationTimeoutError(TimeoutError):
    """
    Raised when an operation does not complete within
    the configured timeout.
    """

    def __init__(
        self,
        message: str,
        *,
        timeout_seconds: float,
    ):
        super().__init__(message)

        self.timeout_seconds = timeout_seconds


def execute_with_timeout(
    operation: Callable[[], Any],
    *,
    timeout_seconds: float,
) -> Any:
    """
    Execute a synchronous operation with a bounded wait time.

    The current ContextVar context is copied into the worker
    thread so trusted request context such as:

        request_id
        user_id
        user_role
        member_id
        session_id

    remains available to deterministic tools.

    If the operation does not complete within timeout_seconds,
    raise OperationTimeoutError.
    """

    if timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds must be greater than 0"
        )

    # ========================================================
    # COPY CURRENT REQUEST CONTEXT
    # ========================================================
    #
    # ThreadPoolExecutor runs the operation in another thread.
    # ContextVars do not automatically propagate into arbitrary
    # worker threads.
    #
    # copy_context() captures the trusted request context so the
    # tool continues to see the authenticated member identity.
    # ========================================================

    current_context = copy_context()

    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1
    )

    # Run the operation inside the copied ContextVar context.
    future = executor.submit(
        current_context.run,
        operation,
    )

    try:
        return future.result(
            timeout=timeout_seconds
        )

    except concurrent.futures.TimeoutError as exc:

        future.cancel()

        raise OperationTimeoutError(
            (
                "Operation exceeded timeout of "
                f"{timeout_seconds} seconds"
            ),
            timeout_seconds=timeout_seconds,
        ) from exc

    finally:
        executor.shutdown(
            wait=False,
            cancel_futures=True,
        )