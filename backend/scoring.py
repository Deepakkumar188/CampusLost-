"""Heuristic Smart Match Score implementation for CampusLost+.

IMPORTANT DESIGN RULE:
Gemma 4 NEVER produces the final match score. This module (`scoring.py`) computes
the deterministic heuristic "Match score" (0 to 100) and returns the full
component breakdown for the UI's "How was this scored?" panel.

Scoring Specification:
- Hard gate: different category -> Match score = 0.0.
- Base weights (sum = 100):
    * attributes : 30 (colour overlap, brand match, distinguishing marks)
    * location   : 20 (same zone = 1.0, adjacent = 0.6, else = 0.2 from config/zones.json)
    * time       : 15 (found on/after lost, decays over 7 days)
    * text       : 15 (bilingual English/Hinglish token similarity)
    * visual     : 20 (only when both reports have photos; otherwise normalise
                       over the remaining 80 points)
"""

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ZONES_CONFIG_PATH = PROJECT_ROOT / "config" / "zones.json"
UPLOADS_DIR = PROJECT_ROOT / "uploads"

BASE_WEIGHTS: Dict[str, float] = {
    "attributes": 30.0,
    "location": 20.0,
    "time": 15.0,
    "text": 15.0,
    "visual": 20.0,
}

HINGLISH_SYNONYMS: Dict[str, str] = {
    "kala": "black",
    "kaala": "black",
    "neela": "blue",
    "laal": "red",
    "safed": "white",
    "hara": "green",
    "peela": "yellow",
    "bhura": "brown",
    "chandi": "silver",
    "botal": "bottle",
    "paani": "water",
    "jhola": "bag",
    "basta": "bag",
    "chabi": "keys",
    "chaabi": "keys",
    "chashma": "glasses",
    "kitaab": "book",
    "batua": "wallet",
    "chhata": "umbrella",
    "pichka": "dent",
    "tuta": "broken",
    "peeche": "back",
    "andar": "inside",
    "bahar": "outside",
}

STOP_WORDS: Set[str] = {
    "a", "an", "the", "in", "on", "at", "near", "by", "from", "to", "with",
    "and", "or", "of", "for", "is", "was", "my", "i", "lost", "found",
    "mera", "meri", "mere", "ke", "ka", "ki", "me", "mein", "pe", "par",
    "gaya", "gayi", "chhoot", "kho", "mila", "mili", "hai", "tha", "thi",
    "report", "item", "campus", "iit", "bhilai",
}


