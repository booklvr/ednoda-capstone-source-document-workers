"""Source Document NLU candidate extractor.

This worker adapts the student NLU engine to Ednoda's stable v1 handoff and
node-candidates callback contract. Reconciled with Nick's integrated handler
(reads the text package from S3, normalizes candidate types to Ednoda's
contract, posts the full result via signed callback, and returns a compact
summary to Step Functions) plus our Stage A-E hardening.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("HOME", "/tmp")
os.environ.setdefault("HF_HOME", "/tmp/huggingface")
os.environ.setdefault("HF_HUB_CACHE", "/tmp/huggingface/hub")
os.environ.setdefault("TRANSFORMERS_CACHE", "/tmp/huggingface/transformers")
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", "/tmp/sentence-transformers")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

WORKER_ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = Path(__file__).resolve().parent
for path in (WORKER_ROOT, WORKER_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from shared.callback_post import (  # noqa: E402
    build_ubc_node_candidates_callback_body,
    try_post_ubc_node_candidates_callback,
)
from shared.contracts import (  # noqa: E402
    CANDIDATE_STATUS_FAILED,
    CANDIDATE_STATUS_READY,
    CANDIDATE_TYPE_EXPRESSION,
    CANDIDATE_TYPE_QUESTION,
    CANDIDATE_TYPE_VOCAB,
    WARNING_NO_CANDIDATES_FOUND,
)
from shared.event import WorkerEventError  # noqa: E402
from shared.s3_client import create_boto3_s3_client, read_object_bytes  # noqa: E402
from shared.ubc_input import (  # noqa: E402
    UbcCandidateExtractionInputV1,
    parse_ubc_candidate_extraction_input_v1,
)
from shared.worker_errors import is_transient_infrastructure_error  # noqa: E402

# A-E hardening modules (pure, dependency-free) — see
# 062526-candidate-quality-language-hardening.md.
from candidate_pruner import prune_candidates, resolve_max_candidates  # noqa: E402
from chunk_dedup import dedupe_overlapping_chunks  # noqa: E402
from preprocess import preprocess_text, resolve_target_language  # noqa: E402

# CANDIDATE_TYPE_UNKNOWN is not defined in our shared/contracts.py (only vocab,
# question, expression are). Define it locally — matching how labeller.py does —
# until Ednoda adds it to the shared contract.
CANDIDATE_TYPE_UNKNOWN = "unknown"

logger = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)
logger.setLevel(logging.INFO)

ALLOWED_CANDIDATE_TYPES = {
    CANDIDATE_TYPE_VOCAB,
    CANDIDATE_TYPE_EXPRESSION,
    CANDIDATE_TYPE_QUESTION,
    CANDIDATE_TYPE_UNKNOWN,
}
STUDENT_GRAMMAR_TYPE = "grammar"
DEFAULT_ANCHOR_WORDS_PATH = WORKER_DIR / "data" / "lexical_targets.txt"

SlidingWindowChunker: Any | None = None
NLULabeller: Any | None = None


def _log_info(message: str, **fields: Any) -> None:
    if fields:
        logger.info("%s %s", message, json.dumps(fields, default=str, sort_keys=True))
        return
    logger.info(message)


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _load_nlu_runtime() -> tuple[Any, Any]:
    """Lazy-load expensive NLU modules after Lambda init has completed."""
    global NLULabeller, SlidingWindowChunker

    if SlidingWindowChunker is None:
        from chunker import SlidingWindowChunker as RuntimeSlidingWindowChunker

        SlidingWindowChunker = RuntimeSlidingWindowChunker

    if NLULabeller is None:
        from labeller import NLULabeller as RuntimeNLULabeller

        NLULabeller = RuntimeNLULabeller

    return SlidingWindowChunker, NLULabeller


def _unwrap_event(event: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Accept direct v1 handoff or Ednoda's small invocation envelope."""
    if isinstance(event.get("candidateExtractionInput"), dict):
        attempt_number = event.get("attemptNumber") or 1
        return event["candidateExtractionInput"], _coerce_attempt_number(attempt_number)

    attempt_number = event.get("attemptNumber") or 1
    return event, _coerce_attempt_number(attempt_number)


