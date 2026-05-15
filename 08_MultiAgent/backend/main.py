"""FastAPI 백엔드 — /generate, /curricula, /auth, /health."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

_BASE = Path(__file__).resolve().parent.parent.parent
load_dotenv(_BASE / ".env")
sys.path.insert(0, str(_BASE / "08_MultiAgent"))

from agents.orchestrator import OrchestratorAgent
from backend.auth import authenticate, create_token, verify_token
from backend.schemas import (
    CurriculumListItem,
    GenerateRequest,
    GenerateResponse,
    LoginRequest,
    LoginResponse,
)
from backend.storage import CurriculumStorage

app = FastAPI(title="AX MultiAgent API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_API_KEY = os.environ.get("OPENAI_API_KEY", "")
_CHROMA_DIR = _BASE / "chroma_db"
_DATA_DIR = _BASE / "Data"
_storage = CurriculumStorage()


def _make_orchestrator() -> OrchestratorAgent:
    if not _API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY 미설정")
    return OrchestratorAgent(
        api_key=_API_KEY,
        chroma_dir=_CHROMA_DIR,
        data_dir=_DATA_DIR,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest):
    if not authenticate(body.username, body.password):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    token, expires_in = create_token(body.username)
    return LoginResponse(token=token, expires_in=expires_in)


@app.get("/auth/verify")
def verify(username: str = Depends(verify_token)):
    return {"username": username, "valid": True}


@app.post("/generate", response_model=GenerateResponse)
def generate(body: GenerateRequest, _: str = Depends(verify_token)):
    orchestrator = _make_orchestrator()
    requirements = body.model_dump()
    try:
        result = orchestrator.run(requirements)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    cid = None
    if result.curriculum:
        cid = _storage.save(
            curriculum=result.curriculum,
            validation=result.validation.to_dict() if result.validation else None,
            requirements=requirements,
            attempts=result.attempts,
        )

    return GenerateResponse(
        success=result.success,
        attempts=result.attempts,
        reply=result.reply,
        curriculum=result.curriculum,
        validation=result.validation.to_dict() if result.validation else None,
        curriculum_id=cid,
    )


@app.get("/curricula", response_model=list[CurriculumListItem])
def list_curricula(_: str = Depends(verify_token)):
    return _storage.list()


@app.get("/curricula/{cid}")
def get_curriculum(cid: str, _: str = Depends(verify_token)):
    data = _storage.get(cid)
    if data is None:
        raise HTTPException(status_code=404, detail="커리큘럼을 찾을 수 없습니다.")
    return data


@app.delete("/curricula/{cid}")
def delete_curriculum(cid: str, _: str = Depends(verify_token)):
    if not _storage.delete(cid):
        raise HTTPException(status_code=404, detail="커리큘럼을 찾을 수 없습니다.")
    return {"deleted": cid}


@app.get("/curricula/{cid}/download")
def download_curriculum(cid: str, _: str = Depends(verify_token)):
    data = _storage.get(cid)
    if data is None:
        raise HTTPException(status_code=404, detail="커리큘럼을 찾을 수 없습니다.")
    company = data.get("company", "curriculum")
    return JSONResponse(
        content=data.get("curriculum"),
        headers={"Content-Disposition": f'attachment; filename="{company}_curriculum.json"'},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
