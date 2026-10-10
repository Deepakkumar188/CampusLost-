"""Skill CLI script: Generate a one-sentence match explanation with Gemma 4."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.gemma_client import explain_match_with_gemma
from backend.scoring import score_report_pair


def main() -> None:
    parser = argparse.ArgumentParser(description="Explain a lost/found match in one sentence with Gemma 4.")
    parser.add_argument("--lost", required=True, help="JSON string of lost report")
    parser.add_argument("--found", required=True, help="JSON string of found report")
    args = parser.parse_args()

    lost_dict = json.loads(args.lost)
    found_dict = json.loads(args.found)
    score_data = score_report_pair(lost_dict, found_dict)
    explanation = explain_match_with_gemma(lost_dict, found_dict, score_data)
    print(json.dumps({"match_score": score_data["match_score"], "explanation": explanation}, indent=2))


if __name__ == "__main__":
    main()
