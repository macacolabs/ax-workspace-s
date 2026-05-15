"""BaseAgent — 프롬프트 로딩 + OpenAI 호출 공통 기반."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from openai import OpenAI

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"Prompt file not found: {path}")


class BaseAgent:
    name: str = "BaseAgent"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def _chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict | None = None,
        temperature: float = 0.7,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""
