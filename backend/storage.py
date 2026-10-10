"""SQLite storage for reviewed source notes (never for user conversations)."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


ALLOWED_HOSTS = {
    "www.ato.gov.au",
    "ato.gov.au",
    "immi.homeaffairs.gov.au",
    "www.education.gov.au",
    "my.gov.au",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_chunks (
    id INTEGER PRIMARY KEY,
    topic TEXT NOT NULL CHECK (topic IN ('tax', 'visa')),
    intent TEXT NOT NULL,
    agency TEXT NOT NULL,
    title TEXT NOT NULL,
    section TEXT NOT NULL,
    url TEXT NOT NULL,
    body TEXT NOT NULL,
    keywords TEXT NOT NULL,
    reviewed_on TEXT NOT NULL,
    digest TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'superseded')),
    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE VIRTUAL TABLE IF NOT EXISTS source_fts USING fts5(
    title, section, body, keywords, tokenize='porter unicode61'
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a file or in-memory database and create its small schema."""
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


def validate_note(raw: dict) -> dict:
    """Require an approved domain and explicit source provenance before staging."""
    required = ("topic", "intent", "agency", "title", "section", "url", "body", "keywords", "reviewed_on")
    if not isinstance(raw, dict) or any(not isinstance(raw.get(key), str) or not raw[key].strip() for key in required):
        raise ValueError("Each source note needs topic, intent, agency, title, section, URL, body, keywords and review date.")
    note = {key: raw[key].strip() for key in required}
    if note["topic"] not in {"tax", "visa"}:
        raise ValueError("Topic must be tax or visa.")
    if not re.fullmatch(r"[a-z_]+", note["intent"]):
        raise ValueError("Intent must use lower-case letters and underscores.")
    parsed = urlparse(note["url"])
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
        raise ValueError("Only allowlisted official HTTPS source URLs can be staged.")
    try:
        date.fromisoformat(note["reviewed_on"])
    except ValueError as exc:
        raise ValueError("Review date must use YYYY-MM-DD.") from exc
    if len(note["body"]) > 1800 or len(note["title"]) > 200 or len(note["section"]) > 200:
        raise ValueError("Source note is too long; split it into shorter reviewed sections.")
    return note


def stage_note(connection: sqlite3.Connection, raw: dict) -> tuple[int, str]:
    """Save a candidate. Pending notes are deliberately absent from the search index."""
    note = validate_note(raw)
    digest = hashlib.sha256(json.dumps(note, sort_keys=True).encode("utf-8")).hexdigest()
    existing = connection.execute("SELECT id, status FROM source_chunks WHERE digest=?", (digest,)).fetchone()
    if existing:
        return int(existing["id"]), str(existing["status"])
    with connection:
        columns = ", ".join(note)
        placeholders = ", ".join("?" for _ in note)
        cursor = connection.execute(
            f"INSERT INTO source_chunks ({columns}, digest, status) VALUES ({placeholders}, ?, 'pending')",
            (*note.values(), digest),
        )
    return int(cursor.lastrowid), "pending"


def approve_note(connection: sqlite3.Connection, note_id: int) -> None:
    """Index a reviewed note, replacing an older approved version of its section."""
    note = connection.execute("SELECT * FROM source_chunks WHERE id=?", (note_id,)).fetchone()
    if note is None:
        raise ValueError(f"No source note with ID {note_id}.")
    if note["status"] == "approved":
        return
    if note["status"] != "pending":
        raise ValueError("Only pending notes can be approved.")
    with connection:
        older = connection.execute(
            "SELECT id FROM source_chunks WHERE url=? AND section=? AND status='approved'",
            (note["url"], note["section"]),
        ).fetchall()
        for row in older:
            connection.execute("DELETE FROM source_fts WHERE rowid=?", (row["id"],))
            connection.execute("UPDATE source_chunks SET status='superseded' WHERE id=?", (row["id"],))
        connection.execute("UPDATE source_chunks SET status='approved' WHERE id=?", (note_id,))
        connection.execute(
            "INSERT INTO source_fts (rowid, title, section, body, keywords) VALUES (?, ?, ?, ?, ?)",
            (note_id, note["title"], note["section"], note["body"], note["keywords"]),
        )


def seed_if_empty(connection: sqlite3.Connection, seed_path: str | Path) -> int:
    """Add missing bundled notes without changing any existing reviewed section.

    This allows a new, separately reviewed seed section to reach an existing demo
    database while preserving local approvals and superseded versions.
    """
    seed = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    if not isinstance(seed, list):
        raise ValueError("Seed file must contain a list of source notes.")
    added = 0
    for raw in seed:
        note = validate_note(raw)
        existing = connection.execute(
            "SELECT 1 FROM source_chunks WHERE url=? AND section=? LIMIT 1",
            (note["url"], note["section"]),
        ).fetchone()
        if existing:
            continue
        note_id, _ = stage_note(connection, raw)
        approve_note(connection, note_id)
        added += 1
    return added


def list_notes(connection: sqlite3.Connection, status: str | None = None) -> list[dict]:
    if status is not None and status not in {"pending", "approved", "superseded"}:
        raise ValueError("Invalid source-note status.")
    query = "SELECT id, topic, intent, agency, title, section, url, reviewed_on, status FROM source_chunks"
    params: tuple[str, ...] = ()
    if status:
        query += " WHERE status=?"
        params = (status,)
    query += " ORDER BY id"
    return [dict(row) for row in connection.execute(query, params)]
