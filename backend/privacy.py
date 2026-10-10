"""Privacy & safety helpers for CampusLost+.

Responsibilities:
1. Redact 10-digit phone numbers, 8-12 digit roll numbers, and email addresses
   from all stored and displayed text.
2. Re-encode uploaded photos with Pillow to strip all EXIF/GPS metadata and
   resize the longest edge to at most 1024px.
3. Enforce sensitive-item rules for ID cards and wallets (hide public photo,
   require staffed handover only).
"""

import io
import re
import uuid
from pathlib import Path
from typing import Tuple
from PIL import Image


# 1. Email pattern
EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# 2. Explicit roll-number context followed by 8-12 digits
EXPLICIT_ROLL_RE = re.compile(
    r"(?i)(\b(?:roll(?:\s*(?:no|number|#))?|id\s*no|reg(?:istration)?\s*no)\s*[:\-]?\s*)(\d{8,12})\b"
)

# 3. 10-digit Indian phone numbers (with optional +91 / 0 prefix and optional space/dash)
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+91[\s\-]?|91[\s\-]|0)?([6-9]\d{4}[\s\-]?\d{5})(?!\d)"
)

# 4. Any remaining 8-12 digit number (e.g., 8-12 digit institute roll numbers like 12140890 or 2023104512)
ROLL_RE = re.compile(
    r"(?<!\d)\d{8,12}(?!\d)"
)


def redact_pii(text: str) -> str:
    """Redact emails, 10-digit phone numbers, and 8-12 digit roll numbers from text."""
    if not text:
        return ""

    # Step 1: Redact emails first so numeric parts in emails aren't partially matched
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", text)

    # Step 2: Redact numbers explicitly labelled as roll numbers (8-12 digits)
    redacted = EXPLICIT_ROLL_RE.sub(r"\1[REDACTED_ROLL]", redacted)

    # Step 3: Redact 10-digit Indian mobile numbers
    redacted = PHONE_RE.sub("[REDACTED_PHONE]", redacted)

    # Step 4: Redact any remaining 8-12 digit numeric sequences (roll numbers / IDs)
    redacted = ROLL_RE.sub("[REDACTED_ROLL]", redacted)

    return redacted


def strip_exif_and_resize_bytes(
    image_bytes: bytes, max_dim: int = 1024
) -> Tuple[bytes, Tuple[int, int]]:
    """Re-encode an image to strip all EXIF metadata and resize to max_dim (1024px).

    Returns (clean_jpeg_bytes, (width, height)).
    """
    with Image.open(io.BytesIO(image_bytes)) as src:
        rgb = src.convert("RGB")
        width, height = rgb.size

        if max(width, height) > max_dim:
            scale = max_dim / float(max(width, height))
            new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
            rgb = rgb.resize(new_size, Image.Resampling.LANCZOS)

        # Copy pixel data into a fresh Image object so zero EXIF/ICC/GPS tags remain
        clean_img = Image.new("RGB", rgb.size)
        clean_img.paste(rgb)

        out = io.BytesIO()
        clean_img.save(out, format="JPEG", quality=88, optimize=True)
        return out.getvalue(), clean_img.size


def sanitize_and_save_image(
    image_bytes: bytes, upload_dir: Path, prefix: str = "report"
) -> str:
    """Strip EXIF, resize to <=1024px, save to upload_dir, and return relative filename."""
    upload_dir.mkdir(parents=True, exist_ok=True)
    clean_bytes, _ = strip_exif_and_resize_bytes(image_bytes, max_dim=1024)
    filename = f"{prefix}_{uuid.uuid4().hex[:12]}.jpg"
    target = upload_dir / filename
    target.write_bytes(clean_bytes)
    return filename


def is_sensitive_item(category: str, gemma_sensitive: bool = False, text: str = "") -> bool:
    """ID cards and wallets are always flagged sensitive to hide public photos and require staffed handover."""
    cat = (category or "").strip().lower()
    if cat in {"id_card", "wallet"} or gemma_sensitive:
        return True
    lower = (text or "").lower()
    sensitive_keywords = [
        "id card",
        "identity card",
        "student card",
        "wallet",
        "aadhar",
        "aadhaar",
        "pan card",
        "debit card",
        "credit card",
        "atm card",
    ]
    return any(kw in lower for kw in sensitive_keywords)


def enforce_staffed_handover(
    drop_off_point: str, sensitive: bool, staffed_default: str
) -> str:
    """Sensitive items (ID cards, wallets) must use staffed handover only."""
    if not sensitive:
        return drop_off_point.strip() if drop_off_point and drop_off_point.strip() else staffed_default
    if not drop_off_point or not drop_off_point.strip():
        return staffed_default
    if "staffed" in drop_off_point.lower() or "security" in drop_off_point.lower() or "dosa" in drop_off_point.lower():
        return f"{drop_off_point.strip()} (Staffed Handover Only — Bring Institute ID)"
    return staffed_default
