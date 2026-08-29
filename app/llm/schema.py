"""Pydantic schema for validated LLM review output."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewCommentSchema(BaseModel):
    """One inline review comment."""
    line: int = Field(ge=1, description="Line number in the new file")
    body: str = Field(max_length=500, description="Review comment text")
    severity: str = Field(pattern="^(error|warning|info)$", description="Issue severity")
