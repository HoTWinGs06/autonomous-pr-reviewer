"""Pydantic models for GitHub webhook payloads."""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class Repository(BaseModel):
    full_name: str
    clone_url: str
    default_branch: str = "main"


class PullRequest(BaseModel):
    number: int
    title: str
    state: str
    head_sha: str = Field(alias="head.sha")
    base_ref: str = Field(alias="base.ref")
    html_url: str
    user_login: str = Field(alias="user.login")

    class Config:
        populate_by_name = True


class WebhookPayload(BaseModel):
    action: str
    pull_request: PullRequest
    repository: Repository
    sender_login: str = Field(alias="sender.login")

    class Config:
        populate_by_name = True
