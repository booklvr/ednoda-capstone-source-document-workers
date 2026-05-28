"""Unit tests for shared worker error classification."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[2]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from shared.worker_errors import is_transient_infrastructure_error  # noqa: E402


class WorkerErrorClassificationTests(unittest.TestCase):
    def test_slow_down_client_error_is_transient(self) -> None:
        from botocore.exceptions import ClientError

        error = ClientError(
            {
                "Error": {"Code": "SlowDown", "Message": "reduce request rate"},
                "ResponseMetadata": {"HTTPStatusCode": 503},
            },
            "GetObject",
        )
        self.assertTrue(is_transient_infrastructure_error(error))

    def test_no_such_key_client_error_is_not_transient(self) -> None:
        from botocore.exceptions import ClientError

        error = ClientError(
            {
                "Error": {"Code": "NoSuchKey", "Message": "not found"},
                "ResponseMetadata": {"HTTPStatusCode": 404},
            },
            "GetObject",
        )
        self.assertFalse(is_transient_infrastructure_error(error))

    def test_value_error_is_not_transient(self) -> None:
        self.assertFalse(is_transient_infrastructure_error(ValueError("bad pdf")))

    def test_timeout_error_is_transient(self) -> None:
        self.assertTrue(is_transient_infrastructure_error(TimeoutError()))


if __name__ == "__main__":
    unittest.main()
