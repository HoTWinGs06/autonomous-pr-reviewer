"""Pydantic models for GitHub webhook payloads.

GitHub sends nested objects (pull_request.head.sha, sender.login, ...),
so models mirror the real payload structure rather than flat dotted keys.
"""
from __future__ import annotations

from pydantic import BaseModel


class Repository(BaseModel):
    full_name: str
    clone_url: str = ""
    default_branch: str = "main"


class User(BaseModel):
    login: str


class Head(BaseModel):
    sha: str
    ref: str = ""


class Base(BaseModel):
    ref: str


class PullRequest(BaseModel):
    number: int
    title: str
    state: str
    head: Head
    base: Base
    html_url: str
    user: User

    @property
    def head_sha(self) -> str:
        return self.head.sha


class Sender(BaseModel):
    login: str


class WebhookPayload(BaseModel):
    action: str
    pull_request: PullRequest
    repository: Repository
    sender: Sender
