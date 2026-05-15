"""JWT 인증 (07_SingleAgent과 동일 구조)."""
from __future__ import annotations

import hashlib
import os
import time

import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_SECRET = os.environ.get("JWT_SECRET", "ax-multiagent-secret-key")
_ALG = "HS256"
_TTL = 8 * 3600

USERS: dict[str, str] = {
    "admin": hashlib.sha256("admin".encode()).hexdigest(),
}

_bearer = HTTPBearer()


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def create_token(username: str) -> tuple[str, int]:
    exp = int(time.time()) + _TTL
    token = jwt.encode({"sub": username, "exp": exp}, _SECRET, algorithm=_ALG)
    return token, _TTL


def verify_token(credentials: HTTPAuthorizationCredentials = Security(_bearer)) -> str:
    try:
        payload = jwt.decode(credentials.credentials, _SECRET, algorithms=[_ALG])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")


def authenticate(username: str, password: str) -> bool:
    return USERS.get(username) == _hash(password)
