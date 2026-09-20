"""Post review comments and optional safe fixes to GitHub PRs."""
from __future__ import annotations

import base64
import logging
from typing import List, Optional

from github import Github, GithubException
from github.PullRequest import PullRequest

from app.config import AUTO_FIX_ENABLED, GITHUB_TOKEN
from app.llm.reviewer import ReviewComment
from app.linter.runner import LintIssue

logger = logging.getLogger(__name__)

# Only whitespace-only fixes are allowed automatically. In particular, do not
# auto-fix security, correctness, or style rules that can change behavior.
SAFE_FIX_RULES = frozenset({"W291", "W292", "W293"})


def _get_pr(repo_full_name: str, pr_number: int) -> Optional[PullRequest]:
    """Fetch a PR object from GitHub API."""
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN not configured")
        return None
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(repo_full_name)
        return repo.get_pull(pr_number)
    except GithubException as e:
        logger.error(f"Failed to fetch PR #{pr_number} in {repo_full_name}: {e}")
        return None


def apply_safe_fixes(
    repo_full_name: str,
    pr_number: int,
    lint_issues_by_file: dict[str, List[LintIssue]],
) -> dict:
    """Apply only safe whitespace fixes to the PR branch.

    Returns counts and errors. The feature is disabled unless
    ``AUTO_FIX_ENABLED=true``. Each changed file is committed through the
    GitHub Contents API, preserving the PR branch and avoiding local git state.
    """
    result = {"enabled": AUTO_FIX_ENABLED, "fixed": 0, "skipped": 0, "errors": []}
    if not AUTO_FIX_ENABLED:
        return result

    pr = _get_pr(repo_full_name, pr_number)
    if pr is None:
        result["errors"].append("Could not fetch PR")
        return result

    repo = pr.base.repo
    branch = pr.head.ref
    for path, issues in lint_issues_by_file.items():
        rules = {issue.rule for issue in issues}
        if not rules & SAFE_FIX_RULES:
            continue
        if not rules.issubset(SAFE_FIX_RULES):
            result["skipped"] += 1
            logger.info("Skipping mixed/unsafe fixes for %s: %s", path, sorted(rules))
            continue

        try:
            content_file = repo.get_contents(path, ref=branch)
            raw = base64.b64decode(content_file.content).decode("utf-8")
            lines = raw.splitlines(keepends=True)
            changed = False
            for issue in issues:
                index = issue.line - 1
                if not 0 <= index < len(lines):
                    continue
                old = lines[index]
                newline = "\n" if old.endswith("\n") else ""
                body = old[:-1] if newline else old
                if issue.rule == "W291":
                    fixed = body.rstrip(" \t") + newline
                elif issue.rule == "W292":
                    fixed = body.rstrip(" \t") + "\n"
                else:  # W293: blank line contains whitespace
                    fixed = "\n" if body.strip() == "" else body.rstrip(" \t") + newline
                if fixed != old:
                    lines[index] = fixed
                    changed = True

            if not changed:
                result["skipped"] += 1
                continue

            repo.update_file(
                path,
                f"fix: safe whitespace cleanup in {path}",
                "".join(lines),
                content_file.sha,
                branch=branch,
            )
            result["fixed"] += 1
            logger.info("Applied safe whitespace fixes to %s", path)
        except GithubException as e:
            result["errors"].append(f"{path}: {e}")
            logger.error("Failed to apply safe fix to %s: %s", path, e)

    return result


def post_inline_comments(
    repo_full_name: str,
    pr_number: int,
    head_sha: str,
    comments: List[ReviewComment],
) -> dict:
    """Post inline review comments on a PR."""
    result = {"posted": 0, "skipped": 0, "errors": []}
    if not comments:
        return result

    pr = _get_pr(repo_full_name, pr_number)
    if pr is None:
        result["errors"].append("Could not fetch PR")
        return result

    for comment in comments:
        try:
            pr.create_review_comment(
                body=f"**[{comment.severity.upper()}]** {comment.body}",
                commit=pr.head.sha,
                path=comment.file_path,
                line=comment.line,
            )
            result["posted"] += 1
            logger.info(f"Posted comment on {comment.file_path}:{comment.line}")
        except GithubException as e:
            logger.warning(
                f"Inline comment failed for {comment.file_path}:{comment.line}: {e}. "
                "Attempting general comment."
            )
            try:
                pr.create_issue_comment(
                    f"**[{comment.severity.upper()}]** "
                    f"`{comment.file_path}:{comment.line}`\n\n{comment.body}"
                )
                result["posted"] += 1
            except GithubException as e2:
                result["errors"].append(
                    f"Failed to post comment on {comment.file_path}:{comment.line}: {e2}"
                )
                result["skipped"] += 1

    return result


def post_summary_comment(repo_full_name: str, pr_number: int, summary: str) -> bool:
    """Post a summary comment on the PR."""
    pr = _get_pr(repo_full_name, pr_number)
    if pr is None:
        return False
    try:
        pr.create_issue_comment(f"## 🤖 Automated Code Review\n\n{summary}")
        logger.info(f"Posted summary on PR #{pr_number}")
        return True
    except GithubException as e:
        logger.error(f"Failed to post summary on PR #{pr_number}: {e}")
        return False


def approve_pr(repo_full_name: str, pr_number: int, message: str = "LGTM") -> bool:
    """Approve a PR (used for docs-only auto-approval)."""
    pr = _get_pr(repo_full_name, pr_number)
    if pr is None:
        return False
    try:
        pr.create_review(event="APPROVE", body=message)
        logger.info(f"Approved PR #{pr_number}")
        return True
    except GithubException as e:
        logger.error(f"Failed to approve PR #{pr_number}: {e}")
        return False