def load_zones_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load campus zones and adjacency map from config/zones.json."""
    target = config_path or ZONES_CONFIG_PATH
    with open(target, "r", encoding="utf-8") as f:
        return json.load(f)


def _tokenise(text: str) -> Set[str]:
    """Normalise English/Hinglish text into a set of meaningful lowercase tokens."""
    raw_tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    out: Set[str] = set()
    for tok in raw_tokens:
        mapped = HINGLISH_SYNONYMS.get(tok, tok)
        if len(mapped) > 1 and mapped not in STOP_WORDS:
            out.add(mapped)
    return out


def compute_location_similarity(
    lost_zone: str,
    found_zone: str,
    zones_config: Optional[Dict[str, Any]] = None,
) -> Tuple[float, str, str]:
    """Return (ratio, detail_string, chip_label) using config/zones.json adjacency.

    Same zone -> 1.0, Adjacent zone -> 0.6, Else -> 0.2.
    """
    cfg = zones_config or load_zones_config()
    adjacency: Dict[str, List[str]] = cfg.get("adjacency", {})

    lz = (lost_zone or "").strip()
    fz = (found_zone or "").strip()

    if not lz or not fz:
        return 0.2, "Zone missing on one report (0.2)", "Zone unknown"

    if lz.lower() == fz.lower():
        return 1.0, f"Same zone: {fz} (1.0)", f"Same zone ({fz})"

    # Case-insensitive lookup in adjacency map
    adj_list: List[str] = []
    for k, neighbours in adjacency.items():
        if k.lower() == lz.lower():
            adj_list = [n.lower() for n in neighbours]
            break

    if fz.lower() in adj_list:
        return 0.6, f"Adjacent zones: {lz} ↔ {fz} (0.6)", f"Adjacent ({lz} ↔ {fz})"

    return 0.2, f"Distant zones: {lz} vs {fz} (0.2)", f"Far zone ({fz})"


def _parse_iso_dt(value: str) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def compute_time_similarity(lost_time_str: str, found_time_str: str) -> Tuple[float, str, str]:
    """Compute time score: found on/after lost, decaying linearly over 7 days (168 hours)."""
    lost_dt = _parse_iso_dt(lost_time_str)
    found_dt = _parse_iso_dt(found_time_str)

    if not lost_dt or not found_dt:
        return 0.5, "Timestamp missing or unparseable (neutral 0.5)", "Time unknown"

    delta_hours = (found_dt - lost_dt).total_seconds() / 3600.0

    if delta_hours < -2.0:
        return (
            0.0,
            f"Found {abs(delta_hours):.1f}h before reported lost time (0.0)",
            "Found before lost",
        )

    if -2.0 <= delta_hours < 0:
        return (
            0.5,
            f"Found within {abs(delta_hours):.1f}h clock tolerance of lost time (0.5)",
            "~Same time",
        )

    # Found on or after lost: linear decay over 7 days (168 hours)
    seven_days_hours = 7.0 * 24.0
    if delta_hours >= seven_days_hours:
        return (
            0.05,
            f"Found {delta_hours / 24.0:.1f} days after lost (>7 days decay)",
            f"+{int(round(delta_hours / 24.0))}d later",
        )

    ratio = max(0.05, 1.0 - (delta_hours / seven_days_hours))
    if delta_hours <= 3.0:
        chip = f"+{max(1, int(round(delta_hours * 60)))}m after lost" if delta_hours < 1 else f"+{delta_hours:.1f}h after lost"
    elif delta_hours < 24.0:
        chip = f"+{delta_hours:.1f}h after lost"
    else:
        chip = f"+{delta_hours / 24.0:.1f}d after lost"

    return (
        round(ratio, 4),
        f"Found {delta_hours:.1f}h after lost (7-day decay -> {ratio:.2f})",
        chip,
    )


def compute_attribute_similarity(
    lost: Dict[str, Any], found: Dict[str, Any]
) -> Tuple[float, str, str]:
    """Compare colours, brand, and distinguishing marks (weight 30)."""
    lost_colours = {c.lower().strip() for c in (lost.get("colours") or []) if c}
    found_colours = {c.lower().strip() for c in (found.get("colours") or []) if c}

    # 1. Colour score (weight 0.50 of attributes)
    if lost_colours and found_colours:
        overlap = lost_colours & found_colours
        union = lost_colours | found_colours
        colour_ratio = len(overlap) / float(len(union))
        colour_chip = (
            f"Colour: {', '.join(sorted(overlap)).title()}"
            if overlap
            else "Colour mismatch"
        )
    elif lost_colours or found_colours:
        colour_ratio = 0.4
        known = sorted(lost_colours or found_colours)
        colour_chip = f"Colour: {', '.join(known).title()} (1-sided)"
    else:
        colour_ratio = 0.5
        colour_chip = "Colour: Unspecified"

    # 2. Brand score (weight 0.25 of attributes)
    lost_brand = (lost.get("brand") or "").strip().lower()
    found_brand = (found.get("brand") or "").strip().lower()
    lost_all_text = f"{lost.get('description', '')} {lost.get('summary', '')} {' '.join(lost.get('marks') or [])}".lower()
    found_all_text = f"{found.get('description', '')} {found.get('summary', '')} {' '.join(found.get('marks') or [])}".lower()

    if lost_brand and found_brand:
        if lost_brand == found_brand or lost_brand in found_brand or found_brand in lost_brand:
            brand_ratio = 1.0
            brand_note = f"brand match ({found.get('brand')})"
        else:
            brand_ratio = 0.0
            brand_note = f"brand conflict ({lost.get('brand')} vs {found.get('brand')})"
    elif lost_brand and lost_brand in found_all_text:
        brand_ratio = 1.0
        brand_note = f"brand '{lost_brand}' in found text"
    elif found_brand and found_brand in lost_all_text:
        brand_ratio = 1.0
        brand_note = f"brand '{found_brand}' in lost text"
    elif lost_brand or found_brand:
        brand_ratio = 0.35
        brand_note = "brand only on one report"
    else:
        brand_ratio = 0.5
        brand_note = "no brand specified"

    # 3. Marks score (weight 0.25 of attributes)
    lost_mark_tokens = _tokenise(" ".join(lost.get("marks") or []))
    found_mark_tokens = _tokenise(" ".join(found.get("marks") or []))
    if lost_mark_tokens and found_mark_tokens:
        shared_marks = lost_mark_tokens & found_mark_tokens
        if shared_marks:
            marks_ratio = min(1.0, len(shared_marks) / float(min(len(lost_mark_tokens), len(found_mark_tokens))))
            marks_note = f"shared marks ({', '.join(sorted(shared_marks))})"
        else:
            # Also check if mark tokens appear in the opposite report's description
            cross_hits = (lost_mark_tokens & _tokenise(found_all_text)) | (
                found_mark_tokens & _tokenise(lost_all_text)
            )
            if cross_hits:
                marks_ratio = 0.75
                marks_note = f"marks in description ({', '.join(sorted(cross_hits))})"
            else:
                marks_ratio = 0.0
                marks_note = "different marks"
    elif lost_mark_tokens or found_mark_tokens:
        active_marks = lost_mark_tokens or found_mark_tokens
        cross_hits = active_marks & _tokenise(found_all_text if lost_mark_tokens else lost_all_text)
        marks_ratio = 0.8 if cross_hits else 0.35
        marks_note = "mark mentioned in description" if cross_hits else "marks on one side only"
    else:
        marks_ratio = 0.5
        marks_note = "no specific marks"

    combined = (0.50 * colour_ratio) + (0.25 * brand_ratio) + (0.25 * marks_ratio)
    detail = f"Colour={colour_ratio:.2f}, {brand_note}, {marks_note}"
    return round(combined, 4), detail, colour_chip


def compute_text_similarity(lost: Dict[str, Any], found: Dict[str, Any]) -> Tuple[float, str]:
    """Compute token Jaccard + containment similarity across bilingual descriptions and summaries."""
    lost_text = f"{lost.get('summary', '')} {lost.get('description', '')} {lost.get('brand', '')} {' '.join(lost.get('marks') or [])}"
    found_text = f"{found.get('summary', '')} {found.get('description', '')} {found.get('brand', '')} {' '.join(found.get('marks') or [])}"

    t1 = _tokenise(lost_text)
    t2 = _tokenise(found_text)

    if not t1 or not t2:
        return 0.0, "Insufficient text tokens (0.0)"

    intersection = t1 & t2
    union = t1 | t2
    jaccard = len(intersection) / float(len(union))
    containment = len(intersection) / float(min(len(t1), len(t2)))
    ratio = (0.5 * jaccard) + (0.5 * containment)
    shared_preview = ", ".join(sorted(list(intersection))[:5]) or "none"
    return round(min(1.0, ratio), 4), f"Shared tokens: {shared_preview} ({ratio:.2f})"


def _resolve_photo_path(report: Dict[str, Any]) -> Optional[Path]:
    """Locate a report's image file on disk if present."""
    for key in ("photo_path", "photo_filename"):
        val = report.get(key)
        if not val or not isinstance(val, str):
            continue
        p = Path(val)
        if p.is_file():
            return p
        candidate = UPLOADS_DIR / p.name
        if candidate.is_file():
            return candidate
    return None


