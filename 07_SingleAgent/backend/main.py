"""FastAPI 백엔드 — /chat, /auth, /health."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

_BASE = Path(__file__).resolve().parent.parent.parent
load_dotenv(_BASE / ".env")
sys.path.insert(0, str(_BASE / "07_SingleAgent"))

from agent.agent import CurriculumAgent
from backend.auth import authenticate, create_token, verify_token
from backend.schemas import ChatRequest, ChatResponse, LoginRequest, LoginResponse

app = FastAPI(title="AX Single Agent API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_sessions: dict[str, CurriculumAgent] = {}

_API_KEY = os.environ.get("OPENAI_API_KEY", "")
_TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "")
_CHROMA_DIR = _BASE / "chroma_db"
_DATA_DIR = _BASE / "Data"


def _get_or_create_agent(session_id: str) -> CurriculumAgent:
    if session_id not in _sessions:
        if not _API_KEY:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY 미설정")
        _sessions[session_id] = CurriculumAgent(
            api_key=_API_KEY,
            chroma_dir=_CHROMA_DIR,
            data_dir=_DATA_DIR,
            tavily_api_key=_TAVILY_KEY,
        )
    return _sessions[session_id]


@app.get("/health")
def health():
    return {"status": "ok", "sessions": len(_sessions)}


@app.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest):
    if not authenticate(body.username, body.password):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    token, expires_in = create_token(body.username)
    return LoginResponse(token=token, expires_in=expires_in)


@app.get("/auth/verify")
def verify(username: str = Depends(verify_token)):
    return {"username": username, "valid": True}


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, _: str = Depends(verify_token)):
    agent = _get_or_create_agent(body.session_id)
    try:
        reply, curriculum, validation = agent.chat(body.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    complete = curriculum is not None and validation is not None and validation.get("passed", False)
    return ChatResponse(
        reply=reply,
        complete=complete,
        curriculum=curriculum,
        validation_result=validation,
    )


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, _: str = Depends(verify_token)):
    _sessions.pop(session_id, None)
    return {"deleted": session_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
