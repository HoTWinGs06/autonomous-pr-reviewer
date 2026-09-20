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


class TestWebhookEndpoint:
    """Integration tests for the /webhook HTTP endpoint."""

    def _make_payload(self) -> bytes:
        import json
        return json.dumps({
            "action": "opened",
            "pull_request": {
                "number": 42,
                "title": "Test PR",
                "state": "open",
                "head.sha": "abc123def456",
                "base.ref": "main",
                "html_url": "https://github.com/o/r/pull/42",
                "user.login": "joel",
            },
            "repository": {
                "full_name": "owner/repo",
                "clone_url": "https://github.com/owner/repo.git",
                "default_branch": "main",
            },
            "sender.login": "joel",
        }).encode()

    @staticmethod
    def _fresh_client(monkeypatch, secret: str):
        """Reload app.config/app.main with a controlled WEBHOOK_SECRET.

        app.config reads env vars at import time, so tests must reload
        the modules after changing the environment — otherwise results
        depend on whether a local .env exists (CI has none).
        """
        monkeypatch.setenv("WEBHOOK_SECRET", secret)
        import importlib
        import app.config
        importlib.reload(app.config)
        import app.main
        importlib.reload(app.main)
        from fastapi.testclient import TestClient
        return TestClient(app.main.app)

    def test_missing_signature_rejected(self, monkeypatch):
        client = self._fresh_client(monkeypatch, "testsecret")
        resp = client.post(
            "/webhook",
            content=self._make_payload(),
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert resp.status_code == 401

    def test_invalid_signature_rejected(self, monkeypatch):
        client = self._fresh_client(monkeypatch, "testsecret")
        resp = client.post(
            "/webhook",
            content=self._make_payload(),
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=deadbeef",
            },
        )
        assert resp.status_code == 401

    def test_non_pr_event_ignored(self, monkeypatch):
        fresh_client = self._fresh_client(monkeypatch, "")

        resp = fresh_client.post(
            "/webhook",
            content=self._make_payload(),
            headers={"X-GitHub-Event": "push"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_valid_signature_accepted(self, monkeypatch):
        secret = "testsecret"
        fresh_client = self._fresh_client(monkeypatch, secret)

        payload = self._make_payload()
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        resp = fresh_client.post(
            "/webhook",
            content=payload,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": sig,
            },
        )
        # Will fail at GitHub API call (no real token), but should pass signature check
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("reviewed", "error")

    def test_ignored_action(self, monkeypatch):
        fresh_client = self._fresh_client(monkeypatch, "")

        import json
        payload = json.dumps({
            "action": "closed",
            "pull_request": {
                "number": 1, "title": "x", "state": "closed",
                "head.sha": "a", "base.ref": "main",
                "html_url": "x", "user.login": "x",
            },
            "repository": {
                "full_name": "o/r", "clone_url": "x", "default_branch": "main",
            },
            "sender.login": "x",
        }).encode()
        resp = fresh_client.post(
            "/webhook",
            content=payload,
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert resp.status_code == 200
        assert resp.json()["reason"] == "action=closed"
