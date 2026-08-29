"""Tests for LLM reviewer schema validation and guardrails."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.diff.parser import ChangedFile, FileType, Hunk
from app.llm.reviewer import review_file
from app.llm.schema import ReviewCommentSchema


class TestLLMReviewGuardrails:
    def _make_file(self, added_lines=None):
        """Create a minimal ChangedFile with a single hunk."""
        added = added_lines or [5, 6, 7]
        hunk = Hunk(
            old_start=1,
            old_lines=3,
            new_start=1,
            new_lines=3,
            content=" line1\n-line2\n+line2_new\n line3\n",
            added_lines=added,
        )
        return ChangedFile(
            path="main.py",
            status="modified",
            file_type=FileType.PYTHON,
            is_code=True,
            hunks=[hunk],
        )

    def test_schema_validates_valid_comment(self):
        data = {"line": 5, "body": "Looks good", "severity": "info"}
        schema = ReviewCommentSchema.model_validate(data)
        assert schema.line == 5
        assert schema.severity == "info"

    def test_schema_rejects_invalid_severity(self):
        with pytest.raises(Exception):
            ReviewCommentSchema.model_validate({"line": 5, "body": "x", "severity": "critical"})

    def test_schema_rejects_negative_line(self):
        with pytest.raises(Exception):
            ReviewCommentSchema.model_validate({"line": -1, "body": "x", "severity": "warning"})

    def test_hallucinated_line_is_filtered(self):
        """LLM comments referencing lines not in added_lines should be dropped."""
        file = self._make_file(added_lines=[5, 6, 7])

        mock_response = MagicMock()
        mock_response.content = '[{"line": 999, "body": " hallucinated", "severity": "warning"}]'

        with patch("app.llm.reviewer._get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = mock_response
            comments = review_file(file)
            assert comments == []

    def test_valid_comment_passes_through(self):
        file = self._make_file(added_lines=[5, 6, 7])
        mock_response = MagicMock()
        mock_response.content = '[{"line": 5, "body": "Use type hints", "severity": "warning"}]'

        with patch("app.llm.reviewer._get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = mock_response
            comments = review_file(file)
            assert len(comments) == 1
            assert comments[0].line == 5
            assert comments[0].body == "Use type hints"

    def test_schema_invalid_drops_comment(self):
        file = self._make_file(added_lines=[5, 6, 7])
        mock_response = MagicMock()
        mock_response.content = '[{"line": "not_a_number", "body": "bad", "severity": "warning"}]'

        with patch("app.llm.reviewer._get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = mock_response
            comments = review_file(file)
            assert comments == []
