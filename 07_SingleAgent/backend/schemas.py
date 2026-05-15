"""Pydantic 스키마."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_in: int


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    complete: bool = False
    curriculum: dict[str, Any] | None = None
    validation_result: dict[str, Any] | None = None
