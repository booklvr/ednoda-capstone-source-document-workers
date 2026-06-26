"""Stage E observability on the UBC-handoff handler.

See 062526-candidate-quality-language-hardening.md. Per-stage reductions
(chunks collapsed, candidates pruned) must be visible in logs.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

WORKER_ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = WORKER_ROOT / "candidate-extractor-nlu"
for path in (WORKER_ROOT, WORKER_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from tests.test_handler_preprocessing import (  # noqa: E402
    load_handler_module,
    make_fake_s3,
    make_handoff,
)


class HandlerObservabilityTests(unittest.TestCase):
    def test_emits_stage_counts_including_prune_stats(self) -> None:
        module = load_handler_module()

        class FakeLabeller:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def label(self, chunks: list[dict], blocks: list[dict]) -> list[dict]:
                return [
                    {"candidateType": "vocab", "text": "photosynthesis",
                     "normalizedText": "photosynthesis", "confidence": 0.9, "metadata": {}},
                    {"candidateType": "vocab", "text": "the",
                     "normalizedText": "the", "confidence": 0.5, "metadata": {}},
                ]

        module.NLULabeller = FakeLabeller
        fake = make_fake_s3("Some English content here. Another sentence here.", ["Some English content here."])
        handoff = module.parse_ubc_candidate_extraction_input_v1(make_handoff())

        with self.assertLogs(module.logger, level="INFO") as logs:
            module.process_candidate_extraction(handoff, s3_client=fake)

        output = "\n".join(logs.output)
        self.assertIn("nlu_candidates_pruned", output)
        self.assertIn("droppedLowQuality", output)
        self.assertIn("chunksCollapsed", output)


if __name__ == "__main__":
    unittest.main()
