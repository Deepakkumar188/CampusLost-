"""Seed script for CampusLost+ (IIT Bhilai Hackathon MVP).

Loads 12 curated demo reports into SQLite:
- 6 FOUND reports and 6 LOST reports
- 3 core true matches (including 1 in Hinglish: L1 <-> F1)
- 2 near-identical decoy black backpacks (F3, F4) vs true backpack match (L2 <-> F2)
- 1 dummy IIT Bhilai Student ID card (F6 <-> L4) demonstrating PII redaction,
  blurred public photo placeholder, and staffed-only handover.
"""

import io
from pathlib import Path
from typing import Any, Dict, List
from PIL import Image, ImageDraw

from backend.db import get_connection, init_db, insert_report
from backend.privacy import (
    enforce_staffed_handover,
    is_sensitive_item,
    redact_pii,
    sanitize_and_save_image,
)
from backend.scoring import load_zones_config

PROJECT_ROOT = Path(__file__).resolve().parent
UPLOADS_DIR = PROJECT_ROOT / "uploads"


def _make_demo_image(rgb: tuple[int, int, int], accent: tuple[int, int, int], label: str) -> bytes:
    """Create a synthetic item photo (1200x900) so sanitize_and_save_image resizes to 1024px and strips EXIF."""
    img = Image.new("RGB", (1200, 900), color=rgb)
    draw = ImageDraw.Draw(img)
    draw.rectangle([180, 140, 1020, 760], fill=accent, outline=(255, 255, 255), width=6)
    draw.rectangle([260, 240, 940, 660], fill=rgb, outline=(240, 240, 240), width=4)
    draw.text((320, 430), label, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


SEED_REPORTS: List[Dict[str, Any]] = [
    # ---------------- 6 FOUND REPORTS ----------------
    {
        "key": "F1_BOTTLE_TRUE",
        "report_type": "found",
        "description": (
            "Found a black and silver Milton Thermosteel bottle on the bench outside LHC. "
            "Has a small dent near the cap and an ISRO sticker on the bottom. Finder phone 9876501234."
        ),
        "zone": "LHC",
        "event_time": "2026-10-10T10:30:00+05:30",
        "drop_off_point": "LHC Security Guard Desk (Ground Floor)",
        "category": "bottle",
        "colours": ["black", "silver"],
        "brand": "Milton",
        "marks": ["dent near cap", "ISRO sticker"],
        "summary": "Black Silver Milton Thermosteel Bottle",
        "sensitive": False,
        "verify_question": "What sticker is on the bottom of the bottle and where is the dent?",
        "verify_answer": "ISRO sticker and dent near cap",
        "image_spec": ((28, 32, 38), (160, 170, 185), "Milton Bottle (LHC)"),
    },
    {
        "key": "F2_BAG_TRUE",
        "report_type": "found",
        "description": (
            "Found a black Wildcraft laptop backpack in Lab 2 near row 3. "
            "Has a red ribbon tied to the main zipper and an external USB charging port."
        ),
        "zone": "Lab 2",
        "event_time": "2026-10-10T11:15:00+05:30",
        "drop_off_point": "Lab 2 Technician Cabin (Room 204)",
        "category": "bag",
        "colours": ["black"],
        "brand": "Wildcraft",
        "marks": ["red ribbon", "usb port"],
        "summary": "Black Wildcraft Laptop Backpack",
        "sensitive": False,
        "verify_question": "What colour ribbon is tied to the zipper and what is inside the front pocket?",
        "verify_answer": "red ribbon and sandisk pendrive",
        "image_spec": ((25, 25, 30), (190, 40, 50), "Wildcraft Bag (Lab 2)"),
    },
    {
        "key": "F3_BAG_DECOY_1",
        "report_type": "found",
        "description": (
            "Found a black Skybags backpack near the Sports ground pavilion. "
            "Left side plastic buckle is slightly cracked."
        ),
        "zone": "Sports ground",
        "event_time": "2026-10-08T17:45:00+05:30",
        "drop_off_point": "Sports Complex Store Room",
        "category": "bag",
        "colours": ["black"],
        "brand": "Skybags",
        "marks": ["cracked buckle"],
        "summary": "Black Skybags Backpack (Decoy #1)",
        "sensitive": False,
        "verify_question": "Which side buckle is cracked on this Skybags backpack?",
        "verify_answer": "left side buckle",
        "image_spec": ((35, 35, 45), (70, 90, 120), "Skybags Backpack (Sports)"),
    },
    {
        "key": "F4_BAG_DECOY_2",
        "report_type": "found",
        "description": (
            "Found a black American Tourister college backpack outside Hostel common room. "
            "Has a round anime pin badge on the shoulder strap."
        ),
        "zone": "Hostel",
        "event_time": "2026-10-07T19:00:00+05:30",
        "drop_off_point": "Hostel Caretaker Desk",
        "category": "bag",
        "colours": ["black"],
        "brand": "American Tourister",
        "marks": ["anime pin badge"],
        "summary": "Black American Tourister Backpack (Decoy #2)",
        "sensitive": False,
        "verify_question": "What kind of badge is pinned on the shoulder strap?",
        "verify_answer": "anime pin badge",
        "image_spec": ((40, 38, 48), (110, 80, 140), "American Tourister Bag"),
    },
    {
        "key": "F5_CALC_TRUE",
        "report_type": "found",
        "description": (
            "Found a blue Casio fx-991CW scientific calculator on a study table in Library 2nd floor. "
            "Initials are scratched inside the hard slide cover."
        ),
        "zone": "Library",
        "event_time": "2026-10-10T12:10:00+05:30",
        "drop_off_point": "Library Circulation Counter",
        "category": "calculator",
        "colours": ["blue", "black"],
        "brand": "Casio",
        "marks": ["fx-991cw", "initials RK on slide cover"],
        "summary": "Blue Casio fx-991CW Scientific Calculator",
        "sensitive": False,
        "verify_question": "What two initials are scratched on the inside of the slide cover?",
        "verify_answer": "RK",
        "image_spec": ((30, 75, 155), (80, 140, 220), "Casio fx-991CW (Library)"),
    },
    {
        "key": "F6_IDCARD_SENSITIVE",
        "report_type": "found",
        "description": (
            "Found dummy IIT Bhilai Student ID card near Mess handwash area. "
            "Roll No: 12140892, contact 9876543210, email student.demo@iitbhilai.ac.in. "
            "Has a blue lanyard and Kanhar Hostel hologram sticker on the back."
        ),
        "zone": "Mess",
        "event_time": "2026-10-10T13:30:00+05:30",
        "drop_off_point": "Mess Supervisor Desk",
        "category": "id_card",
        "colours": ["white", "blue"],
        "brand": "IIT Bhilai",
        "marks": ["blue lanyard", "Kanhar Hostel sticker"],
        "summary": "IIT Bhilai Student ID Card (Sensitive)",
        "sensitive": True,
        "verify_question": "Which hostel sticker is on the back of the ID card?",
        "verify_answer": "Kanhar Hostel",
        "image_spec": ((180, 50, 50), (230, 230, 240), "SENSITIVE DUMMY ID CARD"),
    },
    # ---------------- 6 LOST REPORTS ----------------
    {
        "key": "L1_BOTTLE_HINGLISH",
        "report_type": "lost",
        "description": (
            "Mera black silver Milton thermosteel bottle LHC ke bahar bench pe chhoot gaya. "
            "Cap ke paas chhota dent hai aur neeche ISRO sticker laga hai. Call me at 9123456789."
        ),
        "zone": "LHC",
        "event_time": "2026-10-10T09:45:00+05:30",
        "category": "bottle",
        "colours": ["black", "silver"],
        "brand": "Milton",
        "marks": ["dent near cap", "ISRO sticker"],
        "summary": "Black Silver Milton Bottle (Hinglish Report)",
        "sensitive": False,
        "image_spec": ((30, 34, 40), (155, 168, 182), "Lost Milton Bottle"),
    },
    {
        "key": "L2_BAG_TRUE",
        "report_type": "lost",
        "description": (
            "Lost my black Wildcraft laptop backpack in Lab 2 after the morning coding lab. "
            "It has a red ribbon tied to the zipper, USB port, and a SanDisk pendrive inside."
        ),
        "zone": "Lab 2",
        "event_time": "2026-10-10T10:30:00+05:30",
        "category": "bag",
        "colours": ["black"],
        "brand": "Wildcraft",
        "marks": ["red ribbon", "usb port"],
        "summary": "Black Wildcraft Laptop Bag",
        "sensitive": False,
        "image_spec": ((24, 24, 29), (185, 42, 52), "Lost Wildcraft Bag"),
    },
    {
        "key": "L3_CALC_TRUE",
        "report_type": "lost",
        "description": (
            "Lost my blue Casio fx-991CW scientific calculator in Library reading room this morning. "
            "Has my initials RK scratched inside the cover."
        ),
        "zone": "Library",
        "event_time": "2026-10-10T11:30:00+05:30",
        "category": "calculator",
        "colours": ["blue", "black"],
        "brand": "Casio",
        "marks": ["fx-991cw", "initials RK"],
        "summary": "Blue Casio fx-991CW Calculator",
        "sensitive": False,
        "image_spec": None,  # Intentionally no photo on lost report to showcase missing-photo weight normalisation!
    },
    {
        "key": "L4_IDCARD_SENSITIVE",
        "report_type": "lost",
        "description": (
            "Lost my IIT Bhilai student ID card in Mess during lunch. Roll number 12140892, "
            "email student.demo@iitbhilai.ac.in. Blue lanyard and Kanhar Hostel sticker on the back."
        ),
        "zone": "Mess",
        "event_time": "2026-10-10T13:00:00+05:30",
        "category": "id_card",
        "colours": ["white", "blue"],
        "brand": "IIT Bhilai",
        "marks": ["blue lanyard", "Kanhar Hostel sticker"],
        "summary": "Lost IIT Bhilai Student ID Card",
        "sensitive": True,
        "image_spec": None,
    },
    {
        "key": "L5_KEYS_UNMATCHED",
        "report_type": "lost",
        "description": (
            "Meri hostel room ki chabi (3 silver keys with a blue guitar keychain) "
            "Sports ground badminton court ke paas gir gayi."
        ),
        "zone": "Sports ground",
        "event_time": "2026-10-09T18:15:00+05:30",
        "category": "keys",
        "colours": ["silver", "blue"],
        "brand": "",
        "marks": ["blue guitar keychain", "3 keys"],
        "summary": "Silver Keys with Blue Guitar Keychain",
        "sensitive": False,
        "image_spec": None,
    },
    {
        "key": "L6_EARBUDS_UNMATCHED",
        "report_type": "lost",
        "description": (
            "Lost white boAt Airdopes wireless earbuds in charging case near Hostel mess walkway."
        ),
        "zone": "Hostel",
        "event_time": "2026-10-09T21:00:00+05:30",
        "category": "electronics",
        "colours": ["white"],
        "brand": "boAt",
        "marks": ["charging case"],
        "summary": "White boAt Wireless Earbuds",
        "sensitive": False,
        "image_spec": None,
    },
]


def seed_database(db_path: Path | None = None) -> Dict[str, int]:
    """Reset and populate SQLite with the 12 demo reports. Returns a map of seed key -> report ID."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM claims")
        conn.execute("DELETE FROM reports")
        conn.commit()
    finally:
        conn.close()

    zones_cfg = load_zones_config()
    staffed_default = zones_cfg.get(
        "staffed_handover_default",
        "Staffed Security Desk (Main Gate / DOSA Office) — Bring Institute ID",
    )

    key_to_id: Dict[str, int] = {}

    for item in SEED_REPORTS:
        photo_filename = None
        if item.get("image_spec"):
            rgb, accent, label = item["image_spec"]
            raw_img = _make_demo_image(rgb, accent, label)
            photo_filename = sanitize_and_save_image(
                raw_img, UPLOADS_DIR, prefix=item["report_type"]
            )

        clean_desc = redact_pii(item["description"])
        sensitive = is_sensitive_item(
            item["category"], item.get("sensitive", False), clean_desc
        )
        drop_off = (
            enforce_staffed_handover(
                redact_pii(item.get("drop_off_point", "")),
                sensitive,
                staffed_default,
            )
            if item["report_type"] == "found"
            else ""
        )

        saved = insert_report(
            report_type=item["report_type"],
            description=clean_desc,
            zone=item["zone"],
            event_time=item["event_time"],
            drop_off_point=drop_off,
            category=item["category"],
            colours=item["colours"],
            brand=item["brand"],
            marks=item["marks"],
            summary=redact_pii(item["summary"]),
            sensitive=sensitive,
            verify_question=item.get("verify_question"),
            verify_answer=item.get("verify_answer"),
            photo_filename=photo_filename,
            status="open",
            db_path=db_path,
        )
        key_to_id[item["key"]] = saved["id"]

    return key_to_id


if __name__ == "__main__":
    mapping = seed_database()
    print(f"Seeded {len(mapping)} demo reports into CampusLost+ SQLite database:")
    for k, rid in mapping.items():
        print(f"  - {k}: Report #{rid}")
