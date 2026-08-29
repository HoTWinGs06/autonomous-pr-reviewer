"""Tests for SQLite memory store: hashing, dedup, save, and stats."""
from __future__ import annotations

import os

import pytest

from app.memory.store import (
    _ensure_db,
    compute_comment_hash,
    get_stats,
    get_repo_review_history,
    is_duplicate_comment,
    save_review_comment,
    update_comment_status,
)


class TestCommentHash:
    def test_hash_stable(self):
        h1 = compute_comment_hash("main.py", 10, "Use type hints")
        h2 = compute_comment_hash("main.py", 10, "Use type hints")
        assert h1 == h2

    def test_hash_normalized(self):
        h1 = compute_comment_hash("main.py", 10, "Use   type   hints")
        h2 = compute_comment_hash("main.py", 10, "Use type hints")
        assert h1 == h2

    def test_hash_unique(self):
        h1 = compute_comment_hash("main.py", 10, "Use type hints")
        h2 = compute_comment_hash("main.py", 11, "Use type hints")
        assert h1 != h2


class TestMemoryOperations:
    def test_save_and_dedup(self):
        _ensure_db()
        rid = save_review_comment(1, "owner/repo", "main.py", 10, "Use type hints")
        assert rid > 0
        assert is_duplicate_comment("owner/repo", "main.py", 10, "Use type hints") is True
        assert is_duplicate_comment("other/repo", "main.py", 10, "Use type hints") is False
        assert is_duplicate_comment("owner/repo", "main.py", 11, "Use type hints") is False

    def test_status_update(self):
        _ensure_db()
        rid = save_review_comment(2, "owner/repo", "main.py", 10, "Use type hints")
        assert update_comment_status(rid, "applied") is True

    def test_repo_history(self):
        _ensure_db()
        save_review_comment(3, "owner/repo", "main.py", 10, "Use type hints")
        history = get_repo_review_history("owner/repo")
        assert len(history) >= 1
        assert history[0]["file_path"] == "main.py"

    def test_stats(self):
        _ensure_db()
        save_review_comment(4, "owner/repo", "main.py", 10, "Use type hints")
        stats = get_stats()
        assert stats["total_reviews"] >= 1
