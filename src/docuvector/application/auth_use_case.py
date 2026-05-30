"""Caso de uso de autenticação.

Orquestra a verificação de credenciais, a emissão do token JWT e
o registro de auditoria. Não conhece HTTP, banco ou JWT diretamente:
trabalha através das interfaces do domínio.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from docuvector.domain.entities import AuditEvent, User
from docuvector.domain.enums import AuditAction, AuditStatus
from docuvector.domain.exceptions import AuthenticationError
from docuvector.domain.interfaces.audit_repository import AuditRepository
from docuvector.domain.interfaces.password_hasher import PasswordHasher
from docuvector.domain.interfaces.token_service import TokenPayload, TokenService
from docuvector.domain.interfaces.user_repository import UserRepository

_GENERIC_AUTH_ERROR_MESSAGE = "Credenciais inválidas."
OAUTH2_BEARER_TOKEN_TYPE = "bearer"  # noqa: S105  # nosec B105 - valor público OAuth2.


@dataclass(frozen=True, slots=True)
class LoginResult:
    """Saída do caso de uso de login.

    `access_token` é o JWT serializado. `user` é a entidade autenticada,
    útil para o router montar a resposta sem segunda consulta ao banco.
    """

    access_token: str
    token_type: str
    expires_in_seconds: int
    user: User


class AuthUseCase:
    """Login (verificar credenciais + emitir token) e introspecção do usuário atual.

    Cada login emite evento de auditoria (sucesso OU falha). Tentativas
    com email inexistente também são registradas, para correlação posterior
    no painel administrativo.
    """

    def __init__(
        self,
        user_repository: UserRepository,
        password_hasher: PasswordHasher,
        token_service: TokenService,
        audit_repository: AuditRepository,
        token_expire_minutes: int,
    ) -> None:
        self._user_repository = user_repository
        self._password_hasher = password_hasher
        self._token_service = token_service
        self._audit_repository = audit_repository
        self._token_expire_minutes = token_expire_minutes
        # Hash bcrypt válido pré-computado lazy para igualar timing
        # do caminho de login com email inexistente vs. existente.
        # Inicializado sob demanda no primeiro acesso.
        self._timing_equalizer_hash: str | None = None

    def login(
        self,
        email: str,
        plain_password: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> LoginResult:
        """Autentica credenciais e devolve token JWT.

        Comportamento anti-enumeration:
        - Email inexistente E senha errada produzem a mesma mensagem.
        - Tempo de execução é equilibrado: mesmo quando o email não existe,
          executamos uma verificação dummy para evitar canal lateral
          de timing.
        """
        normalized_email = email.lower().strip()
        user = self._user_repository.find_by_email(normalized_email)

        if user is None:
            self._equalize_timing_against_enumeration(plain_password)
            self._record_failed_login(
                attempted_email=normalized_email,
                user_id=None,
                client_ip=client_ip,
                user_agent=user_agent,
                reason="user_not_found",
            )
            raise AuthenticationError(_GENERIC_AUTH_ERROR_MESSAGE)

        if not user.is_active:
            self._record_failed_login(
                attempted_email=normalized_email,
                user_id=user.id,
                client_ip=client_ip,
                user_agent=user_agent,
                reason="user_inactive",
            )
            raise AuthenticationError(_GENERIC_AUTH_ERROR_MESSAGE)

        if not self._password_hasher.verify(plain_password, user.password_hash):
            self._record_failed_login(
                attempted_email=normalized_email,
                user_id=user.id,
                client_ip=client_ip,
                user_agent=user_agent,
                reason="wrong_password",
            )
            raise AuthenticationError(_GENERIC_AUTH_ERROR_MESSAGE)

        access_token = self._token_service.issue(user)
        self._record_successful_login(
            user=user,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        return LoginResult(
            access_token=access_token,
            token_type=OAUTH2_BEARER_TOKEN_TYPE,
            expires_in_seconds=self._token_expire_minutes * 60,
            user=user,
        )

    def me(self, token_payload: TokenPayload) -> User:
        """Recupera o usuário autenticado a partir do payload do token.

        Levanta `AuthenticationError` se o usuário foi removido ou
        desativado após a emissão do token.
        """
        user = self._user_repository.find_by_id(token_payload.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Sessão inválida.")
        return user

    def _equalize_timing_against_enumeration(self, candidate_password: str) -> None:
        """Executa verify contra hash bcrypt VÁLIDO para igualar o custo.

        Atenção: usar hash com formato bcrypt mas conteúdo malformado
        (ex.: `"$2b$12$" + "x" * 53`) causa travamento em algumas combinações
        de bcrypt + Python no Windows (a lib trava decodificando base64 inválido).
        Por isso geramos um hash REAL de uma senha aleatória descartável,
        cacheado no primeiro acesso.
        """
        if self._timing_equalizer_hash is None:
            self._timing_equalizer_hash = self._password_hasher.hash(secrets.token_hex(16))
        self._password_hasher.verify(candidate_password, self._timing_equalizer_hash)

    def _record_successful_login(
        self,
        user: User,
        client_ip: str | None,
        user_agent: str | None,
    ) -> None:
        self._audit_repository.append(
            AuditEvent(
                action=AuditAction.LOGIN_SUCCESS,
                status=AuditStatus.SUCCESS,
                resource_type="user",
                actor_user_id=user.id,
                actor_email=user.email,
                actor_role=user.role,
                resource_id=user.id,
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={"email": user.email},
            ),
        )

    def _record_failed_login(
        self,
        attempted_email: str,
        user_id: object,
        client_ip: str | None,
        user_agent: str | None,
        reason: str,
    ) -> None:
        self._audit_repository.append(
            AuditEvent(
                action=AuditAction.LOGIN_FAILED,
                status=AuditStatus.FAILURE,
                resource_type="user",
                actor_user_id=user_id,  # type: ignore[arg-type]
                ip_address=client_ip,
                user_agent=user_agent,
                metadata={"attempted_email": attempted_email, "reason": reason},
            ),
        )
