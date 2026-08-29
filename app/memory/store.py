"""SQLite-based memory system for review deduplication and learning."""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, List

from app.config import DB_PATH

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_number INTEGER NOT NULL,
    repo TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line INTEGER NOT NULL,
    comment_hash TEXT NOT NULL,
    body TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning',
    status TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reviews_hash ON reviews(comment_hash);
CREATE INDEX IF NOT EXISTS idx_reviews_pr ON reviews(repo, pr_number);
CREATE INDEX IF NOT EXISTS idx_reviews_file ON reviews(repo, file_path);
"""


def _ensure_db() -> None:
    """Create database directory and initialize schema if needed."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection with row factory."""
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def compute_comment_hash(file_path: str, line: int, body: str) -> str:
    """Compute a stable hash for deduplication.

    Normalizes whitespace in body before hashing to avoid
    duplicate comments from minor formatting differences.
    """
    normalized = " ".join(body.strip().split())
    key = f"{file_path}:{line}:{normalized}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def is_duplicate_comment(
    repo: str,
    file_path: str,
    line: int,
    body: str,
) -> bool:
    """Check if a similar comment was already posted on this repo.

    Args:
        repo: Repository full name.
        file_path: File path in the PR.
        line: Line number.
        body: Comment body text.

    Returns:
        True if a matching comment exists (any PR in this repo).
    """
    comment_hash = compute_comment_hash(file_path, line, body)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM reviews WHERE repo = ? AND comment_hash = ? LIMIT 1",
            (repo, comment_hash),
        ).fetchone()

    return row is not None


def save_review_comment(
    pr_number: int,
    repo: str,
    file_path: str,
    line: int,
    body: str,
    severity: str = "warning",
    status: str = "unknown",
) -> int:
    """Save a review comment to the database.

    Args:
        pr_number: PR number.
        repo: Repository full name.
        file_path: File path.
        line: Line number.
        body: Comment body.
        severity: error/warning/info.
        status: unknown/ignored/applied.

    Returns:
        Row ID of inserted record.
    """
    comment_hash = compute_comment_hash(file_path, line, body)
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO reviews
               (
        pr_number, repo, file_path, line, comment_hash,
        body, severity, status, created_at, updated_at
    )
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pr_number, repo, file_path, line, comment_hash, body, severity, status, now, now),
        )
        return cursor.lastrowid


def update_comment_status(comment_id: int, status: str) -> bool:
    """Update the status of a review comment.

    Args:
        comment_id: Database row ID.
        status: New status (ignored/applied/unknown).

    Returns:
        True if updated successfully.
    """
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE reviews SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, comment_id),
        )
        return cursor.rowcount > 0


def get_repo_review_history(repo: str, limit: int = 50) -> List[dict]:
    """Get recent review history for a repository.

    Args:
        repo: Repository full name.
        limit: Max results to return.

    Returns:
        List of review records as dicts.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT pr_number, file_path, line, body, severity, status, created_at
               FROM reviews WHERE repo = ?
               ORDER BY created_at DESC LIMIT ?""",
            (repo, limit),
        ).fetchall()

    return [dict(row) for row in rows]


def get_stats() -> dict:
    """Get overall review statistics."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM reviews GROUP BY status"
        ).fetchall()
        by_severity = conn.execute(
            "SELECT severity, COUNT(*) as cnt FROM reviews GROUP BY severity"
        ).fetchall()

    return {
        "total_reviews": total,
        "by_status": {row["status"]: row["cnt"] for row in by_status},
        "by_severity": {
            row["severity"]: row["cnt"] for row in by_severity
        },
    }
