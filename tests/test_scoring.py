"""Pytest unit tests for CampusLost+ heuristic Match score (backend/scoring.py)."""

from backend.scoring import score_report_pair, rank_matches_for_report


def test_category_hard_gate_blocks_different_categories() -> None:
    """Hard gate: different categories must return Match score = 0.0 and gated_out = True."""
    lost_bottle = {
        "id": 1,
        "report_type": "lost",
        "category": "bottle",
        "colours": ["black"],
        "brand": "Milton",
        "marks": ["dent near cap"],
        "zone": "LHC",
        "event_time": "2026-10-10T09:00:00+00:00",
        "description": "Black Milton bottle lost in LHC",
        "summary": "Black Milton Bottle",
    }
    found_bag = {
        "id": 2,
        "report_type": "found",
        "category": "bag",
        "colours": ["black"],
        "brand": "Milton",
        "marks": ["dent near cap"],
        "zone": "LHC",
        "event_time": "2026-10-10T09:30:00+00:00",
        "description": "Black bag found in LHC",
        "summary": "Black Bag",
    }
    result = score_report_pair(lost_bottle, found_bag)
    assert result["gated_out"] is True
    assert result["match_score"] == 0.0
    assert set(result["components"].keys()) == {
        "attributes",
        "location",
        "time",
        "text",
        "visual",
    }


def test_same_zone_beats_adjacent_and_far_zone() -> None:
    """Location weight (20): same zone (1.0) > adjacent zone (0.6) > far zone (0.2)."""
    base_lost = {
        "id": 10,
        "report_type": "lost",
        "category": "calculator",
        "colours": ["blue"],
        "brand": "Casio",
        "marks": ["fx-991cw"],
        "zone": "Library",
        "event_time": "2026-10-10T10:00:00+00:00",
        "description": "Blue Casio fx-991cw calculator",
        "summary": "Blue Casio Calculator",
    }
    found_same = {**base_lost, "id": 11, "report_type": "found", "zone": "Library"}
    found_adjacent = {**base_lost, "id": 12, "report_type": "found", "zone": "LHC"}
    found_far = {**base_lost, "id": 13, "report_type": "found", "zone": "Sports ground"}

    s_same = score_report_pair(base_lost, found_same)
    s_adj = score_report_pair(base_lost, found_adjacent)
    s_far = score_report_pair(base_lost, found_far)

    assert s_same["components"]["location"]["raw_ratio"] == 1.0
    assert s_adj["components"]["location"]["raw_ratio"] == 0.6
    assert s_far["components"]["location"]["raw_ratio"] == 0.2
    assert s_same["match_score"] > s_adj["match_score"] > s_far["match_score"]


def test_missing_photo_does_not_crash_and_normalises_weights() -> None:
    """When one or both reports have no photo, visual weight (20) is omitted and the remaining 80 points normalise to 100."""
    lost_no_photo = {
        "id": 20,
        "report_type": "lost",
        "category": "bottle",
        "colours": ["black", "silver"],
        "brand": "Milton",
        "marks": ["dent", "sticker"],
        "zone": "LHC",
        "event_time": "2026-10-10T08:00:00+00:00",
        "description": "Mera black Milton bottle LHC ke bahar chhoot gaya with dent and sticker",
        "summary": "Black Silver Milton Bottle",
        "photo_filename": None,
    }
    found_no_photo = {
        "id": 21,
        "report_type": "found",
        "category": "bottle",
        "colours": ["black", "silver"],
        "brand": "Milton",
        "marks": ["dent", "sticker"],
        "zone": "LHC",
        "event_time": "2026-10-10T09:00:00+00:00",
        "description": "Found black silver Milton bottle outside LHC with dent and sticker",
        "summary": "Black Silver Milton Bottle",
        "photo_filename": "non_existent_file.jpg",
    }

    res = score_report_pair(lost_no_photo, found_no_photo)
    assert res["photos_compared"] is False
    assert res["components"]["visual"]["effective_weight"] == 0.0
    # Remaining effective weights (37.5 + 25.0 + 18.75 + 18.75) sum to 100.0
    eff_sum = sum(c["effective_weight"] for c in res["components"].values())
    assert abs(eff_sum - 100.0) < 0.05
    assert res["match_score"] > 85.0


def test_ranking_returns_top_3_and_separates_decoys() -> None:
    """True match should outrank near-identical decoy bags in different zones/brands."""
    lost_bag = {
        "id": 100,
        "report_type": "lost",
        "category": "bag",
        "colours": ["black"],
        "brand": "Wildcraft",
        "marks": ["red ribbon", "usb port"],
        "zone": "Lab 2",
        "event_time": "2026-10-10T10:00:00+00:00",
        "description": "Black Wildcraft backpack with red ribbon on zipper and usb port lost in Lab 2",
        "summary": "Black Wildcraft Bag",
    }
    candidates = [
        {
            "id": 101,
            "report_type": "found",
            "category": "bag",
            "colours": ["black"],
            "brand": "Skybags",
            "marks": ["broken buckle"],
            "zone": "Sports ground",
            "event_time": "2026-10-10T14:00:00+00:00",
            "description": "Black Skybags backpack found at Sports ground",
            "summary": "Black Skybags Bag",
        },
        {
            "id": 102,
            "report_type": "found",
            "category": "bag",
            "colours": ["black"],
            "brand": "Wildcraft",
            "marks": ["red ribbon", "usb port"],
            "zone": "Lab 2",
            "event_time": "2026-10-10T11:00:00+00:00",
            "description": "Found black Wildcraft laptop bag in Lab 2 with red ribbon and usb port",
            "summary": "Black Wildcraft Bag",
        },
        {
            "id": 103,
            "report_type": "found",
            "category": "bag",
            "colours": ["black"],
            "brand": "American Tourister",
            "marks": ["anime badge"],
            "zone": "Hostel",
            "event_time": "2026-10-10T16:00:00+00:00",
            "description": "Black American Tourister backpack found near Hostel",
            "summary": "Black American Tourister Bag",
        },
    ]

    ranked = rank_matches_for_report(lost_bag, candidates, top_k=3)
    assert len(ranked) == 3
    assert ranked[0][0]["id"] == 102
    assert ranked[0][1]["match_score"] > ranked[1][1]["match_score"]