def compute_visual_similarity(
    lost: Dict[str, Any], found: Dict[str, Any]
) -> Tuple[Optional[float], str]:
    """Compute deterministic image similarity using Pillow (dHash + RGB histogram cosine).

    Returns (None, reason) if either report does not have a photo so the caller
    normalises the score across the remaining 4 weights.
    """
    # Allow explicit numeric override for unit tests
    if "visual_similarity" in lost and "visual_similarity" in found:
        override = lost.get("visual_similarity")
        if isinstance(override, (int, float)):
            val = max(0.0, min(1.0, float(override)))
            return val, f"Precomputed visual similarity ({val:.2f})"

    p1 = _resolve_photo_path(lost)
    p2 = _resolve_photo_path(found)

    if p1 is None or p2 is None:
        return None, "Photo missing on one or both reports — weight normalised across other signals"

    try:
        with Image.open(p1) as img1, Image.open(p2) as img2:
            # 1. 64-bit difference hash (dHash) on 9x8 grayscale
            g1 = img1.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            g2 = img2.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            px1 = list(g1.getdata())
            px2 = list(g2.getdata())

            bits1: List[int] = []
            bits2: List[int] = []
            for row in range(8):
                offset = row * 9
                for col in range(8):
                    bits1.append(1 if px1[offset + col] > px1[offset + col + 1] else 0)
                    bits2.append(1 if px2[offset + col] > px2[offset + col + 1] else 0)

            hamming_same = sum(1 for a, b in zip(bits1, bits2) if a == b)
            dhash_sim = hamming_same / 64.0

            # 2. Normalised RGB histogram cosine similarity (48 bins)
            r1 = img1.convert("RGB").resize((64, 64), Image.Resampling.LANCZOS)
            r2 = img2.convert("RGB").resize((64, 64), Image.Resampling.LANCZOS)
            h1 = r1.histogram()
            h2 = r2.histogram()
            # Down-bin 768 values into 48 bins of 16
            b1 = [sum(h1[i : i + 16]) for i in range(0, 768, 16)]
            b2 = [sum(h2[i : i + 16]) for i in range(0, 768, 16)]
            dot = sum(a * b for a, b in zip(b1, b2))
            norm1 = math.sqrt(sum(a * a for a in b1)) or 1.0
            norm2 = math.sqrt(sum(b * b for b in b2)) or 1.0
            hist_sim = dot / (norm1 * norm2)

            combined = (0.55 * hist_sim) + (0.45 * dhash_sim)
            return round(max(0.0, min(1.0, combined)), 4), f"RGB histogram ({hist_sim:.2f}) + dHash ({dhash_sim:.2f})"
    except Exception:
        return None, "Image comparison skipped — weight normalised across other signals"


