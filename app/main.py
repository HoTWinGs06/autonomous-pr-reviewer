"""FastAPI application — full PR review pipeline."""
import logging
from fastapi import FastAPI, Request, HTTPException, Header
from typing import Optional
from github import Github

from app.config import GITHUB_TOKEN, WEBHOOK_SECRET
from app.webhook.security import verify_signature
from app.webhook.models import WebhookPayload
from app.diff.parser import FileType, parse_pr_files, is_docs_only_pr
from app.linter.runner import run_linters_on_files
from app.llm.reviewer import review_pr
from app.llm.poster import post_inline_comments, post_summary_comment, approve_pr
from app.memory.store import is_duplicate_comment, save_review_comment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Autonomous PR Reviewer", version="0.1.0")


def _fetch_file_contents(repo_full_name: str, pr_number: int, files: list) -> dict:
    """Fetch full file contents from GitHub for changed code files."""
    contents = {}
    if not GITHUB_TOKEN:
        return contents
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        for f in files:
            if f.is_code and f.status != "removed":
                try:
                    blob = repo.get_contents(f.path, ref=pr.head.sha)
                    import base64
                    contents[f.path] = base64.b64decode(blob.content).decode(
                        "utf-8", errors="replace"
                    )
                except Exception as e:
                    logger.warning(f"Could not fetch {f.path}: {e}")
    except Exception as e:
        logger.error(f"Failed to fetch file contents: {e}")
    return contents


async def process_pr(payload: WebhookPayload) -> dict:
    """Full PR review pipeline: diff → lint → LLM → dedup → post."""
    repo_name = payload.repository.full_name
    pr_number = payload.pull_request.number
    head_sha = payload.pull_request.head_sha

    # Step 1: Fetch PR files and classify
    try:
        if not GITHUB_TOKEN or GITHUB_TOKEN == "ghp_your_token_here":
            raise ValueError("GITHUB_TOKEN not configured")
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        raw_files = list(pr.get_files())
    except Exception as e:
        logger.error(f"Failed to fetch PR files: {e}")
        return {"status": "error", "detail": str(e)}

    classified = parse_pr_files(raw_files)
    logger.info(
        f"Classified {len(classified)} files "
        f"({sum(1 for f in classified if f.is_code)} code)"
    )

    # Step 2: Auto-approve docs-only PRs (conservative guardrails)
    if is_docs_only_pr(classified):
        # Guard 1: Max 50 changed files
        if len(classified) > 50:
            logger.info(f"Docs-only PR has {len(classified)} files, too many for auto-approval")
        else:
            # Guard 2: Fail closed — if any file is ambiguous, treat as code
            ambiguous = [f.path for f in classified if f.file_type == FileType.UNKNOWN]
            if ambiguous:
                logger.info(f"Ambiguous files detected: {ambiguous}, skipping auto-approval")
            else:
                logger.info("Docs-only PR detected, auto-approving")
                approve_pr(
                    repo_name, pr_number,
                    "LGTM — documentation/config changes only \U0001f916"
                )
                return {"status": "auto_approved", "pr": pr_number}

    # Step 3: Fetch file contents and run linters
    contents = _fetch_file_contents(repo_name, pr_number, classified)
    lint_result = run_linters_on_files(classified, contents)
    logger.info(f"Linted {lint_result.files_checked} files, found {len(lint_result.issues)} issues")

    # Build lint map by file
    lint_map = {}
    for issue in lint_result.issues:
        lint_map.setdefault(issue.file_path, []).append(issue)

    # Step 4: LLM review
    review = review_pr(classified, lint_map)
    logger.info(f"LLM generated {len(review.comments)} comments")

    # Step 5: Deduplicate and post
    posted = 0
    skipped = 0
    for comment in review.comments:
        if is_duplicate_comment(repo_name, comment.file_path, comment.line, comment.body):
            logger.info(f"Skipping duplicate: {comment.file_path}:{comment.line}")
            skipped += 1
            continue

        save_review_comment(
            pr_number=pr_number,
            repo=repo_name,
            file_path=comment.file_path,
            line=comment.line,
            body=comment.body,
            severity=comment.severity,
        )
        posted += 1

    # Post inline comments
    if review.comments:
        unique_comments = [
            c for c in review.comments
            if not is_duplicate_comment(repo_name, c.file_path, c.line, c.body)
        ]
        post_result = post_inline_comments(repo_name, pr_number, head_sha, unique_comments)
        logger.info(f"Posted {post_result['posted']} comments, skipped {post_result['skipped']}")

    # Post summary
    if review.summary:
        post_summary_comment(repo_name, pr_number, review.summary)

    return {
        "status": "reviewed",
        "pr": pr_number,
        "files": len(classified),
        "code_files": sum(1 for f in classified if f.is_code),
        "lint_issues": len(lint_result.issues),
        "llm_comments": len(review.comments),
        "posted": posted,
        "duplicates_skipped": skipped,
    }


@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
):
    """Handle GitHub webhook events."""
    body = await request.body()

    if WEBHOOK_SECRET and not verify_signature(body, x_hub_signature_256, WEBHOOK_SECRET):
        logger.warning("Invalid webhook signature received")
        raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event={x_github_event}"}

    try:
        payload = WebhookPayload.model_validate_json(body)
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    if payload.action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "reason": f"action={payload.action}"}

    logger.info(
        f"Processing PR #{payload.pull_request.number} "
        f"in {payload.repository.full_name} "
        f"(action={payload.action}, sha={payload.pull_request.head_sha[:7]})"
    )

    result = await process_pr(payload)
    return result


@app.get("/health")
async def health():
    return {"status": "ok"}
