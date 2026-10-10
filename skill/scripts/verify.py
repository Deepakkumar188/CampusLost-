"""Skill CLI script: Verify an ownership claim answer (exact normalised match first, Gemma 4 fuzzy fallback)."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.gemma_client import verify_ownership_answer


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ownership claim answer.")
    parser.add_argument("--question", required=True, help="Verification question")
    parser.add_argument("--expected", required=True, help="Expected private answer")
    parser.add_argument("--answer", required=True, help="Claimant's submitted answer")
    args = parser.parse_args()

    matched, method, reason = verify_ownership_answer(
        question=args.question,
        expected_answer=args.expected,
        user_answer=args.answer,
    )
    print(
        json.dumps(
            {"verified": matched, "method": method, "reason": reason},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
