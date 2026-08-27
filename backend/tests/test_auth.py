from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.config import Settings
from app.security import auth


class _SigningKey:
    key = object()


class _JwkClient:
    def get_signing_key_from_jwt(self, _token: str) -> _SigningKey:
        return _SigningKey()


def _settings() -> Settings:
    return Settings(
        AUTH_MODE="oidc",
        OIDC_ISSUER="https://tenant.example/",
        OIDC_AUDIENCE="https://api.sl3dge.local",
        OIDC_JWKS_URL="https://tenant.example/.well-known/jwks.json",
        OIDC_TENANT_CLAIM="https://sl3dge.app/merchant_id",
        OIDC_ROLES_CLAIM="https://sl3dge.app/roles",
    )


def test_auth0_subject_and_namespaced_claims_are_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "_jwk_client", lambda _url: _JwkClient())
    monkeypatch.setattr(
        auth.jwt,
        "decode",
        lambda *_args, **_kwargs: {
            "sub": "auth0|6a905f5d814220953a6999a7",
            "https://sl3dge.app/merchant_id": "novacart_demo",
            "https://sl3dge.app/roles": ["admin"],
        },
    )

    principal = auth.authenticate(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="signed-token"),
        _settings(),
    )

    assert principal.subject == "auth0|6a905f5d814220953a6999a7"
    assert principal.tenant_id == "novacart_demo"
    assert principal.roles == frozenset({"admin"})


def test_oidc_token_without_roles_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "_jwk_client", lambda _url: _JwkClient())
    monkeypatch.setattr(
        auth.jwt,
        "decode",
        lambda *_args, **_kwargs: {
            "sub": "auth0|6a905f5d814220953a6999a7",
            "https://sl3dge.app/merchant_id": "novacart_demo",
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.authenticate(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="signed-token"),
            _settings(),
        )

    assert exc_info.value.status_code == 403
