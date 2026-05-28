#!/usr/bin/env python3
"""Run candidate extraction heuristics over a local plain.txt file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKERS_DIR = ROOT / "workers"
CANDIDATE_DIR = WORKERS_DIR / "candidate-extractor-stub"
for path in (WORKERS_DIR, CANDIDATE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from heuristics import extract_candidates_from_plain_text  # noqa: E402
from shared.contracts import WARNING_NO_CANDIDATES_FOUND  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plain_text_file", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "local-output" / "candidate-result.json",
    )
    parser.add_argument("--source-document-id", type=int, default=42)
    parser.add_argument("--extraction-id", type=int, default=7)
    parser.add_argument("--attempt-number", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.plain_text_file.exists():
        raise FileNotFoundError(args.plain_text_file)

    plain_text = args.plain_text_file.read_text(encoding="utf-8")
    candidates = extract_candidates_from_plain_text(plain_text)
    body = {
        "version": "source-document-candidate-extraction-result.v1",
        "sourceDocumentId": args.source_document_id,
        "extractionId": args.extraction_id,
        "attemptNumber": args.attempt_number,
        "status": "ready",
        "candidates": candidates,
    }
    if not candidates:
        body["warnings"] = [WARNING_NO_CANDIDATES_FOUND]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(body, indent=2, ensure_ascii=False))
    print(f"\nWrote candidate result to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
