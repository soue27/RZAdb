import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy.sql import Select

from app.application.users.bootstrap import (
    SYSTEM_EMAIL,
    SYSTEM_ID,
    BootstrapCredentials,
    BootstrapError,
    bootstrap_superadmin,
)
from app.domain.enums import AccessCategory, UserRole
from app.domain.user import User


def make_system_user(**overrides) -> User:
    values = {
        "id": SYSTEM_ID,
        "full_name": "SYSTEM",
        "role": UserRole.SUPERADMIN,
        "email": SYSTEM_EMAIL,
        "password_hash": "unchanged-system-hash",
        "enterprise_id": None,
        "access_category": AccessCategory.IV,
        "active": False,
        "must_change_password": False,
        "deleted_at": None,
        "created_by": SYSTEM_ID,
        "updated_by": SYSTEM_ID,
    }
    values.update(overrides)
    return User(**values)


class FakeTransaction:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.in_transaction = True

    async def __aexit__(self, exc_type, exc, traceback):
        self.session.in_transaction = False
        if exc_type is None:
            self.session.committed = True
            if self.session.pending_user is not None:
                self.session.shared_users.append(self.session.pending_user)
        else:
            self.session.rolled_back = True
            self.session.pending_user = None
        if self.session.lock is not None:
            self.session.lock.release()


class FakeSession:
    def __init__(self, *, system_user=None, shared_users=None, lock=None):
        self.system_user = system_user or make_system_user()
        self.shared_users = shared_users if shared_users is not None else []
        self.lock = lock
        self.scalar_calls = 0
        self.pending_user = None
        self.committed = False
        self.rolled_back = False
        self.in_transaction = False
        self.lock_statement = None
        self.fail_flush = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return FakeTransaction(self)

    async def execute(self, statement, params):
        self.lock_statement = str(statement)
        if self.lock is not None:
            await self.lock.acquire()

    async def get(self, model, identity):
        assert model is User
        assert identity == SYSTEM_ID
        return self.system_user

    async def scalar(self, statement):
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            assert isinstance(statement, Select)
            return self.system_user
        if self.scalar_calls == 2:
            existing = next(iter(self.shared_users), None)
            return existing.id if existing is not None else None
        assert self.scalar_calls == 3
        return None

    def add(self, user):
        self.pending_user = user

    async def flush(self):
        if self.fail_flush:
            raise RuntimeError("simulated database error")
        if self.pending_user is not None and self.pending_user.id is None:
            self.pending_user.id = uuid4()


def credentials(**overrides):
    values = {
        "full_name": "Иванов Иван Иванович",
        "email": "ivanov@example.test",
        "password": "temporary-password-12",
        "password_confirmation": "temporary-password-12",
    }
    values.update(overrides)
    return BootstrapCredentials(**values)


@pytest.mark.asyncio
async def test_creates_first_superadmin_with_audit_fields_and_preserves_system():
    system = make_system_user()
    original_system_values = (
        system.password_hash,
        system.active,
        system.created_by,
        system.updated_by,
    )
    session = FakeSession(system_user=system)

    user = await bootstrap_superadmin(session, lambda: credentials())

    assert user.role is UserRole.SUPERADMIN
    assert user.active is True
    assert user.must_change_password is True
    assert user.deleted_at is None
    assert user.enterprise_id is None
    assert user.access_category is AccessCategory.IV
    assert user.created_by == SYSTEM_ID
    assert user.updated_by == SYSTEM_ID
    assert user.password_hash != "temporary-password-12"
    assert session.committed is True
    assert session.lock_statement and "pg_advisory_xact_lock" in session.lock_statement
    assert (
        system.password_hash,
        system.active,
        system.created_by,
        system.updated_by,
    ) == original_system_values


@pytest.mark.parametrize("existing_active", [True, False])
@pytest.mark.parametrize("archived", [True, False])
@pytest.mark.asyncio
async def test_existing_superadmin_blocks_bootstrap_regardless_of_state(
    existing_active, archived
):
    existing = make_system_user(
        id=UUID("00000000-0000-7000-8000-000000000002"),
        email="existing@example.test",
        active=existing_active,
        deleted_at=object() if archived else None,
    )
    session = FakeSession(shared_users=[existing])

    with pytest.raises(BootstrapError, match="уже есть реальный SUPERADMIN"):
        await bootstrap_superadmin(session, lambda: pytest.fail("must not prompt"))

    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_missing_system_blocks_bootstrap_before_prompting():
    session = FakeSession(system_user=None)
    session.system_user = None

    with pytest.raises(BootstrapError, match="SYSTEM отсутствует"):
        await bootstrap_superadmin(session, lambda: pytest.fail("must not prompt"))


