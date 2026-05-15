"""커리큘럼 결과 JSON 저장/목록/다운로드."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "curricula"


class CurriculumStorage:
    def __init__(self, data_dir: Path = _DATA_DIR) -> None:
        self._dir = data_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        curriculum: dict[str, Any],
        validation: dict[str, Any] | None,
        requirements: dict[str, Any],
        attempts: int = 1,
    ) -> str:
        cid = str(uuid.uuid4())[:8]
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        company = curriculum.get("overview", {}).get("company", "unknown")
        filename = f"{ts}_{company}_{cid}.json"

        record = {
            "id": cid,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "company": company,
            "attempts": attempts,
            "requirements": requirements,
            "curriculum": curriculum,
            "validation": validation,
        }
        (self._dir / filename).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return cid

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for f in sorted(self._dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                ov = data.get("curriculum", {}).get("overview", {})
                items.append({
                    "id": data.get("id", f.stem),
                    "filename": f.name,
                    "created_at": data.get("created_at", ""),
                    "company": data.get("company", ""),
                    "days": ov.get("days", 0),
                    "hours_per_day": ov.get("hours_per_day", 0),
                    "total_hours": ov.get("total_hours", 0),
                    "validation_passed": data.get("validation", {}).get("passed", None),
                    "attempts": data.get("attempts", 1),
                })
            except Exception:
                continue
        return items

    def get(self, cid: str) -> dict[str, Any] | None:
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("id") == cid or f.stem.endswith(cid):
                    return data
            except Exception:
                continue
        return None

    def delete(self, cid: str) -> bool:
        for f in self._dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("id") == cid or f.stem.endswith(cid):
                    f.unlink()
                    return True
            except Exception:
                continue
        return False
