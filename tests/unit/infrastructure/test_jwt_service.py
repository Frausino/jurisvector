"""Testes unitários do `JwtTokenService`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from docuvector.domain.entities import User
from docuvector.domain.enums import UserRole
from docuvector.domain.exceptions import AuthenticationError
from docuvector.infrastructure.security.jwt_service import JwtTokenService

_TEST_SECRET = (
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"  # pragma: allowlist secret
)

_OTHER_SECRET = (
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"  # pragma: allowlist secret
)


@pytest.fixture
def jwt_service() -> JwtTokenService:
    """Serviço JWT com segredo fixo de 64 chars (atende mínimo de 32)."""
    return JwtTokenService(secret_key=_TEST_SECRET, access_token_expire_minutes=60)


@pytest.fixture
def sample_user() -> User:
    """Usuário de teste com role=user."""
    return User(
        email="advogado@docuvector.local",
        password_hash="$2b$04$fake_hash_unit_test_only",
        role=UserRole.USER,
    )


@pytest.mark.unit
def test_issued_token_round_trips_with_correct_claims(
    jwt_service: JwtTokenService,
    sample_user: User,
) -> None:
    """Token emitido deve verificar e retornar os mesmos claims essenciais."""
    raw_token = jwt_service.issue(sample_user)

    payload = jwt_service.verify(raw_token)

    assert payload.user_id == sample_user.id
    assert payload.email == sample_user.email
    assert payload.role is UserRole.USER
    assert payload.expires_at > datetime.now(UTC)


@pytest.mark.unit
def test_secret_below_minimum_length_is_rejected_on_construction() -> None:
    """Segredo curto deve falhar antes de qualquer uso (fail-fast)."""
    with pytest.raises(ValueError, match="32"):
        JwtTokenService(secret_key="muito-curto")  # pragma: allowlist secret


@pytest.mark.unit
def test_tampered_token_raises_authentication_error(
    jwt_service: JwtTokenService,
    sample_user: User,
) -> None:
    """Modificação de qualquer caractere do token quebra a assinatura."""
    valid_token = jwt_service.issue(sample_user)
    tampered_token = valid_token[:-2] + "AA"

    with pytest.raises(AuthenticationError):
        jwt_service.verify(tampered_token)


@pytest.mark.unit
def test_token_signed_with_other_secret_is_rejected(sample_user: User) -> None:
    """Token assinado com outra chave HMAC NÃO deve verificar."""
    foreign_issuer = JwtTokenService(secret_key=_OTHER_SECRET)
    local_verifier = JwtTokenService(secret_key=_TEST_SECRET)

    foreign_token = foreign_issuer.issue(sample_user)

    with pytest.raises(AuthenticationError):
        local_verifier.verify(foreign_token)


@pytest.mark.unit
def test_expired_token_is_rejected(sample_user: User) -> None:
    """Token expirado (exp no passado) é rejeitado pelo decoder."""
    expired_claims = {
        "sub": str(sample_user.id),
        "email": sample_user.email,
        "role": sample_user.role.value,
        "iat": int((datetime.now(UTC) - timedelta(hours=2)).timestamp()),
        "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
    }
    expired_token = jwt.encode(expired_claims, _TEST_SECRET, algorithm="HS256")

    verifier = JwtTokenService(secret_key=_TEST_SECRET)
    with pytest.raises(AuthenticationError):
        verifier.verify(expired_token)


@pytest.mark.unit
def test_token_missing_required_claim_is_rejected(jwt_service: JwtTokenService) -> None:
    """Token estruturalmente válido mas sem claim 'sub' é rejeitado."""
    incomplete_claims = {
        "email": "x@y.local",
        "role": "user",
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
    }
    malformed_token = jwt.encode(incomplete_claims, _TEST_SECRET, algorithm="HS256")

    with pytest.raises(AuthenticationError):
        jwt_service.verify(malformed_token)
