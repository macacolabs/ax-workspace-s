from __future__ import annotations
from typing import Any
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_in: int


class GenerateRequest(BaseModel):
    company: str
    audience: str
    ai_experience: str = ""
    constraints: str = ""
    goal: str
    days: int
    hours_per_day: float
    ax_counts: dict[str, int]


class GenerateResponse(BaseModel):
    success: bool
    attempts: int
    reply: str
    curriculum: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    curriculum_id: str | None = None


class CurriculumListItem(BaseModel):
    id: str
    filename: str
    created_at: str
    company: str
    days: int
    hours_per_day: float
    total_hours: float
    validation_passed: bool | None
    attempts: int
