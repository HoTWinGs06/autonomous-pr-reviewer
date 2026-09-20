"""Tests for optional safe auto-fix behavior."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.llm import poster
from app.linter.runner import LintIssue


def _issue(line: int, rule: str) -> LintIssue:
    return LintIssue(
        file_path="example.py",
        line=line,
        column=1,
        severity="warning",
        message="test",
        rule=rule,
    )


def _fake_pr(content: str):
    content_file = SimpleNamespace(
        content=__import__("base64").b64encode(content.encode()).decode(),
        sha="old-sha",
    )
    update_file = Mock()
    repo = SimpleNamespace(
        get_contents=lambda path, ref: content_file,
        update_file=update_file,
    )
    return SimpleNamespace(base=SimpleNamespace(repo=repo), head=SimpleNamespace(ref="test"))


def test_auto_fix_disabled_by_default(monkeypatch):
    monkeypatch.setattr(poster, "AUTO_FIX_ENABLED", False)
    result = poster.apply_safe_fixes("owner/repo", 1, {"example.py": [_issue(1, "W291")]})
    assert result == {"enabled": False, "fixed": 0, "skipped": 0, "errors": []}


def test_auto_fix_removes_trailing_whitespace(monkeypatch):
    monkeypatch.setattr(poster, "AUTO_FIX_ENABLED", True)
    fake_pr = _fake_pr("x = 1  \n")
    with patch.object(poster, "_get_pr", return_value=fake_pr):
        result = poster.apply_safe_fixes("owner/repo", 1, {"example.py": [_issue(1, "W291")]})

    assert result["fixed"] == 1
    fake_pr.base.repo.update_file.assert_called_once()
    args, kwargs = fake_pr.base.repo.update_file.call_args
    assert args[0] == "example.py"
    assert args[2] == "x = 1\n"
    assert kwargs["branch"] == "test"


def test_auto_fix_skips_mixed_unsafe_rules(monkeypatch):
    monkeypatch.setattr(poster, "AUTO_FIX_ENABLED", True)
    fake_pr = _fake_pr("x = 1  \n")
    with patch.object(poster, "_get_pr", return_value=fake_pr):
        result = poster.apply_safe_fixes(
            "owner/repo", 1, {"example.py": [_issue(1, "W291"), _issue(1, "E999")]}
        )

    assert result["fixed"] == 0
    assert result["skipped"] == 1
    assert result["errors"] == []
