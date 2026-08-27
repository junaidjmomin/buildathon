from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant_id: str
    roles: frozenset[str]
    auth_mode: str


@lru_cache(maxsize=4)
def _jwk_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=300, timeout=5)


def _roles(value: Any) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset(role.strip().lower() for role in value.split() if role.strip())
    if isinstance(value, list):
        return frozenset(str(role).strip().lower() for role in value if str(role).strip())
    return frozenset()


def authenticate(
    credentials: HTTPAuthorizationCredentials | None,
    settings: Settings,
) -> Principal:
    if settings.auth_mode == "disabled":
        if settings.environment == "production":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Principal(
            subject="local-demo-user",
            tenant_id="novacart_demo",
            roles=frozenset({"viewer", "analyst", "approver", "admin"}),
            auth_mode="disabled",
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        signing_key = _jwk_client(settings.oidc_jwks_url).get_signing_key_from_jwt(
            credentials.credentials
        )
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    tenant_id = str(claims.get(settings.oidc_tenant_claim, "")).strip()
    roles = _roles(claims.get(settings.oidc_roles_claim))
    subject = str(claims.get("sub", "")).strip()
    if (
        not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", tenant_id)
        or not re.fullmatch(r"[A-Za-z0-9._:@+|-]{1,160}", subject)
        or not roles
        or len(roles) > 32
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token has invalid tenant, subject, or role claims",
        )
    return Principal(
        subject=subject,
        tenant_id=tenant_id,
        roles=roles,
        auth_mode="oidc",
    )


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    return authenticate(credentials, get_settings())


def require_roles(*allowed_roles: str):
    allowed = frozenset(role.lower() for role in allowed_roles)

    def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if "admin" not in principal.roles and principal.roles.isdisjoint(allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action is not permitted for the current role",
            )
        return principal

    return dependency
