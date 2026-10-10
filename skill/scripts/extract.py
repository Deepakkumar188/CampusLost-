"""Skill CLI script: Extract structured features from a lost/found report using Gemma 4."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.gemma_client import extract_features_with_gemma


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract structured features with Gemma 4.")
    parser.add_argument("--type", choices=["lost", "found"], default="lost")
    parser.add_argument("--text", required=True, help="Report description in English, Hindi, or Hinglish")
    args = parser.parse_args()

    features = extract_features_with_gemma(text=args.text, report_type=args.type)
    print(json.dumps(features.model_dump(), indent=2))


if __name__ == "__main__":
    main()
