"""Pytest tests for privacy redaction, EXIF stripping, Gemma wrapper resilience, and 3-attempt claim flow."""

import io
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image

from backend.gemma_client import (
    call_gemma_validated,
    strip_code_fences,
    fallback_extract_features,
)
from backend.main import app
from backend.privacy import redact_pii, strip_exif_and_resize_bytes
from backend.schemas import ExtractedFeatures


def test_redact_phone_roll_and_email() -> None:
    """10-digit phones, 8-12 digit roll numbers, and emails must be redacted."""
    raw = (
        "Lost my IIT Bhilai ID card! Name: Aarav, Roll No: 12140892, "
        "alt roll 2023104512, call me at 9876543210 or +91 91234-56789 "
        "or email aarav.sharma@iitbhilai.ac.in."
    )
    cleaned = redact_pii(raw)
    assert "9876543210" not in cleaned
    assert "91234-56789" not in cleaned
    assert "12140892" not in cleaned
    assert "2023104512" not in cleaned
    assert "aarav.sharma@iitbhilai.ac.in" not in cleaned
    assert "[REDACTED_PHONE]" in cleaned
    assert "[REDACTED_ROLL]" in cleaned
    assert "[REDACTED_EMAIL]" in cleaned


def test_strip_exif_and_resize_to_1024px() -> None:
    """Uploaded images >1024px must be resized to max 1024px and have EXIF stripped."""
    src = Image.new("RGB", (1600, 1200), color=(40, 100, 200))
    exif = src.getexif()
    exif[0x010F] = "CameraMakerSecret"  # Make tag
    buf = io.BytesIO()
    src.save(buf, format="JPEG", exif=exif.tobytes())

    clean_bytes, new_size = strip_exif_and_resize_bytes(buf.getvalue(), max_dim=1024)
    assert new_size == (1024, 768)

    with Image.open(io.BytesIO(clean_bytes)) as reloaded:
        assert max(reloaded.size) <= 1024
        assert len(reloaded.getexif()) == 0


def test_gemma_fence_stripping_and_safe_fallback() -> None:
    """Fence stripping + Pydantic validation + safe fallback when model errors."""
    fenced = '```json\n{"category": "bottle", "colours": ["black"], "brand": "Milton", "marks": ["dent"], "summary": "Black Milton bottle", "sensitive": false}\n```'
    stripped = strip_code_fences(fenced)
    parsed = ExtractedFeatures.model_validate_json(stripped)
    assert parsed.category == "bottle"
    assert parsed.colours == ["black"]

    # Force a fallback by passing an empty/unconfigured prompt call
    res = call_gemma_validated(
        prompt="test",
        schema_cls=ExtractedFeatures,
        fallback_fn=lambda: fallback_extract_features(
            "Mera black Milton bottle LHC ke bahar chhoot gaya", report_type="lost"
        ),
    )
    assert res.category == "bottle"
    assert "black" in res.colours
    assert res.brand == "Milton"


def test_api_privacy_and_three_attempt_claim_flow(tmp_path: Path, monkeypatch) -> None:
    """End-to-end API test:
    - Public endpoints never return verify_answer, drop_off_point, or sensitive photo_url.
    - Claim verification allows max 3 attempts and reveals handover point only on success.
    """
    db_file = tmp_path / "test_campus.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    from backend.db import init_db

    init_db(db_file)
    client = TestClient(app)

    # 1. Create a sensitive FOUND report (ID card) with PII in text and a photo
    img_buf = io.BytesIO()
    Image.new("RGB", (400, 300), color=(200, 50, 50)).save(img_buf, format="JPEG")
    img_buf.seek(0)

    resp = client.post(
        "/api/reports",
        data={
            "report_type": "found",
            "description": "Found IIT Bhilai student ID card roll 12140555 near Mess, call 9988776655",
            "zone": "Mess",
            "drop_off_point": "Mess Warden Desk",
            "custom_verify_question": "What hostel block sticker is on the back of the ID card?",
            "custom_verify_answer": "Kanhar Hostel B-Block",
        },
        files={"photo": ("idcard.jpg", img_buf.getvalue(), "image/jpeg")},
    )
    assert resp.status_code == 200
    found_data = resp.json()

    # Verify PII redaction and sensitive flags on public payload
    assert "12140555" not in found_data["description"]
    assert "9988776655" not in found_data["description"]
    assert found_data["sensitive"] is True
    assert found_data["photo_hidden"] is True
    assert found_data["photo_url"] is None
    assert "verify_answer" not in found_data
    assert "drop_off_point" not in found_data

    found_id = found_data["id"]

    # 2. Failed attempt 1
    v1 = client.post(
        f"/api/claims/{found_id}/verify",
        json={"answer": "Completely wrong guess"},
    )
    assert v1.status_code == 200
    d1 = v1.json()
    assert d1["verified"] is False
    assert d1["attempts_used"] == 1
    assert d1["attempts_remaining"] == 2
    assert d1["handover_point"] is None

    # 3. Successful attempt 2 (exact normalised match)
    v2 = client.post(
        f"/api/claims/{found_id}/verify",
        json={"answer": "kanhar hostel b block"},
    )
    assert v2.status_code == 200
    d2 = v2.json()
    assert d2["verified"] is True
    assert d2["method"] == "exact_normalised"
    assert d2["handover_point"] is not None
    assert "Staffed" in d2["handover_point"]
    assert d2["status_stage"] == "Verified"

    # 4. Advance status tracker to "Handover scheduled" and "Done"
    claim_id = d2["claim_id"]
    st = client.patch(
        f"/api/claims/{claim_id}/status",
        json={"stage": "Handover scheduled"},
    )
    assert st.status_code == 200
    assert st.json()["status_stage"] == "Handover scheduled"
