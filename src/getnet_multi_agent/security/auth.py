"""HS256 JWT identity: CLI-issued tokens and FastAPI role dependencies."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from getnet_multi_agent.contracts import Principal
from getnet_multi_agent.core.settings import Settings, get_settings
from getnet_multi_agent.security.pseudonym import pseudonym

ROLES = ("merchant", "operator")


class AuthError(Exception):
    """Missing, invalid or expired token, or an unknown role."""


def _secret(settings: Settings) -> str:
    if not settings.JWT_SECRET:
        raise AuthError("JWT_SECRET is not set")
    return settings.JWT_SECRET


def issue_token(sub: str, role: str, hours: float = 12, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    if role not in ROLES:
        raise AuthError(f"unknown role {role!r}")
    now = datetime.now(UTC)
    claims = {
        "iss": s.JWT_ISSUER, "aud": s.JWT_AUDIENCE, "sub": sub, "role": role,
        "iat": now, "exp": now + timedelta(hours=hours),
    }
    return jwt.encode(claims, _secret(s), algorithm="HS256")


def decode_token(token: str, settings: Settings | None = None) -> Principal:
    s = settings or get_settings()
    try:
        claims = jwt.decode(
            token, _secret(s), algorithms=["HS256"], audience=s.JWT_AUDIENCE,
            issuer=s.JWT_ISSUER, options={"require": ["exp", "sub", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc
    role = claims.get("role")
    if role not in ROLES:
        raise AuthError(f"unknown role {role!r}")
    sub = str(claims["sub"])
    return Principal(sub=sub, role=role, pseudonym=pseudonym(sub))


_bearer = HTTPBearer(auto_error=False)
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def _principal(creds: HTTPAuthorizationCredentials | None, role: str) -> Principal:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(401, detail={"error": "missing_token"},
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        principal = decode_token(creds.credentials)
    except AuthError as exc:
        raise HTTPException(401, detail={"error": "invalid_token"},
                            headers={"WWW-Authenticate": "Bearer"}) from exc
    if principal.role != role:
        raise HTTPException(403, detail={"error": "forbidden", "required_role": role})
    return principal


def require_merchant(creds: Credentials) -> Principal:
    return _principal(creds, "merchant")


def require_operator(creds: Credentials) -> Principal:
    return _principal(creds, "operator")
