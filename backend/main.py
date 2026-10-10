"""FastAPI application for CampusLost+: Lost on Campus. Found by AI.

Exposes endpoints for:
- Reporting lost & found items (with automatic PII redaction, EXIF stripping, and Gemma 4 feature extraction)
- Ranking top 3 matches using scoring.py + Gemma 4 one-sentence explanations
- Ownership verification (max 3 attempts; exact normalised match first, Gemma fuzzy fallback)
- Handover status tracker (Matched -> Verified -> Handover scheduled -> Done)
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.db import (
    get_claim_by_id,
    get_or_create_claim,
    get_report_by_id,
    init_db,
    insert_report,
    list_reports,
    update_claim_stage,
    update_claim_verification,
)
from backend.gemma_client import (
    explain_match_with_gemma,
    extract_features_with_gemma,
    verify_ownership_answer,
)
from backend.privacy import (
    enforce_staffed_handover,
    is_sensitive_item,
    redact_pii,
    sanitize_and_save_image,
)
from backend.schemas import (
    ComponentDetail,
    MatchResult,
    PublicReport,
    StatusUpdateRequest,
    VerifyAttemptRequest,
    VerifyAttemptResponse,
)
from backend.scoring import load_zones_config, rank_matches_for_report

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UPLOADS_DIR = PROJECT_ROOT / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

MAX_CLAIM_ATTEMPTS = 3
HANDOVER_STAGES = ["Matched", "Verified", "Handover scheduled", "Done"]

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="CampusLost+ API",
    description="Lost on Campus. Found by AI. (IIT Bhilai Hackathon MVP)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_public_report(row: Dict[str, Any]) -> PublicReport:
    """Convert an internal DB report dict into a privacy-safe PublicReport.

    Guarantees:
    - Never includes `verify_answer` or `drop_off_point`.
    - Description & summary are PII-redacted.
    - Sensitive items (`id_card`, `wallet`, `sensitive=True`) never expose `photo_url`.
    """
    sensitive = bool(row.get("sensitive")) or is_sensitive_item(
        row.get("category", ""), False, row.get("description", "")
    )
    has_photo = bool(row.get("photo_filename"))
    photo_hidden = bool(sensitive)
    photo_url = (
        f"/api/photos/{row['photo_filename']}"
        if (has_photo and not photo_hidden)
        else None
    )

    return PublicReport(
        id=row["id"],
        report_type=row["report_type"],
        description=redact_pii(row.get("description", "")),
        zone=row.get("zone", "Library"),
        event_time=row.get("event_time", ""),
        category=row.get("category", "other"),
        colours=row.get("colours", []),
        brand=redact_pii(row.get("brand", "")),
        marks=[redact_pii(m) for m in (row.get("marks") or [])],
        summary=redact_pii(row.get("summary", "")),
        sensitive=sensitive,
        has_photo=has_photo,
        photo_hidden=photo_hidden,
        photo_url=photo_url,
        verify_question=redact_pii(row.get("verify_question") or "")
        if row.get("verify_question")
        else None,
        status=row.get("status", "open"),
        created_at=row.get("created_at", ""),
    )


@app.get("/api/health")
def health_check() -> Dict[str, Any]:
    """Health & configuration check (never exposes API keys)."""
    zones_cfg = load_zones_config()
    model_env = os.getenv("GEMMA_MODEL", "")
    key_env = os.getenv("GEMINI_API_KEY", "")
    gemma_configured = bool(
        key_env and key_env != "your_gemini_api_key_here" and model_env
    )
    return {
        "status": "ok",
        "app": "CampusLost+",
        "gemma_model_configured": gemma_configured,
        "gemma_model": model_env or "unconfigured (using deterministic fallback)",
        "zones": zones_cfg.get("zones", []),
    }


@app.get("/api/zones")
def get_zones() -> Dict[str, Any]:
    """Return campus zones and adjacency graph from config/zones.json."""
    return load_zones_config()


@app.post("/api/reports", response_model=PublicReport)
async def create_report(
    report_type: str = Form(..., description="'lost' or 'found'"),
    description: str = Form("", description="Item description in English, Hindi, or Hinglish"),
    zone: str = Form(..., description="Campus zone from config/zones.json"),
    event_time: Optional[str] = Form(None, description="ISO timestamp when lost/found"),
    drop_off_point: str = Form("", description="For found items: where item is kept"),
    custom_verify_question: Optional[str] = Form(None),
    custom_verify_answer: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
) -> PublicReport:
    """Create a Lost or Found report.

    1. Validates report_type and zone.
    2. Re-encodes uploaded image (strips EXIF, resizes to <=1024px).
    3. Redacts phone numbers, roll numbers, and emails from text.
    4. Extracts structured features + verification question via Gemma 4.
    5. Applies sensitive-item rules for ID cards and wallets.
    """
    rtype = report_type.strip().lower()
    if rtype not in {"lost", "found"}:
        raise HTTPException(status_code=400, detail="report_type must be 'lost' or 'found'")

    zones_cfg = load_zones_config()
    valid_zones = zones_cfg.get("zones", [])
    if zone not in valid_zones:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid zone '{zone}'. Must be one of: {', '.join(valid_zones)}",
        )

    photo_bytes: Optional[bytes] = None
    photo_filename: Optional[str] = None
    if photo and photo.filename:
        raw_bytes = await photo.read()
        if raw_bytes:
            try:
                photo_filename = sanitize_and_save_image(
                    raw_bytes, UPLOADS_DIR, prefix=rtype
                )
                photo_bytes = (UPLOADS_DIR / photo_filename).read_bytes()
            except Exception as exc:
                raise HTTPException(
                    status_code=400, detail=f"Invalid image upload: {exc}"
                ) from exc

    if rtype == "found" and not photo_filename and not description.strip():
        raise HTTPException(
            status_code=400,
            detail="Found reports require a photo or a description.",
        )

    # Redact PII before extraction and storage
    clean_description = redact_pii(description.strip() or f"{rtype.title()} item near {zone}")
    clean_drop_off = redact_pii(drop_off_point.strip())

    extracted = extract_features_with_gemma(
        text=clean_description,
        report_type=rtype,
        image_bytes=photo_bytes,
    )

    sensitive = is_sensitive_item(
        extracted.category, extracted.sensitive, clean_description
    )
    staffed_default = zones_cfg.get(
        "staffed_handover_default",
        "Staffed Security Desk (Main Gate / DOSA Office) — Bring Institute ID",
    )
    final_drop_off = (
        enforce_staffed_handover(clean_drop_off, sensitive, staffed_default)
        if rtype == "found"
        else ""
    )

    verify_q = (
        redact_pii(custom_verify_question.strip())
        if (custom_verify_question and custom_verify_question.strip())
        else extracted.verify_question
    )
    verify_a = (
        custom_verify_answer.strip()
        if (custom_verify_answer and custom_verify_answer.strip())
        else extracted.verify_answer
    )

    iso_time = (
        event_time.strip()
        if (event_time and event_time.strip())
        else datetime.now(timezone.utc).isoformat()
    )

    saved = insert_report(
        report_type=rtype,
        description=clean_description,
        zone=zone,
        event_time=iso_time,
        drop_off_point=final_drop_off,
        category=extracted.category,
        colours=extracted.colours,
        brand=redact_pii(extracted.brand),
        marks=[redact_pii(m) for m in extracted.marks],
        summary=redact_pii(extracted.summary),
        sensitive=sensitive,
        verify_question=verify_q if rtype == "found" else None,
        verify_answer=verify_a if rtype == "found" else None,
        photo_filename=photo_filename,
        status="open",
    )
    return _to_public_report(saved)


@app.get("/api/reports", response_model=List[PublicReport])
def get_reports(
    report_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
) -> List[PublicReport]:
    """List public-safe reports for the Campus Board and report selectors."""
    rows = list_reports(
        report_type=report_type, status=status, zone=zone, category=category
    )
    return [_to_public_report(r) for r in rows]


@app.get("/api/reports/{report_id}", response_model=PublicReport)
def get_single_report(report_id: int) -> PublicReport:
    """Get a single public-safe report by ID."""
    row = get_report_by_id(report_id)
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return _to_public_report(row)


@app.get("/api/reports/{report_id}/matches", response_model=List[MatchResult])
def get_matches_for_report(report_id: int) -> List[MatchResult]:
    """Rank open reports of the opposite type using scoring.py and return top 3 with Gemma explanations."""
    source = get_report_by_id(report_id)
    if not source:
        raise HTTPException(status_code=404, detail="Report not found")

    opposite_type = "found" if source["report_type"] == "lost" else "lost"
    candidates = list_reports(report_type=opposite_type, status="open")
    # Also include claimed candidates if they were claimed by this specific report
    if not candidates:
        candidates = list_reports(report_type=opposite_type)

    zones_cfg = load_zones_config()
    top_ranked = rank_matches_for_report(
        source_report=source,
        candidate_reports=candidates,
        top_k=3,
        zones_config=zones_cfg,
    )

    results: List[MatchResult] = []
    for cand, score_data in top_ranked:
        lost_r = source if source["report_type"] == "lost" else cand
        found_r = cand if source["report_type"] == "lost" else source
        explanation = explain_match_with_gemma(lost_r, found_r, score_data)
        comp_models = {
            k: ComponentDetail(**v) for k, v in score_data["components"].items()
        }
        results.append(
            MatchResult(
                candidate=_to_public_report(cand),
                match_score=score_data["match_score"],
                gated_out=score_data["gated_out"],
                photos_compared=score_data["photos_compared"],
                chips=score_data["chips"],
                components=comp_models,
                explanation=explanation,
            )
        )
    return results


@app.get("/api/photos/{filename}")
def get_sanitized_photo(filename: str) -> FileResponse:
    """Serve sanitised item photo ONLY if the report is not flagged sensitive."""
    safe_name = Path(filename).name
    target = UPLOADS_DIR / safe_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")

    # Never serve photos belonging to sensitive reports (ID cards, wallets)
    all_reports = list_reports()
    for r in all_reports:
        if r.get("photo_filename") == safe_name:
            if r.get("sensitive") or is_sensitive_item(
                r.get("category", ""), False, r.get("description", "")
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Photo is hidden for privacy because this item is flagged sensitive.",
                )
    return FileResponse(str(target), media_type="image/jpeg")


@app.get("/api/claims/{found_report_id}")
def get_claim_info(
    found_report_id: int, lost_report_id: Optional[int] = Query(None)
) -> Dict[str, Any]:
    """Fetch verification question and attempt status for claiming a found item.

    Never reveals `verify_answer` or `handover_point` unless `verified` is already True.
    """
    found = get_report_by_id(found_report_id)
    if not found or found["report_type"] != "found":
        raise HTTPException(status_code=404, detail="Found report not found")

    claim = get_or_create_claim(found_report_id, lost_report_id)
    attempts_used = int(claim["attempts_used"])
    verified = bool(claim["verified"])
    locked = (not verified) and (attempts_used >= MAX_CLAIM_ATTEMPTS)

    zones_cfg = load_zones_config()
    staffed_default = zones_cfg.get(
        "staffed_handover_default",
        "Staffed Security Desk (Main Gate / DOSA Office) — Bring Institute ID",
    )
    sensitive = bool(found.get("sensitive")) or is_sensitive_item(
        found.get("category", ""), False, found.get("description", "")
    )
    handover_point = (
        enforce_staffed_handover(found.get("drop_off_point", ""), sensitive, staffed_default)
        if verified
        else None
    )

    return {
        "claim_id": claim["id"],
        "found_report": _to_public_report(found).model_dump(),
        "verify_question": found.get("verify_question")
        or "Describe one specific identifying mark, brand, or detail on this item.",
        "attempts_used": attempts_used,
        "attempts_remaining": max(0, MAX_CLAIM_ATTEMPTS - attempts_used),
        "verified": verified,
        "locked": locked,
        "status_stage": claim["status_stage"],
        "stages": HANDOVER_STAGES,
        "handover_point": handover_point,
        "staffed_only": sensitive,
    }


@app.post("/api/claims/{found_report_id}/verify", response_model=VerifyAttemptResponse)
def verify_claim(
    found_report_id: int, payload: VerifyAttemptRequest
) -> VerifyAttemptResponse:
    """Verify ownership answer (max 3 attempts).

    1. Checks if claim is already verified or locked (3 failed attempts).
    2. Runs exact normalised check first, then Gemma 4 fuzzy fallback.
    3. On success, reveals handover_point and advances status_stage to 'Verified'.
    """
    found = get_report_by_id(found_report_id)
    if not found or found["report_type"] != "found":
        raise HTTPException(status_code=404, detail="Found report not found")

    claim = get_or_create_claim(found_report_id, payload.lost_report_id)
    attempts_used = int(claim["attempts_used"])
    already_verified = bool(claim["verified"])
    sensitive = bool(found.get("sensitive")) or is_sensitive_item(
        found.get("category", ""), False, found.get("description", "")
    )
    zones_cfg = load_zones_config()
    staffed_default = zones_cfg.get(
        "staffed_handover_default",
        "Staffed Security Desk (Main Gate / DOSA Office) — Bring Institute ID",
    )
    resolved_handover = enforce_staffed_handover(
        found.get("drop_off_point", ""), sensitive, staffed_default
    )

    if already_verified:
        return VerifyAttemptResponse(
            claim_id=claim["id"],
            verified=True,
            method=claim.get("verify_method") or "exact_normalised",
            attempts_used=attempts_used,
            attempts_remaining=max(0, MAX_CLAIM_ATTEMPTS - attempts_used),
            locked=False,
            message="Ownership already verified. Handover details unlocked.",
            handover_point=resolved_handover,
            staffed_only=sensitive,
            status_stage=claim["status_stage"],
        )

    if attempts_used >= MAX_CLAIM_ATTEMPTS:
        return VerifyAttemptResponse(
            claim_id=claim["id"],
            verified=False,
            method="locked",
            attempts_used=attempts_used,
            attempts_remaining=0,
            locked=True,
            message="Maximum verification attempts (3/3) reached. Please visit the Staffed Security Desk with your Institute ID.",
            handover_point=None,
            staffed_only=sensitive,
            status_stage=claim["status_stage"],
        )

    user_answer = (payload.answer or "").strip()
    if not user_answer:
        raise HTTPException(status_code=400, detail="Verification answer cannot be empty")

    expected_answer = (
        found.get("verify_answer")
        or found.get("brand")
        or " ".join(found.get("marks") or [])
        or found.get("summary", "")
    )
    question = (
        found.get("verify_question")
        or "What distinguishing detail identifies this item?"
    )

    matched, method, reason = verify_ownership_answer(
        question=question,
        expected_answer=expected_answer,
        user_answer=user_answer,
    )

    new_attempts = attempts_used + 1
    new_stage = "Verified" if matched else "Matched"
    updated = update_claim_verification(
        claim["id"],
        attempts_used=new_attempts,
        verified=matched,
        verify_method=method if matched else "",
        status_stage=new_stage,
    )

    remaining = max(0, MAX_CLAIM_ATTEMPTS - new_attempts)
    locked = (not matched) and (remaining == 0)

    if matched:
        msg = f"Ownership verified ({method.replace('_', ' ')}). {reason}"
    elif locked:
        msg = "Incorrect answer. All 3 attempts used — claim is now locked for online reveal. Please visit the Staffed Security Desk."
    else:
        msg = f"Answer did not match ({remaining} attempt{'s' if remaining != 1 else ''} left). {reason}"

    return VerifyAttemptResponse(
        claim_id=updated["id"],
        verified=matched,
        method=method,
        attempts_used=new_attempts,
        attempts_remaining=remaining,
        locked=locked,
        message=msg,
        handover_point=resolved_handover if matched else None,
        staffed_only=sensitive,
        status_stage=updated["status_stage"],
    )


@app.patch("/api/claims/{claim_id}/status")
def advance_claim_status(
    claim_id: int, payload: StatusUpdateRequest
) -> Dict[str, Any]:
    """Update the handover status tracker ('Matched' -> 'Verified' -> 'Handover scheduled' -> 'Done')."""
    claim = get_claim_by_id(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if not claim.get("verified") and payload.stage in {"Verified", "Handover scheduled", "Done"}:
        raise HTTPException(
            status_code=403,
            detail="Cannot advance handover status before ownership is verified.",
        )

    updated = update_claim_stage(claim_id, payload.stage)
    return {
        "claim_id": claim_id,
        "status_stage": updated["status_stage"] if updated else payload.stage,
        "stages": HANDOVER_STAGES,
    }


FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIST), html=True),
        name="frontend",
    )