def score_report_pair(
    lost_report: Dict[str, Any],
    found_report: Dict[str, Any],
    zones_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute the heuristic Match score (0 to 100) between a lost report and a found report.

    Always returns:
      - `match_score`: float (0.0 to 100.0)
      - `gated_out`: bool
      - `photos_compared`: bool
      - `chips`: {"Colour": ..., "Zone": ..., "Time": ...}
      - `components`: per-signal breakdown dictionary
    """
    lost_cat = (lost_report.get("category") or "other").strip().lower()
    found_cat = (found_report.get("category") or "other").strip().lower()

    # HARD GATE: different category means 0 match score immediately
    if lost_cat != found_cat:
        zero_components = {
            k: {
                "raw_ratio": 0.0,
                "base_weight": w,
                "effective_weight": w,
                "points": 0.0,
                "detail": f"Hard gate: category mismatch ({lost_cat} != {found_cat})",
            }
            for k, w in BASE_WEIGHTS.items()
        }
        return {
            "match_score": 0.0,
            "gated_out": True,
            "photos_compared": False,
            "chips": {
                "Colour": "Category mismatch",
                "Zone": f"{lost_report.get('zone', '?')} vs {found_report.get('zone', '?')}",
                "Time": "Gated out",
            },
            "components": zero_components,
        }

    # Compute raw 0..1 ratios for each component
    attr_ratio, attr_detail, colour_chip = compute_attribute_similarity(
        lost_report, found_report
    )
    loc_ratio, loc_detail, zone_chip = compute_location_similarity(
        lost_report.get("zone", ""),
        found_report.get("zone", ""),
        zones_config=zones_config,
    )
    time_ratio, time_detail, time_chip = compute_time_similarity(
        lost_report.get("event_time", ""),
        found_report.get("event_time", ""),
    )
    text_ratio, text_detail = compute_text_similarity(lost_report, found_report)
    vis_ratio, vis_detail = compute_visual_similarity(lost_report, found_report)

    photos_compared = vis_ratio is not None
    if photos_compared:
        active_total_weight = 100.0
    else:
        # Normalise over the 4 non-visual weights (30 + 20 + 15 + 15 = 80)
        active_total_weight = (
            BASE_WEIGHTS["attributes"]
            + BASE_WEIGHTS["location"]
            + BASE_WEIGHTS["time"]
            + BASE_WEIGHTS["text"]
        )

    scale = 100.0 / active_total_weight

    raw_map: Dict[str, Tuple[float, str, bool]] = {
        "attributes": (attr_ratio, attr_detail, True),
        "location": (loc_ratio, loc_detail, True),
        "time": (time_ratio, time_detail, True),
        "text": (text_ratio, text_detail, True),
        "visual": (vis_ratio if vis_ratio is not None else 0.0, vis_detail, photos_compared),
    }

    components: Dict[str, Dict[str, Any]] = {}
    total_score = 0.0

    for name, (ratio, detail, is_active) in raw_map.items():
        base_w = BASE_WEIGHTS[name]
        eff_w = round(base_w * scale, 2) if is_active else 0.0
        pts = round(ratio * eff_w, 2) if is_active else 0.0
        total_score += pts
        components[name] = {
            "raw_ratio": round(ratio, 4),
            "base_weight": base_w,
            "effective_weight": eff_w,
            "points": pts,
            "detail": detail,
        }

    return {
        "match_score": round(min(100.0, max(0.0, total_score)), 1),
        "gated_out": False,
        "photos_compared": photos_compared,
        "chips": {
            "Colour": colour_chip,
            "Zone": zone_chip,
            "Time": time_chip,
        },
        "components": components,
    }


def rank_matches_for_report(
    source_report: Dict[str, Any],
    candidate_reports: List[Dict[str, Any]],
    top_k: int = 3,
    zones_config: Optional[Dict[str, Any]] = None,
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Score `source_report` against all open opposite-type `candidate_reports` and return top_k."""
    cfg = zones_config or load_zones_config()
    scored_pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []

    for cand in candidate_reports:
        if cand.get("id") == source_report.get("id"):
            continue
        if cand.get("report_type") == source_report.get("report_type"):
            continue

        if source_report.get("report_type") == "lost":
            lost_r, found_r = source_report, cand
        else:
            lost_r, found_r = cand, source_report

        score_data = score_report_pair(lost_r, found_r, zones_config=cfg)
        if not score_data["gated_out"] and score_data["match_score"] > 0:
            scored_pairs.append((cand, score_data))

    scored_pairs.sort(key=lambda item: item[1]["match_score"], reverse=True)
    return scored_pairs[:top_k]
