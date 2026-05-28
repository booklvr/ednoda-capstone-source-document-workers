"""Worker processing limit resolution from environment variables."""

from __future__ import annotations

import os
import time

from shared.contracts import (
    DEFAULT_MAX_BLOCKS,
    DEFAULT_MAX_CHUNKS,
    DEFAULT_MAX_EXTRACTION_CHARS,
    DEFAULT_MAX_PREVIEW_PAGES,
    DEFAULT_MAX_PROCESSING_SECONDS,
    DEFAULT_MAX_TABLE_ROWS_FOR_PREVIEW,
)


def _resolve_positive_int(env_name: str, default: int) -> int:
    configured = os.environ.get(env_name, "").strip()
    if not configured:
        return default
    try:
        return max(1, int(configured))
    except ValueError:
        return default


def resolve_max_preview_pages() -> int:
    return _resolve_positive_int("MAX_PREVIEW_PAGES", DEFAULT_MAX_PREVIEW_PAGES)


def resolve_max_table_rows_for_preview() -> int:
    return _resolve_positive_int(
        "MAX_TABLE_ROWS_FOR_PREVIEW",
        DEFAULT_MAX_TABLE_ROWS_FOR_PREVIEW,
    )


def resolve_max_extraction_chars() -> int:
    return _resolve_positive_int(
        "MAX_EXTRACTION_CHARS",
        DEFAULT_MAX_EXTRACTION_CHARS,
    )


def resolve_max_blocks() -> int:
    return _resolve_positive_int("MAX_BLOCKS", DEFAULT_MAX_BLOCKS)


def resolve_max_chunks() -> int:
    return _resolve_positive_int("MAX_CHUNKS", DEFAULT_MAX_CHUNKS)


def resolve_max_processing_seconds() -> int:
    return _resolve_positive_int(
        "MAX_PROCESSING_SECONDS",
        DEFAULT_MAX_PROCESSING_SECONDS,
    )


class ProcessingDeadline:
    """Wall-clock budget helper for worker invocations."""

    def __init__(self, max_seconds: int) -> None:
        self._started_at = time.monotonic()
        self._max_seconds = max_seconds

    def exceeded(self) -> bool:
        return (time.monotonic() - self._started_at) >= self._max_seconds

    def remaining_seconds(self) -> float:
        return max(0.0, self._max_seconds - (time.monotonic() - self._started_at))
