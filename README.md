# Autonomous PR Reviewer

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-supported-blue)
![Code style](https://img.shields.io/badge/code%20style-black-black)
![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)

An AI-powered GitHub bot that automatically monitors pull requests, performs sandboxed static analysis, and posts actionable inline code review comments.

## Overview

The Autonomous PR Reviewer watches for `pull_request` events on GitHub, classifies changed files, runs language-appropriate linters inside isolated Docker containers, generates contextual feedback via an LLM, and posts inline comments. It also auto-approves trivial documentation-only changes and can optionally push minor fixes.

**Key features:**
- **Webhook Integration** — Secure `/webhook` endpoint with HMAC-SHA256 signature verification for `opened`, `synchronize`, and `reopened` events.
- **Diff Analysis** — Parses PR diffs, classifies files as code vs docs/config, and extracts changed line context.
- **Sandboxed Linting** — Runs `flake8`/`mypy` for Python and `eslint` for JS/TS inside Docker to avoid dependency conflicts.
- **LLM-Powered Review** — Uses an OpenAI-compatible LLM to generate specific, actionable inline review comments.
- **Memory & Deduplication** — SQLite-backed history prevents repeating identical advice across PRs.
- **Auto-Approval** — Automatically approves docs-only PRs.
- **Optional Auto-Fix** — Configurable auto-fix for simple formatting issues.

## Architecture

```
GitHub Webhook
     |
     v
FastAPI Server (/webhook)
     |
     +-- HMAC-SHA256 Verification
     |
     v
PR Fetch & Diff Parsing
     |
     +-- Classify files (code / docs / config)
     +-- Extract diff hunks & changed lines
     |
     v
Docker Linter Runner
     |
     +-- Python: flake8, mypy
     +-- JS/TS: eslint
     +-- Parse output → line-level issues
     |
     v
LLM Review Generator
     |
     +-- Prompt: diff + linter issues
     +-- Output: structured inline comments
     |
     v
Memory Check & GitHub Poster
     |
     +-- Deduplicate against SQLite history
     +-- Post inline comments
     +-- Post summary comment
     +-- Auto-approve docs-only PRs
```

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│ GitHub PR   │────▶│ FastAPI      │────▶│ Docker Linter   │────▶│ LLM Review   │
│ Webhook     │     │ Webhook      │     │ Runner          │     │ Generator    │
│             │     │ Handler      │     │ (flake8/eslint) │     │              │
└─────────────┘     └──────────────┘     └─────────────────┘     └──────┬───────┘
                                                                      │
                                                                      ▼
                                                            ┌──────────────────┐
                                                            │ GitHub API       │
                                                            │ Inline Comments  │
                                                            │ + Auto-Approval  │
                                                            └──────────────────┘
```

## Tech Stack

- **Language:** Python 3.10+
- **Web Framework:** FastAPI
- **GitHub Integration:** PyGithub
- **LLM Orchestration:** LangChain + OpenAI-compatible API
- **Static Analysis:** Docker-sandboxed `flake8`, `mypy`, `eslint`
- **Memory:** SQLite
- **Deployment:** Docker + Docker Compose

## Getting Started

### Prerequisites

- Python 3.10+
- Docker engine
- GitHub account with a bot token (`repo`, `pull_requests:write`)
- OpenAI-compatible API key

### Installation

```bash
git clone https://github.com/<YOUR_USERNAME>/autonomous-pr-reviewer.git
cd autonomous-pr-reviewer

# Copy environment template
cp .env.example .env

# Edit .env with your tokens and keys
# GITHUB_TOKEN=...
# WEBHOOK_SECRET=...
# LLM_API_KEY=...
# LLM_BASE_URL=...
# LLM_MODEL=...
```

### Build and Run

```bash
docker compose up --build -d
```

Verify it's running:

```bash
curl http://localhost:8000/health
```

### GitHub Webhook Setup

1. Go to your repository → **Settings** → **Webhooks** → **Add webhook**
2. **Payload URL:** `https://your-domain.com/webhook`
3. **Content type:** `application/json`
4. **Secret:** Same value as `WEBHOOK_SECRET` in `.env`
5. **Events:** Select **Pull requests**
6. For local testing, expose the server with **ngrok**:
   ```bash
   ngrok http 8000
   ```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `GITHUB_TOKEN` | GitHub PAT with `repo` + `pull_requests:write` | *(required)* |
| `WEBHOOK_SECRET` | Secret for HMAC-SHA256 webhook verification | *(required)* |
| `LLM_API_KEY` | OpenAI-compatible API key | *(required)* |
| `LLM_BASE_URL` | API base URL | `https://api.openai.com/v1` |
| `LLM_MODEL` | Model name | `gpt-4o-mini` |
| `AUTO_FIX_ENABLED` | Push auto-fixes to PR branches | `false` |
| `DOCKER_LINTER_IMAGE_PYTHON` | Python linter Docker image | `python:3.11-slim` |
| `DOCKER_LINTER_IMAGE_JS` | JS/TS linter Docker image | `node:20-slim` |
| `DOCKER_TIMEOUT_SECONDS` | Linter timeout | `120` |
| `DB_PATH` | SQLite database path | `data/reviews.db` |
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server port | `8000` |

### Supported Languages

| Language | File Extensions | Linters |
|----------|----------------|---------|
| Python | `.py` | `flake8`, `mypy` |
| JavaScript | `.js`, `.jsx` | `eslint` |
| TypeScript | `.ts`, `.tsx` | `eslint`, `tsc` |

To add new languages, extend `LINTER_CONFIG` in `app/linter/runner.py` with a new Docker image and linter command template.

## Usage

1. **PR Opened** — Webhook triggers, bot fetches the PR diff, classifies files.
2. **Docs-Only PRs** — Bot auto-approves with an "LGTM" comment.
3. **Code PRs** — Bot fetches file contents, runs sandboxed linters, sends diff + issues to the LLM.
4. **LLM Review** — Returns structured inline comments; bot checks SQLite for duplicates, posts new comments, and summarizes findings.
5. **Memory** — Future PRs reuse review history to reduce noise.

### Toggle Features

- **Auto-fix:** Set `AUTO_FIX_ENABLED=true` in `.env`
- **Auto-approval:** Always enabled for docs-only PRs
- **LLM model:** Change `LLM_MODEL` and `LLM_BASE_URL` for your provider

## Testing

Run unit tests for individual modules:

```bash
.venv/bin/python -c "from app.diff.parser import classify_file, parse_patch; assert classify_file('main.py')[1] == True; print('OK')"
.venv/bin/python -c "from app.memory.store import get_stats; print(get_stats())"
```

Simulate a docs-only PR:

```bash
.venv/bin/python -c "
from unittest.mock import MagicMock, patch
from app.webhook.models import WebhookPayload

payload = WebhookPayload.model_validate({...})  # see test examples in Phase 6
# Mock approvals and run process_pr(payload)
"
```

## Deployment

### Cloud VM

```bash
# On Ubuntu/Debian
sudo apt update && sudo apt install -y docker.io docker-compose git
sudo systemctl enable --now docker

git clone https://github.com/<YOUR_USERNAME>/autonomous-pr-reviewer.git
cd autonomous-pr-reviewer
cp .env.example .env
# Edit .env

docker compose up --build -d
```

### Reverse Proxy with HTTPS

Use **Caddy**, **Nginx**, or **Traefik** to terminate TLS in front of the FastAPI server. Example Caddyfile:

```
pr-reviewer.example.com {
  reverse_proxy localhost:8000
}
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-change`
3. Make changes and run tests
4. Commit with a clear message: `git commit -m "feat: add my change"`
5. Push and open a PR

Please follow [PEP 8](https://peps.python.org/pep-0008/) and run `black .` before submitting.

## License

MIT License — see [LICENSE](LICENSE) for details.
EOF
echo "README.md written"