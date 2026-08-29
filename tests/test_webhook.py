"""Tests for webhook security and models."""
from __future__ import annotations

import hashlib
import hmac

from app.webhook.security import verify_signature
from app.webhook.models import WebhookPayload


class TestVerifySignature:
    def test_valid_signature(self):
        secret = "mysecret"
        payload = b"hello world"
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_signature(payload, sig, secret) is True

    def test_invalid_signature(self):
        payload = b"hello world"
        assert verify_signature(payload, "sha256=bad", "mysecret") is False

    def test_missing_signature(self):
        assert verify_signature(b"payload", None, "secret") is False

    def test_wrong_prefix(self):
        payload = b"hello"
        assert verify_signature(payload, "md5=abc", "secret") is False

    def test_empty_secret(self):
        payload = b"hello"
        assert verify_signature(payload, "sha256=abc", "") is False


class TestWebhookPayload:
    def test_minimal_payload(self):
        data = {
            "action": "opened",
            "pull_request": {
                "number": 1,
                "title": "Test",
                "state": "open",
                "head.sha": "abc123",
                "base.ref": "main",
                "html_url": "https://github.com/o/r/pull/1",
                "user.login": "joel",
            },
            "repository": {
                "full_name": "owner/repo",
                "clone_url": "https://github.com/owner/repo.git",
                "default_branch": "main",
            },
            "sender.login": "joel",
        }
        payload = WebhookPayload.model_validate(data)
        assert payload.action == "opened"
        assert payload.pull_request.number == 1
        assert payload.repository.full_name == "owner/repo"
