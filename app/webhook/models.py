"""Pydantic models for GitHub webhook payloads."""
from __future__ import annotations


from pydantic import BaseModel, Field, ConfigDict

class Repository(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    full_name: str
    clone_url: str
    default_branch: str = "main"


class PullRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    number: int
    title: str
    state: str
    head_sha: str = Field(alias="head.sha")
    base_ref: str = Field(alias="base.ref")
    html_url: str
    user_login: str = Field(alias="user.login")


class WebhookPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    action: str
    pull_request: PullRequest
    repository: Repository
    sender_login: str = Field(alias="sender.login")
