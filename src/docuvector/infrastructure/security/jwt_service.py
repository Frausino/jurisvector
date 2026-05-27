"""Implementação de emissão e verificação de JWT com HS256.

Decisão: HMAC SHA-256 com segredo de 32+ bytes (validado em Settings)
é adequado para autenticação intra-aplicação. RS256 seria necessário
se houvesse múltiplos serviços validando o token sem compartilhar
segredo, o que não é o caso da v1.0.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt

from docuvector.domain.entities import User
from docuvector.domain.enums import UserRole
from docuvector.domain.exceptions import AuthenticationError
from docuvector.domain.interfaces.token_service import TokenPayload

MIN_JWT_SECRET_LENGTH = 32


class JwtTokenService:
    """Emissão e verificação de tokens JWT.

    Satisfaz estruturalmente `domain.interfaces.TokenService`.
    Claims customizadas: `sub` (user_id), `email`, `role`, `exp`, `iat`.
    """

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60,
    ) -> None:
        if len(secret_key) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                f"JWT secret precisa ter no mínimo {MIN_JWT_SECRET_LENGTH} caracteres."
            )
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._expire_minutes = access_token_expire_minutes

    def issue(self, user: User) -> str:
        """Gera token assinado representando a sessão do usuário."""
        issued_at = datetime.now(UTC)
        expires_at = issued_at + timedelta(minutes=self._expire_minutes)
        claims: dict[str, Any] = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value,
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return jwt.encode(claims, self._secret_key, algorithm=self._algorithm)

    def verify(self, raw_token: str) -> TokenPayload:
        """Valida o token e retorna os claims.

        Levanta `AuthenticationError` para qualquer falha:
        token inválido, expirado, adulterado, assinatura quebrada,
        ou claim obrigatória ausente. Mensagem sempre genérica.
        """
        try:
            claims = jwt.decode(
                raw_token,
                self._secret_key,
                algorithms=[self._algorithm],
            )
        except JWTError as decode_error:
            raise AuthenticationError("Token inválido ou expirado.") from decode_error

        try:
            return TokenPayload(
                user_id=UUID(claims["sub"]),
                email=claims["email"],
                role=UserRole(claims["role"]),
                expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
            )
        except (KeyError, ValueError) as malformed_claim_error:
            raise AuthenticationError("Token com claims malformadas.") from malformed_claim_error
