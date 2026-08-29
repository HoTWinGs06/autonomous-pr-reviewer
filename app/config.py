"""Centralized configuration loaded from environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()

# GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

# LLM
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", None)

# Docker
DOCKER_LINTER_IMAGE_PYTHON = os.getenv("DOCKER_LINTER_IMAGE_PYTHON", "python:3.11-slim")
DOCKER_LINTER_IMAGE_JS = os.getenv("DOCKER_LINTER_IMAGE_JS", "node:20-slim")
DOCKER_TIMEOUT_SECONDS = int(os.getenv("DOCKER_TIMEOUT_SECONDS", "120"))

# Auto-fix
AUTO_FIX_ENABLED = os.getenv("AUTO_FIX_ENABLED", "false").lower() == "true"

# Database
DB_PATH = os.getenv("DB_PATH", "data/reviews.db")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