def _coerce_attempt_number(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return 1
    return value


def _decode_json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as error:
        raise WorkerEventError(f"{label} must be valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise WorkerEventError(f"{label} must be a JSON object")
    return value


def _read_manifest(
    handoff: UbcCandidateExtractionInputV1,
    *,
    s3_client: Any,
) -> dict[str, Any]:
    raw = read_object_bytes(
        s3_client,
        bucket=handoff.extracted_text_package.manifest.bucket,
        key=handoff.extracted_text_package.manifest.key,
    )
    return _decode_json_bytes(raw, label="manifest")


def _read_plain_text(
    handoff: UbcCandidateExtractionInputV1,
    *,
    s3_client: Any,
) -> str:
    raw = read_object_bytes(
        s3_client,
        bucket=handoff.extracted_text_package.plain_text.bucket,
        key=handoff.extracted_text_package.plain_text.key,
    )
    return raw.decode("utf-8")


def _read_blocks_from_manifest(
    manifest: dict[str, Any],
    *,
    s3_client: Any,
) -> list[dict[str, Any]]:
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        return []

    block_index = outputs.get("blockIndex")
    if not isinstance(block_index, list):
        return []

    blocks: list[dict[str, Any]] = []
    for item in block_index:
        if not isinstance(item, dict):
            continue
        bucket = item.get("bucket")
        key = item.get("key")
        if not isinstance(bucket, str) or not isinstance(key, str):
            continue
        try:
            raw = read_object_bytes(s3_client, bucket=bucket, key=key)
            block = _decode_json_bytes(raw, label=f"block {key}")
        except Exception as error:
            logger.warning("Skipping unreadable text block %s: %s", key, error)
            continue
        blocks.append(block)

    return blocks


def load_anchor_words(path: Path = DEFAULT_ANCHOR_WORDS_PATH) -> frozenset[str]:
    if not path.exists():
        logger.warning("Lexical anchor file not found: %s", path)
        return frozenset()

    words: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.strip().lower()
        if word and not word.startswith("#"):
            words.add(word)
    return frozenset(words)


def _preprocess_blocks(
    blocks: list[dict[str, Any]],
    target_language: str,
) -> list[dict[str, Any]]:
    """Stage A on blocks: gate to the target language, then clean.

    Blocks feed question/grammar detection, so they get the same language gate as
    the plain text. Blocks emptied by the gate/cleaner are dropped.
    """
    cleaned: list[dict[str, Any]] = []
    for block in blocks:
        text = block.get("text")
        if not isinstance(text, str):
            continue
        cleaned_text = preprocess_text(text, target_language)
        if not cleaned_text.strip():
            continue
        cleaned.append({**block, "text": cleaned_text})
    return cleaned


def normalize_candidate_for_ednoda(candidate: dict[str, Any]) -> dict[str, Any]:
    """Map student/internal NLU labels into Ednoda's current candidate contract."""
    candidate_type = candidate.get("candidateType")
    metadata = candidate.get("metadata")
    normalized_metadata = metadata if isinstance(metadata, dict) else {}

    if candidate_type == STUDENT_GRAMMAR_TYPE:
        return {
            **candidate,
            "candidateType": CANDIDATE_TYPE_EXPRESSION,
            "metadata": {
                **normalized_metadata,
                "nluCandidateType": STUDENT_GRAMMAR_TYPE,
            },
        }

    if candidate_type not in ALLOWED_CANDIDATE_TYPES:
        return {
            **candidate,
            "candidateType": CANDIDATE_TYPE_UNKNOWN,
            "metadata": {
                **normalized_metadata,
                "nluCandidateType": candidate_type or "missing",
                "contractNormalization": "mapped_to_unknown",
            },
        }

    if metadata is None:
        return {**candidate, "metadata": None}
    if isinstance(metadata, dict):
        return candidate
    return {
        **candidate,
        "metadata": {"rawMetadata": str(metadata)},
    }


def normalize_candidates_for_ednoda(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for candidate in candidates:
        text = candidate.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        normalized.append(normalize_candidate_for_ednoda(candidate))
    return normalized


def build_candidate_branch_result(
    *,
    status: str,
    candidates: list[dict[str, Any]],
    warnings: list[str] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "candidates": candidates,
        "warnings": warnings or [],
        "error": error,
    }


def process_candidate_extraction(
    handoff: UbcCandidateExtractionInputV1,
    *,
    s3_client: Any | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    _log_info(
        "nlu_candidate_extraction_started",
        sourceDocumentId=handoff.source_document_id,
        extractionId=handoff.extraction_id,
        environment=handoff.environment,
    )
    client = s3_client or create_boto3_s3_client()

    try:
        manifest = _read_manifest(handoff, s3_client=client)
        plain_text = _read_plain_text(handoff, s3_client=client)
        blocks = _read_blocks_from_manifest(manifest, s3_client=client)
        _log_info(
            "nlu_text_package_loaded",
            elapsedMs=_elapsed_ms(started_at),
            plainTextChars=len(plain_text),
            blockCount=len(blocks),
        )
    except Exception as error:
        if is_transient_infrastructure_error(error):
            raise
        _log_info(
            "nlu_text_package_unreadable",
            elapsedMs=_elapsed_ms(started_at),
            error=str(error),
        )
        return build_candidate_branch_result(
            status=CANDIDATE_STATUS_FAILED,
            candidates=[],
            error={
                "code": "text_package_unreadable",
                "message": str(error),
            },
        )

    # Stage A: gate to the target language (default English, config) and strip
    # scraped-data noise BEFORE chunking/scoring. Applies to plain text + blocks.
    target_language = resolve_target_language()
    cleaned_plain_text = preprocess_text(plain_text, target_language)
    cleaned_blocks = _preprocess_blocks(blocks, target_language)
    _log_info(
        "nlu_text_package_cleaned",
        elapsedMs=_elapsed_ms(started_at),
        targetLanguage=target_language,
        charsBefore=len(plain_text),
        cleanedChars=len(cleaned_plain_text),
        blockCountBefore=len(blocks),
        cleanedBlockCount=len(cleaned_blocks),
    )

    if not cleaned_blocks and cleaned_plain_text.strip():
        cleaned_blocks = [
            {
                "blockId": "plain-text",
                "text": cleaned_plain_text,
                "source": {},
            },
        ]

    _log_info("nlu_runtime_import_started", elapsedMs=_elapsed_ms(started_at))
    chunker_class, labeller_class = _load_nlu_runtime()

    _log_info("nlu_runtime_import_finished", elapsedMs=_elapsed_ms(started_at))
    chunks = chunker_class().chunk(cleaned_plain_text, cleaned_blocks)

    # Stage B: collapse the chunker's overlap so each sentence is scored once.
    raw_chunk_count = len(chunks)
    chunks = dedupe_overlapping_chunks(chunks)
    _log_info(
        "nlu_chunking_finished",
        elapsedMs=_elapsed_ms(started_at),
        rawChunkCount=raw_chunk_count,
        chunkCount=len(chunks),
        chunksCollapsed=raw_chunk_count - len(chunks),
    )

    # Stage C: target language threaded into the labeller (belt-and-suspenders).
    raw_candidates = labeller_class(
        anchor_words=load_anchor_words(),
        target_language=target_language,
    ).label(chunks, cleaned_blocks)
    normalized_candidates = normalize_candidates_for_ednoda(raw_candidates)

    # Stage D: quality pruning + redundancy reduction (earned reduction, not a
    # cap); a high configurable safety ceiling truncates with type balance only
    # if exceeded.
    prune_result = prune_candidates(
        normalized_candidates,
        max_candidates=resolve_max_candidates(),
    )
    candidates = prune_result.candidates
    _log_info(
        "nlu_labelling_finished",
        elapsedMs=_elapsed_ms(started_at),
        rawCandidateCount=len(raw_candidates),
        normalizedCandidateCount=len(normalized_candidates),
        candidateCount=len(candidates),
    )
    _log_info("nlu_candidates_pruned", elapsedMs=_elapsed_ms(started_at), **prune_result.stats)

    warnings: list[str] = []
    if not candidates:
        warnings.append(WARNING_NO_CANDIDATES_FOUND)

    return build_candidate_branch_result(
        status=CANDIDATE_STATUS_READY,
        candidates=candidates,
        warnings=warnings or None,
    )


def run_nlu_candidate_extraction_handoff(
    handoff_payload: dict[str, Any],
    *,
    attempt_number: int = 1,
    s3_client: Any | None = None,
    post_callback: bool = True,
    include_debug_payloads: bool = False,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        handoff = parse_ubc_candidate_extraction_input_v1(handoff_payload)
    except WorkerEventError as error:
        _log_info("nlu_invalid_handoff", error=str(error))
        return {
            "status": "invalid_handoff",
            "error": {"code": "invalid_handoff", "message": str(error)},
        }

    try:
        result = process_candidate_extraction(handoff, s3_client=s3_client)
    except Exception as error:
        if is_transient_infrastructure_error(error):
            raise
        result = build_candidate_branch_result(
            status=CANDIDATE_STATUS_FAILED,
            candidates=[],
            error={
                "code": "candidate_extraction_failed",
                "message": str(error),
            },
        )

    callback_body = build_ubc_node_candidates_callback_body(
        handoff,
        result,
        attempt_number=attempt_number,
    )

    if post_callback:
        _log_info(
            "nlu_callback_post_started",
            elapsedMs=_elapsed_ms(started_at),
            sourceDocumentId=handoff.source_document_id,
            extractionId=handoff.extraction_id,
            status=result["status"],
            candidateCount=len(result["candidates"]),
        )
        try_post_ubc_node_candidates_callback(handoff, callback_body)
        _log_info(
            "nlu_callback_post_finished",
            elapsedMs=_elapsed_ms(started_at),
            sourceDocumentId=handoff.source_document_id,
            extractionId=handoff.extraction_id,
        )

    response = {
        "status": result["status"],
        "handoffMode": "nlu_candidate_extractor",
        "candidateCount": len(result["candidates"]),
        "warnings": result.get("warnings") or [],
    }
    if result.get("error") is not None:
        response["error"] = result["error"]
    if include_debug_payloads:
        response["extractionResult"] = result
        response["callbackBody"] = callback_body
    return response


def handler(event: dict[str, Any], _context: Any | None = None) -> dict[str, Any]:
    _log_info(
        "nlu_lambda_handler_started",
        eventKeys=sorted(event.keys()) if isinstance(event, dict) else [],
    )
    # Top-level safety net (CLAUDE.md): the handler must never raise. Transient
    # infrastructure errors are re-raised so Step Functions/Lambda can retry;
    # everything else is turned into a failed result.
    try:
        if not isinstance(event, dict):
            raise WorkerEventError("event must be a JSON object")
        handoff_payload, attempt_number = _unwrap_event(event)
        result = run_nlu_candidate_extraction_handoff(
            handoff_payload,
            attempt_number=attempt_number,
        )
    except Exception as error:
        if is_transient_infrastructure_error(error):
            raise
        _log_info("nlu_lambda_handler_unhandled_error", error=str(error))
        result = {
            "status": CANDIDATE_STATUS_FAILED,
            "handoffMode": "nlu_candidate_extractor",
            "candidateCount": 0,
            "warnings": [],
            "error": {"code": "unhandled_error", "message": str(error)},
        }
    _log_info(
        "nlu_lambda_handler_finished",
        status=result.get("status"),
        candidateCount=result.get("candidateCount"),
        warnings=result.get("warnings"),
    )
    return result
