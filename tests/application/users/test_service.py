from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.auth.password import PasswordService
from app.application.users.service import UserOperationError, UserService
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User


def make_user(role: UserRole) -> User:
    return User(
        id=uuid4(),
        full_name="Super Admin",
        role=role,
        email="admin@example.test",
        password_hash="stored-hash",
        access_category=AccessCategory.IV,
        active=True,
    )


def make_service(*, existing=None):
    repository = AsyncMock()
    repository.get_by_email.return_value = existing
    repository.add.side_effect = lambda user: user
    enterprise_repository = AsyncMock()
    enterprise_repository.get_by_id.return_value = SimpleNamespace(id=uuid4())
    return UserService(repository, enterprise_repository, PasswordService()), repository


@pytest.mark.asyncio
async def test_create_hashes_temporary_password_and_requires_change():
    actor = make_user(UserRole.SUPERADMIN)
    service, repository = make_service()

    user = await service.create(
        actor=actor,
        full_name=" New User ",
        email="new@example.test ",
        role=UserRole.ENGINEER,
        enterprise_id=None,
        access_category=AccessCategory.III,
        temporary_password="TemporaryPassword123",
    )

    assert user.full_name == "New User"
    assert user.email == "new@example.test"
    assert user.password_hash != "TemporaryPassword123"
    assert service.password_service.verify(
        "TemporaryPassword123", user.password_hash
    )
    assert user.must_change_password is True
    assert user.created_by == actor.id
    repository.add.assert_awaited_once_with(user)


@pytest.mark.asyncio
async def test_create_rejects_duplicate_email():
    service, _ = make_service(existing=make_user(UserRole.ENGINEER))

    with pytest.raises(UserOperationError, match="уже существует"):
        await service.create(
            actor=make_user(UserRole.SUPERADMIN),
            full_name="User",
            email="admin@example.test",
            role=UserRole.ENGINEER,
            enterprise_id=None,
            access_category=AccessCategory.III,
            temporary_password="TemporaryPassword123",
        )


@pytest.mark.asyncio
async def test_non_superadmin_cannot_create_user():
    service, repository = make_service()

    with pytest.raises(UserOperationError, match="прав"):
        await service.create(
            actor=make_user(UserRole.ADMIN),
            full_name="User",
            email="user@example.test",
            role=UserRole.SUPERADMIN,
            enterprise_id=None,
            access_category=AccessCategory.III,
            temporary_password="TemporaryPassword123",
        )
    repository.add.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("full_name", "email", "password"),
    [
        ("  ", "user@example.test", "TemporaryPassword123"),
        ("User", "not-an-email", "TemporaryPassword123"),
        ("User", "user@example.test", ""),
    ],
)
async def test_create_rejects_invalid_user_data(full_name, email, password):
    service, repository = make_service()

    with pytest.raises(UserOperationError):
        await service.create(
            actor=make_user(UserRole.SUPERADMIN),
            full_name=full_name,
            email=email,
            role=UserRole.ENGINEER,
            enterprise_id=None,
            access_category=AccessCategory.III,
            temporary_password=password,
        )
    repository.add.assert_not_awaited()


@pytest.mark.asyncio
async def test_superadmin_cannot_change_own_role():
    actor = make_user(UserRole.SUPERADMIN)
    service, repository = make_service()
    repository.get_managed_by_id.return_value = actor

    with pytest.raises(UserOperationError, match="собственную"):
        await service.update(
            actor=actor,
            user_id=actor.id,
            full_name=actor.full_name,
            email=actor.email,
            role=UserRole.ENGINEER,
            enterprise_id=None,
            access_category=AccessCategory.I,
        )
    repository.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_superadmin_can_deactivate_and_archive_another_user():
    actor = make_user(UserRole.SUPERADMIN)
    target = make_user(UserRole.ENGINEER)
    service, repository = make_service()
    repository.get_managed_by_id.return_value = target

    await service.set_active(actor=actor, user_id=target.id, active=False)
    assert target.active is False
    await service.archive(actor=actor, user_id=target.id)

    assert target.deleted_at is not None
    assert target.deleted_by == actor.id
    assert target.updated_by == actor.id
    assert repository.flush.await_count == 2


@pytest.mark.asyncio
async def test_ordinary_password_change_requires_current_password():
    password_service = PasswordService()
    user = make_user(UserRole.ENGINEER)
    user.password_hash = password_service.hash("CurrentPassword123")
    service, repository = make_service()
    service.password_service = password_service

    with pytest.raises(UserOperationError, match="Текущий пароль"):
        await service.change_password(
            user=user,
            current_password="wrong-password",
            new_password="NewPassword12345",
        )
    repository.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_temporary_password_change_does_not_require_old_password():
    password_service = PasswordService()
    user = make_user(UserRole.ENGINEER)
    user.password_hash = password_service.hash("TemporaryPassword123")
    user.must_change_password = True
    service, repository = make_service()
    service.password_service = password_service

    await service.change_password(
        user=user,
        current_password=None,
        new_password="PermanentPassword123",
    )

    assert user.must_change_password is False
    assert password_service.verify("PermanentPassword123", user.password_hash)
    repository.flush.assert_awaited_once()