@pytest.mark.parametrize(
    "system_overrides",
    [
        {"active": True},
        {"email": "wrong@example.test"},
        {"role": UserRole.ADMIN},
        {"access_category": AccessCategory.I},
    ],
)
@pytest.mark.asyncio
async def test_unexpected_system_properties_block_bootstrap(system_overrides):
    session = FakeSession(system_user=make_system_user(**system_overrides))

    with pytest.raises(BootstrapError, match="SYSTEM отсутствует или имеет неверные"):
        await bootstrap_superadmin(session, lambda: pytest.fail("must not prompt"))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"password_confirmation": "different-password"},
            "пароли не совпадают",
        ),
        ({"email": "not-an-email"}, "корректный Email"),
        ({"password": "short", "password_confirmation": "short"}, "12 символов"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_credentials_are_rejected(overrides, message):
    session = FakeSession()
    supplied = credentials(**overrides)

    with pytest.raises(BootstrapError, match=message):
        await bootstrap_superadmin(session, lambda: supplied)

    assert supplied.password not in message
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_creation_failure_rolls_back():
    session = FakeSession()
    session.fail_flush = True

    with pytest.raises(RuntimeError, match="simulated database error"):
        await bootstrap_superadmin(session, lambda: credentials())

    assert session.rolled_back is True
    assert session.pending_user is None


@pytest.mark.asyncio
async def test_parallel_bootstraps_serialize_and_create_only_one_superadmin():
    lock = asyncio.Lock()
    shared_users = []
    first = FakeSession(shared_users=shared_users, lock=lock)
    second = FakeSession(shared_users=shared_users, lock=lock)
    outcomes = await asyncio.gather(
        bootstrap_superadmin(first, lambda: credentials()),
        bootstrap_superadmin(
            second,
            lambda: credentials(email="second@example.test"),
        ),
        return_exceptions=True,
    )

    assert sum(isinstance(result, User) for result in outcomes) == 1
    assert sum(isinstance(result, BootstrapError) for result in outcomes) == 1
    assert len(shared_users) == 1


def test_database_display_does_not_include_credentials():
    from app.infrastructure.bootstrap.__main__ import _target_database_display

    database, display = _target_database_display(
        "postgresql+asyncpg://operator:secret@db.internal:5432/production"
    )

    assert database == "production"
    assert display == "db.internal:5432/production"
    assert "operator" not in display
    assert "secret" not in display


def test_unconfirmed_target_database_stops_before_opening_a_session(monkeypatch, capsys):
    from types import SimpleNamespace

    import app.infrastructure.bootstrap.__main__ as cli

    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql+asyncpg://operator:secret@db.internal/production"
        ),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "rzadb")
    monkeypatch.setattr(
        cli,
        "_run",
        lambda: pytest.fail("database session must not be opened"),
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    output = capsys.readouterr()
    assert error.value.code == 1
    assert "не подтверждено" in output.out
    assert "secret" not in output.out
    assert output.err == ""


def test_cli_never_prints_or_logs_temporary_password(monkeypatch, capsys, caplog):
    from types import SimpleNamespace

    import app.infrastructure.bootstrap.__main__ as cli

    secret = "unique-temporary-password-42"
    session = FakeSession()
    supplied = credentials(password=secret, password_confirmation=secret)
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql+asyncpg://operator:db-secret@db.internal/production"
        ),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "production")
    monkeypatch.setattr(cli, "_request_credentials", lambda: supplied)
    monkeypatch.setattr(cli, "async_session_factory", lambda: session)

    async def dispose_engine():
        return None

    monkeypatch.setattr(cli, "engine", SimpleNamespace(dispose=dispose_engine))
    cli.main()

    output = capsys.readouterr()
    assert secret not in output.out
    assert secret not in output.err
    assert secret not in caplog.text
    assert "db-secret" not in output.out
