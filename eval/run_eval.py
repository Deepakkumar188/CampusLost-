"""Evaluation harness (`eval/run_eval.py`) for CampusLost+.

Evaluates `scoring.py` across labelled ground-truth pairs (including Hinglish
descriptions, missing-photo weight normalisation, and decoy backpack separation)
and prints Top-1 accuracy, Top-3 accuracy, and a per-query Markdown table.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db import get_report_by_id, list_reports
from backend.scoring import load_zones_config, rank_matches_for_report
from seed import seed_database


# Ground-truth labelled pairs: (lost_seed_key, expected_found_seed_key, scenario_label)
GROUND_TRUTH_PAIRS = [
    ("L1_BOTTLE_HINGLISH", "F1_BOTTLE_TRUE", "Hinglish Milton Bottle (LHC)"),
    ("L2_BAG_TRUE", "F2_BAG_TRUE", "Wildcraft Bag vs 2 Black Decoy Bags (Lab 2)"),
    ("L3_CALC_TRUE", "F5_CALC_TRUE", "Casio Calculator without Lost Photo (Library)"),
    ("L4_IDCARD_SENSITIVE", "F6_IDCARD_SENSITIVE", "Sensitive Student ID Card with Redacted PII (Mess)"),
]


def run_evaluation() -> dict:
    """Seed a temporary evaluation DB, rank candidates for each labelled pair, and report metrics."""
    eval_db = PROJECT_ROOT / "eval_temp.db"
    try:
        key_to_id = seed_database(db_path=eval_db)
        found_candidates = list_reports(report_type="found", status="open", db_path=eval_db)
        zones_cfg = load_zones_config()

        top1_hits = 0
        top3_hits = 0
        rows = []

        for lost_key, expected_found_key, label in GROUND_TRUTH_PAIRS:
            lost_id = key_to_id[lost_key]
            expected_found_id = key_to_id[expected_found_key]
            lost_report = get_report_by_id(lost_id, db_path=eval_db)

            ranked = rank_matches_for_report(
                source_report=lost_report,
                candidate_reports=found_candidates,
                top_k=3,
                zones_config=zones_cfg,
            )
            ranked_ids = [cand["id"] for cand, _ in ranked]
            top_score = ranked[0][1]["match_score"] if ranked else 0.0
            runner_up_score = ranked[1][1]["match_score"] if len(ranked) > 1 else 0.0

            is_top1 = len(ranked_ids) >= 1 and ranked_ids[0] == expected_found_id
            is_top3 = expected_found_id in ranked_ids[:3]

            if is_top1:
                top1_hits += 1
            if is_top3:
                top3_hits += 1

            rank_pos = (ranked_ids.index(expected_found_id) + 1) if is_top3 else None
            rows.append(
                {
                    "scenario": label,
                    "lost_id": lost_id,
                    "expected_found_id": expected_found_id,
                    "predicted_top1_id": ranked_ids[0] if ranked_ids else None,
                    "rank": rank_pos,
                    "top1_score": top_score,
                    "runner_up_score": runner_up_score,
                    "top1_hit": is_top1,
                    "top3_hit": is_top3,
                }
            )

        total = len(GROUND_TRUTH_PAIRS)
        top1_acc = (top1_hits / total) * 100.0
        top3_acc = (top3_hits / total) * 100.0

        print("\n=== CampusLost+ Heuristic Match Score Evaluation ===")
        print(f"Labelled Queries Evaluated : {total}")
        print(f"Found Candidates Pool      : {len(found_candidates)} (includes 2 near-identical decoy bags)")
        print(f"Top-1 Accuracy             : {top1_hits}/{total} ({top1_acc:.1f}%)")
        print(f"Top-3 Accuracy             : {top3_hits}/{total} ({top3_acc:.1f}%)\n")

        print("| Scenario | Lost # | True Found # | Rank | Top-1 Match Score | Runner-Up Score | Top-1 | Top-3 |")
        print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for r in rows:
            print(
                f"| {r['scenario']} | #{r['lost_id']} | #{r['expected_found_id']} | "
                f"#{r['rank'] or 'Miss'} | {r['top1_score']:.1f}/100 | {r['runner_up_score']:.1f}/100 | "
                f"{'PASS' if r['top1_hit'] else 'FAIL'} | {'PASS' if r['top3_hit'] else 'FAIL'} |"
            )

        return {
            "total": total,
            "top1_accuracy": top1_acc,
            "top3_accuracy": top3_acc,
            "rows": rows,
        }
    finally:
        if eval_db.exists():
            eval_db.unlink()


if __name__ == "__main__":
    run_evaluation()
