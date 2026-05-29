from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from docuvector.application.auth_use_case import AuthUseCase
from docuvector.domain.entities import User
from docuvector.domain.enums import UserRole
from docuvector.domain.exceptions import AuthenticationError
from docuvector.domain.interfaces.token_service import TokenPayload


@pytest.fixture()
def dependencies() -> dict[str, Mock]:
    return {
        "user_repository": Mock(),
        "password_hasher": Mock(),
        "token_service": Mock(),
        "audit_repository": Mock(),
    }


@pytest.fixture()
def auth_use_case(dependencies: dict[str, Mock]) -> AuthUseCase:
    return AuthUseCase(
        user_repository=dependencies["user_repository"],
        password_hasher=dependencies["password_hasher"],
        token_service=dependencies["token_service"],
        audit_repository=dependencies["audit_repository"],
        token_expire_minutes=60,
    )


@pytest.fixture()
def active_user() -> User:
    user = SimpleNamespace(
        id=1,
        email="admin@test.com",
        password_hash="hashed-password",
        role=UserRole.ADMIN,
        is_active=True,
    )
    return cast(User, user)


@pytest.fixture()
def inactive_user() -> User:
    user = SimpleNamespace(
        id=2,
        email="inactive@test.com",
        password_hash="hashed-password",
        role=UserRole.USER,
        is_active=False,
    )
    return cast(User, user)


def test_login_success(
    auth_use_case: AuthUseCase,
    dependencies: dict[str, Mock],
    active_user: User,
) -> None:
    dependencies["user_repository"].find_by_email.return_value = active_user
    dependencies["password_hasher"].verify.return_value = True
    dependencies["token_service"].issue.return_value = "jwt-token"

    result = auth_use_case.login(
        email="  ADMIN@Test.Com  ",
        plain_password="password123",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )

    dependencies["user_repository"].find_by_email.assert_called_once_with("admin@test.com")
    dependencies["password_hasher"].verify.assert_called_once_with(
        "password123",
        active_user.password_hash,
    )
    dependencies["token_service"].issue.assert_called_once_with(active_user)
    dependencies["audit_repository"].append.assert_called_once()

    assert result.access_token == "jwt-token"
    assert result.token_type == "bearer"
    assert result.expires_in_seconds == 3600
    assert result.user is active_user


def test_login_user_not_found_uses_timing_equalizer_once(
    auth_use_case: AuthUseCase,
    dependencies: dict[str, Mock],
) -> None:
    dependencies["user_repository"].find_by_email.return_value = None
    dependencies["password_hasher"].hash.return_value = "timing-hash"
    dependencies["password_hasher"].verify.return_value = False

    with pytest.raises(AuthenticationError):
        auth_use_case.login(email="missing@test.com", plain_password="password123")

    with pytest.raises(AuthenticationError):
        auth_use_case.login(email="missing@test.com", plain_password="password123")

    assert dependencies["password_hasher"].hash.call_count == 1
    assert dependencies["password_hasher"].verify.call_count == 2
    assert dependencies["token_service"].issue.call_count == 0
    assert dependencies["audit_repository"].append.call_count == 2


def test_login_inactive_user(
    auth_use_case: AuthUseCase,
    dependencies: dict[str, Mock],
    inactive_user: User,
) -> None:
    dependencies["user_repository"].find_by_email.return_value = inactive_user

    with pytest.raises(AuthenticationError):
        auth_use_case.login(email="inactive@test.com", plain_password="password123")

    dependencies["password_hasher"].verify.assert_not_called()
    dependencies["token_service"].issue.assert_not_called()
    dependencies["audit_repository"].append.assert_called_once()


def test_login_wrong_password(
    auth_use_case: AuthUseCase,
    dependencies: dict[str, Mock],
    active_user: User,
) -> None:
    dependencies["user_repository"].find_by_email.return_value = active_user
    dependencies["password_hasher"].verify.return_value = False

    with pytest.raises(AuthenticationError):
        auth_use_case.login(email="admin@test.com", plain_password="wrong-password")

    dependencies["password_hasher"].verify.assert_called_once_with(
        "wrong-password",
        active_user.password_hash,
    )
    dependencies["token_service"].issue.assert_not_called()
    dependencies["audit_repository"].append.assert_called_once()


def test_me_success(
    auth_use_case: AuthUseCase,
    dependencies: dict[str, Mock],
    active_user: User,
) -> None:
    dependencies["user_repository"].find_by_id.return_value = active_user

    payload = cast(
        TokenPayload,
        SimpleNamespace(
            user_id=1,
            email="admin@test.com",
            role="admin",
        ),
    )

    result = auth_use_case.me(payload)

    dependencies["user_repository"].find_by_id.assert_called_once_with(1)
    assert result is active_user


@pytest.mark.parametrize(
    ("returned_user", "expected_calls"),
    [
        (None, 1),
        (
            cast(
                User,
                SimpleNamespace(
                    id=3,
                    email="disabled@test.com",
                    password_hash="hashed-password",
                    role=UserRole.USER,
                    is_active=False,
                ),
            ),
            1,
        ),
    ],
)
def test_me_rejects_invalid_session(
    auth_use_case: AuthUseCase,
    dependencies: dict[str, Mock],
    returned_user: Any,
    expected_calls: int,
) -> None:
    dependencies["user_repository"].find_by_id.return_value = returned_user

    payload = cast(
        TokenPayload,
        SimpleNamespace(
            user_id=99,
            email="invalid@test.com",
            role="user",
        ),
    )

    with pytest.raises(AuthenticationError):
        auth_use_case.me(payload)

    dependencies["user_repository"].find_by_id.assert_called_once_with(99)
