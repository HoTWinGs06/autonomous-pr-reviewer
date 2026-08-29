"""Post review comments to GitHub PRs via PyGithub."""
from __future__ import annotations

import logging
from typing import List, Optional

from github import Github, GithubException
from github.PullRequest import PullRequest

from app.config import GITHUB_TOKEN
from app.llm.reviewer import ReviewComment

logger = logging.getLogger(__name__)


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


def post_inline_comments(
    repo_full_name: str,
    pr_number: int,
    head_sha: str,
    comments: List[ReviewComment],
) -> dict:
    """Post inline review comments on a PR.

    Args:
        repo_full_name: owner/repo format.
        pr_number: PR number.
        head_sha: Commit SHA for the comment position.
        comments: List of ReviewComment to post.

    Returns:
        Dict with posted count, skipped count, and any errors.
    """
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
            # Line may not exist in diff; fall back to general comment
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


def post_summary_comment(
    repo_full_name: str,
    pr_number: int,
    summary: str,
) -> bool:
    """Post a summary comment on the PR.

    Args:
        repo_full_name: owner/repo format.
        pr_number: PR number.
        summary: Summary text to post.

    Returns:
        True if posted successfully.
    """
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
    """Approve a PR (used for docs-only auto-approval).

    Args:
        repo_full_name: owner/repo format.
        pr_number: PR number.
        message: Approval message.

    Returns:
        True if approved successfully.
    """
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
