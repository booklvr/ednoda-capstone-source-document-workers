"""Classify worker exceptions at Lambda handler boundaries."""

from __future__ import annotations

TRANSIENT_AWS_ERROR_CODES = frozenset(
    {
        "InternalError",
        "ServiceUnavailable",
        "SlowDown",
        "RequestTimeout",
        "RequestTimeoutException",
        "Throttling",
        "ThrottlingException",
        "TooManyRequestsException",
        "ProvisionedThroughputExceededException",
    }
)

TRANSIENT_HTTP_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def is_transient_infrastructure_error(error: BaseException) -> bool:
    """Return True when the handler should re-raise for orchestration retry."""
    try:
        from botocore.exceptions import (
            BotoCoreError,
            ClientError,
            ConnectionError as BotoConnectionError,
            EndpointConnectionError,
            ReadTimeoutError,
        )
    except ImportError:
        return isinstance(error, (TimeoutError, OSError))

    if isinstance(error, (BotoConnectionError, EndpointConnectionError, ReadTimeoutError)):
        return True

    if isinstance(error, ClientError):
        response = error.response or {}
        err = response.get("Error") or {}
        code = str(err.get("Code") or "")
        if code in TRANSIENT_AWS_ERROR_CODES:
            return True
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status in TRANSIENT_HTTP_STATUS_CODES:
            return True
        return False

    if isinstance(error, BotoCoreError):
        return True

    if isinstance(error, TimeoutError):
        return True

    if isinstance(error, OSError):
        import errno

        if error.errno in {
            errno.ECONNRESET,
            errno.ETIMEDOUT,
            errno.EHOSTUNREACH,
            errno.ENETUNREACH,
        }:
            return True

    return False
