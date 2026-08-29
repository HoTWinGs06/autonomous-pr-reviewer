"""LLM-powered code review generation with structured output."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import LLM_API_KEY, LLM_MODEL, LLM_BASE_URL
from app.diff.parser import ChangedFile, Hunk
from app.linter.runner import LintIssue

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior software engineer performing a code review.
Analyze the provided diff hunks and linter output for a single file.
Focus ONLY on the changed lines (lines starting with + in the diff).

Rules:
- Be concise and actionable. No generic advice.
- Point out bugs, security issues, performance problems, and style violations.
- Do NOT repeat linter warnings unless they indicate a deeper issue.
- Reference specific line numbers from the NEW file (the + side of the diff).
- If the code looks good, say so briefly — do not invent problems.

Output format: Return a JSON array of review comments. Each comment must have:
- "line": integer (line number in the new file)
- "body": string (the review comment, max 500 chars)
- "severity": "error" | "warning" | "info"

If no issues found, return an empty array: []
Return ONLY valid JSON, no markdown fences or explanation."""


@dataclass
class ReviewComment:
    """A single LLM-generated review comment."""
    file_path: str
    line: int
    body: str
    severity: str = "warning"


@dataclass
class ReviewResult:
    """Aggregated review results for a PR."""
    comments: List[ReviewComment] = field(default_factory=list)
    summary: str = ""
    errors: List[str] = field(default_factory=list)


def _build_review_prompt(
    file: ChangedFile,
    lint_issues: List[LintIssue],
) -> str:
    """Build the human message prompt for reviewing a single file."""
    parts = [f"## File: {file.path} ({file.file_type.value})\n"]

    # Add diff hunks
    parts.append("### Diff Hunks:")
    for hunk in file.hunks:
        parts.append(f"```\n{hunk.content}```")
        if hunk.added_lines:
            parts.append(f"(Added lines at: {hunk.added_lines})")

    # Add linter output
    if lint_issues:
        parts.append("\n### Linter Issues:")
        for issue in lint_issues[:10]:  # Cap to avoid token overflow
            parts.append(f"- Line {issue.line}: [{issue.severity}] {issue.rule}: {issue.message}")

    parts.append("\nProvide your review as a JSON array per the system instructions.")
    return "\n".join(parts)


def _get_llm() -> ChatOpenAI:
    """Create configured LLM client."""
    kwargs = {
        "model": LLM_MODEL,
        "api_key": LLM_API_KEY,
        "temperature": 0.2,
        "max_tokens": 2000,
    }
    if LLM_BASE_URL:
        kwargs["base_url"] = LLM_BASE_URL
    return ChatOpenAI(**kwargs)


def review_file(
    file: ChangedFile,
    lint_issues: Optional[List[LintIssue]] = None,
) -> List[ReviewComment]:
    """Generate LLM review comments for a single changed file.

    Args:
        file: Classified changed file with diff hunks.
        lint_issues: Optional lint issues to include as context.

    Returns:
        List of ReviewComment objects.
    """
    if not file.hunks:
        return []

    llm = _get_llm()
    prompt = _build_review_prompt(file, lint_issues or [])

    try:
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])

        raw = response.content.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]

        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            logger.warning(f"LLM returned non-list for {file.path}: {type(parsed)}")
            return []

        comments = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            line = item.get("line")
            body = item.get("body", "")
            if line is None or not body:
                continue
            comments.append(ReviewComment(
                file_path=file.path,
                line=int(line),
                body=body[:500],
                severity=item.get("severity", "warning"),
            ))
        return comments

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON for {file.path}: {e}")
        return []
    except Exception as e:
        logger.error(f"LLM review failed for {file.path}: {e}")
        return []


def review_pr(
    files: List[ChangedFile],
    lint_results_by_file: Optional[dict[str, List[LintIssue]]] = None,
) -> ReviewResult:
    """Review all changed code files in a PR.

    Args:
        files: List of classified changed files.
        lint_results_by_file: Dict mapping file path to lint issues.

    Returns:
        ReviewResult with all comments and optional summary.
    """
    result = ReviewResult()
    lint_map = lint_results_by_file or {}

    code_files = [f for f in files if f.is_code and f.hunks]

    for cf in code_files:
        issues = lint_map.get(cf.path, [])
        try:
            comments = review_file(cf, issues)
            result.comments.extend(comments)
        except Exception as e:
            result.errors.append(f"Review failed for {cf.path}: {e}")
            logger.error(f"Review failed for {cf.path}: {e}")

    # Generate summary if there are comments
    if result.comments:
        error_count = sum(1 for c in result.comments if c.severity == "error")
        warn_count = sum(1 for c in result.comments if c.severity == "warning")
        result.summary = f"Found {len(result.comments)} issues ({error_count} errors, {warn_count} warnings) across {len(code_files)} files."

    return result
