from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

_bearer = HTTPBearer(auto_error=True)


@dataclass
class CurrentUser:
    sub: str
    username: str


class _JWKSCache:
    def __init__(self) -> None:
        self._keys: dict[str, dict] = {}
        self._fetched_at: float = 0.0
        self._ttl: float = 300.0
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def _fetch(self) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(settings.keycloak_jwks_url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
        self._keys = {k["kid"]: k for k in data.get("keys", [])}
        self._fetched_at = time.monotonic()

    async def get_keys(self) -> dict[str, dict]:
        if self._keys and (time.monotonic() - self._fetched_at) < self._ttl:
            return self._keys
        async with self._get_lock():
            if self._keys and (time.monotonic() - self._fetched_at) < self._ttl:
                return self._keys
            await self._fetch()
        return self._keys

    async def get_key(self, kid: str) -> dict | None:
        keys = await self.get_keys()
        if kid not in keys:
            # Force-refresh on key-not-found to handle key rotation.
            async with self._get_lock():
                self._fetched_at = 0.0
            keys = await self.get_keys()
        return keys.get(kid)


_cache = _JWKSCache()


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> CurrentUser:
    token = creds.credentials
    try:
        headers = jwt.get_unverified_headers(token)
        key = await _cache.get_key(headers.get("kid", ""))
        if key is None:
            raise JWTError("unknown key id")
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.keycloak_issuer,
            options={"verify_aud": False},
        )
        aud = payload.get("aud", [])
        if isinstance(aud, str):
            aud = [aud]
        azp = payload.get("azp", "")
        if settings.keycloak_client_id not in aud and azp != settings.keycloak_client_id:
            raise JWTError("client_id mismatch")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentUser(
        sub=payload.get("sub", ""),
        username=payload.get("preferred_username", payload.get("sub", "")),
    )
