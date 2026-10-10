"""Skill CLI script: Compute the deterministic heuristic Match score between a lost and found report."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scoring import score_report_pair


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute heuristic Match score via backend/scoring.py.")
    parser.add_argument("--lost", required=True, help="JSON string of lost report")
    parser.add_argument("--found", required=True, help="JSON string of found report")
    args = parser.parse_args()

    lost_dict = json.loads(args.lost)
    found_dict = json.loads(args.found)
    result = score_report_pair(lost_dict, found_dict)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
