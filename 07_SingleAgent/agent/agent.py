"""CurriculumAgent — OpenAI tool-calling ReAct 루프."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

_WORKSPACE = Path(__file__).resolve().parent.parent.parent
_PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt"

sys.path.insert(0, str(_WORKSPACE / "05_Advanced_RAG_indexing_contextual"))
from indexing_pipeline import AdvancedRAGIndexer

from .tools import (
    TOOL_SCHEMAS,
    CurriculumGeneratorTool,
    RAGTool,
    ValidatorTool,
    WebSearchTool,
)

_MAX_STEPS = 10
_MAX_REGEN = 3


def _load_system_prompt() -> str:
    if _PROMPT_FILE.exists():
        return _PROMPT_FILE.read_text(encoding="utf-8")
    return "당신은 AX Compass 기반 AI 교육 커리큘럼 전문가입니다."


class CurriculumAgent:
    """단일 세션 커리큘럼 생성 에이전트."""

    def __init__(
        self,
        api_key: str,
        chroma_dir: Path,
        data_dir: Path,
        tavily_api_key: str = "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",
        model: str = "gpt-4o-mini",
        on_tool_call: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._on_tool_call = on_tool_call

        indexer = AdvancedRAGIndexer(
            api_key=api_key,
            chroma_dir=chroma_dir,
            data_dir=data_dir,
            rerank=True,
        )
        self._rag = RAGTool(indexer)
        self._web = WebSearchTool(tavily_api_key) if tavily_api_key else None
        self._generator = CurriculumGeneratorTool(api_key, model=model)
        self._validator = ValidatorTool()

        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": _load_system_prompt()}
        ]
        self._last_curriculum: dict[str, Any] | None = None
        self._last_validation: dict[str, Any] | None = None
        self._regen_count = 0

    @property
    def history(self) -> list[dict[str, Any]]:
        return self._messages[1:]  # system 제외

    def chat(self, user_message: str) -> tuple[str, dict | None, dict | None]:
        """
        Returns:
            (reply_text, curriculum_or_None, validation_or_None)
        """
        self._messages.append({"role": "user", "content": user_message})
        self._last_curriculum = None
        self._last_validation = None

        for _ in range(_MAX_STEPS):
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=self._messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
            )
            msg = resp.choices[0].message
            self._messages.append(msg.model_dump(exclude_unset=True))

            if resp.choices[0].finish_reason != "tool_calls":
                break

            for tc in msg.tool_calls or []:
                result = self._dispatch(tc.function.name, json.loads(tc.function.arguments))
                self._messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                })

        reply = self._messages[-1].get("content") or ""
        if isinstance(reply, list):
            reply = " ".join(p.get("text", "") for p in reply if isinstance(p, dict))

        return str(reply), self._last_curriculum, self._last_validation

    def _dispatch(self, name: str, args: dict[str, Any]) -> Any:
        if self._on_tool_call:
            self._on_tool_call(name, args)

        if name == "rag_search":
            return self._rag.search(args["query"], k=args.get("k", 6))

        if name == "web_search":
            if self._web is None:
                return "웹 검색 기능이 비활성화되어 있습니다 (TAVILY_API_KEY 미설정)."
            return self._web.search(args["query"], max_results=args.get("max_results", 3))

        if name == "generate_curriculum":
            if self._regen_count >= _MAX_REGEN:
                return {"error": f"커리큘럼 재생성 한도({_MAX_REGEN}회) 초과"}
            self._regen_count += 1
            curriculum = self._generator.generate(
                company=args.get("company", ""),
                audience=args.get("audience", ""),
                goal=args.get("goal", ""),
                days=int(args.get("days", 1)),
                hours_per_day=float(args.get("hours_per_day", 8)),
                ax_counts=args.get("ax_counts", {}),
                ai_experience=args.get("ai_experience", ""),
                constraints=args.get("constraints", ""),
                rag_context=args.get("rag_context", ""),
            )
            self._last_curriculum = curriculum
            return curriculum

        if name == "validate_curriculum":
            curriculum = args.get("curriculum") or self._last_curriculum or {}
            result = self._validator.validate(
                curriculum=curriculum,
                requirements=args.get("requirements", {}),
            )
            self._last_validation = result
            if not result["passed"]:
                # validation 실패 시 regen 카운터 리셋 허용 (최대 재시도용)
                self._regen_count = max(0, self._regen_count - 1)
            return result

        return {"error": f"알 수 없는 도구: {name}"}

    def reset(self) -> None:
        self._messages = [{"role": "system", "content": _load_system_prompt()}]
        self._last_curriculum = None
        self._last_validation = None
        self._regen_count = 0
