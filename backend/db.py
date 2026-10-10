"""SQLite persistence layer for CampusLost+.

Stores reports (lost and found) and ownership claims.
All stored text is PII-redacted before insertion.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "campus_lost_plus.db"


def get_db_path() -> Path:
    """Resolve SQLite database path from DATABASE_PATH env var or default."""
    env_path = os.getenv("DATABASE_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        return p if p.is_absolute() else (PROJECT_ROOT / p)
    return DEFAULT_DB_PATH


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open a SQLite connection with Row factory enabled."""
    target = db_path or get_db_path()
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Create the reports and claims tables if they do not exist."""
    conn = get_connection(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL CHECK(report_type IN ('lost', 'found')),
                description TEXT NOT NULL,
                zone TEXT NOT NULL,
                event_time TEXT NOT NULL,
                drop_off_point TEXT DEFAULT '',
                category TEXT NOT NULL DEFAULT 'other',
                colours_json TEXT NOT NULL DEFAULT '[]',
                brand TEXT NOT NULL DEFAULT '',
                marks_json TEXT NOT NULL DEFAULT '[]',
                summary TEXT NOT NULL DEFAULT '',
                sensitive INTEGER NOT NULL DEFAULT 0,
                verify_question TEXT DEFAULT NULL,
                verify_answer TEXT DEFAULT NULL,
                photo_filename TEXT DEFAULT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                found_report_id INTEGER NOT NULL,
                lost_report_id INTEGER DEFAULT NULL,
                attempts_used INTEGER NOT NULL DEFAULT 0,
                verified INTEGER NOT NULL DEFAULT 0,
                verify_method TEXT DEFAULT '',
                status_stage TEXT NOT NULL DEFAULT 'Matched',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (found_report_id) REFERENCES reports(id)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def insert_report(
    *,
    report_type: str,
    description: str,
    zone: str,
    event_time: str,
    drop_off_point: str = "",
    category: str = "other",
    colours: Optional[List[str]] = None,
    brand: str = "",
    marks: Optional[List[str]] = None,
    summary: str = "",
    sensitive: bool = False,
    verify_question: Optional[str] = None,
    verify_answer: Optional[str] = None,
    photo_filename: Optional[str] = None,
    status: str = "open",
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Insert a sanitised report into SQLite and return the stored dictionary."""
    conn = get_connection(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """
            INSERT INTO reports (
                report_type, description, zone, event_time, drop_off_point,
                category, colours_json, brand, marks_json, summary,
                sensitive, verify_question, verify_answer, photo_filename,
                status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_type,
                description,
                zone,
                event_time,
                drop_off_point,
                category,
                json.dumps(colours or []),
                brand or "",
                json.dumps(marks or []),
                summary or description[:80],
                1 if sensitive else 0,
                verify_question,
                verify_answer,
                photo_filename,
                status,
                now,
            ),
        )
        conn.commit()
        report_id = cur.lastrowid
        return get_report_by_id(report_id, db_path=db_path)  # type: ignore[return-value]
    finally:
        conn.close()


def _row_to_report_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a SQLite Row into a structured Python dictionary."""
    return {
        "id": row["id"],
        "report_type": row["report_type"],
        "description": row["description"],
        "zone": row["zone"],
        "event_time": row["event_time"],
        "drop_off_point": row["drop_off_point"] or "",
        "category": row["category"],
        "colours": json.loads(row["colours_json"] or "[]"),
        "brand": row["brand"] or "",
        "marks": json.loads(row["marks_json"] or "[]"),
        "summary": row["summary"] or "",
        "sensitive": bool(row["sensitive"]),
        "verify_question": row["verify_question"],
        "verify_answer": row["verify_answer"],
        "photo_filename": row["photo_filename"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


def get_report_by_id(
    report_id: int, db_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """Fetch a single report by primary key."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        return _row_to_report_dict(row) if row else None
    finally:
        conn.close()


def list_reports(
    report_type: Optional[str] = None,
    status: Optional[str] = None,
    zone: Optional[str] = None,
    category: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """List reports with optional filters, newest first."""
    conn = get_connection(db_path)
    try:
        clauses: List[str] = []
        params: List[Any] = []
        if report_type:
            clauses.append("report_type = ?")
            params.append(report_type)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if zone:
            clauses.append("zone = ?")
            params.append(zone)
        if category:
            clauses.append("category = ?")
            params.append(category)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM reports {where_sql} ORDER BY id DESC", params
        ).fetchall()
        return [_row_to_report_dict(r) for r in rows]
    finally:
        conn.close()


def get_or_create_claim(
    found_report_id: int,
    lost_report_id: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Fetch existing claim record for (found_report_id, lost_report_id) or create one."""
    conn = get_connection(db_path)
    try:
        if lost_report_id is not None:
            row = conn.execute(
                "SELECT * FROM claims WHERE found_report_id = ? AND lost_report_id = ?",
                (found_report_id, lost_report_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM claims WHERE found_report_id = ? AND lost_report_id IS NULL",
                (found_report_id,),
            ).fetchone()

        if row:
            return dict(row)

        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """
            INSERT INTO claims (
                found_report_id, lost_report_id, attempts_used,
                verified, verify_method, status_stage, updated_at
            ) VALUES (?, ?, 0, 0, '', 'Matched', ?)
            """,
            (found_report_id, lost_report_id, now),
        )
        conn.commit()
        created = conn.execute(
            "SELECT * FROM claims WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(created)
    finally:
        conn.close()


def get_claim_by_id(
    claim_id: int, db_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """Fetch a claim by ID."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM claims WHERE id = ?", (claim_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_claim_verification(
    claim_id: int,
    *,
    attempts_used: int,
    verified: bool,
    verify_method: str,
    status_stage: str,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Update attempt counter and verification status for a claim."""
    conn = get_connection(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE claims
            SET attempts_used = ?, verified = ?, verify_method = ?, status_stage = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                attempts_used,
                1 if verified else 0,
                verify_method,
                status_stage,
                now,
                claim_id,
            ),
        )
        if verified:
            claim_row = conn.execute(
                "SELECT found_report_id, lost_report_id FROM claims WHERE id = ?",
                (claim_id,),
            ).fetchone()
            if claim_row:
                conn.execute(
                    "UPDATE reports SET status = 'claimed' WHERE id = ?",
                    (claim_row["found_report_id"],),
                )
                if claim_row["lost_report_id"]:
                    conn.execute(
                        "UPDATE reports SET status = 'claimed' WHERE id = ?",
                        (claim_row["lost_report_id"],),
                    )
        conn.commit()
        row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_claim_stage(
    claim_id: int, stage: str, db_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """Advance the status tracker stage ('Matched', 'Verified', 'Handover scheduled', 'Done')."""
    conn = get_connection(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE claims SET status_stage = ?, updated_at = ? WHERE id = ?",
            (stage, now, claim_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
