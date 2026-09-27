"""add universal audit fields

Revision ID: a74c1d8f2b90
Revises: 9cabe5e81fe3
Create Date: 2026-09-27
"""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision: str = "a74c1d8f2b90"
down_revision: str | Sequence[str] | None = "9cabe5e81fe3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Fixed identity prevents repeated upgrades from creating different SYSTEM users.
SYSTEM_ID = UUID("00000000-0000-7000-8000-000000000001")
SYSTEM_EMAIL = "system@rzadb.local"
SYSTEM_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "f3UFgbgncQAt7ov7TH1SuA$"
    "rJS1aGwj0n4n65Usqz/Y0xjxBWVaHTAy76vo9fJuEbo"
)

AUDIT_TABLES = (
    "users",
    "enterprises",
    "substations",
    "connections",
    "urzas",
    "otds",
    "otd_versions",
    "settings_forms",
    "settings_records",
    "schema_forms",
    "schema_records",
    "urza_instructions",
    "urza_instruction_versions",
    "rza_instructions",
    "rza_instruction_versions",
    "selectivity_schemes",
    "selectivity_scheme_versions",
    "programs",
    "files",
    "tasks",
    "inspection_tasks",
    "inspections",
    "to_records",
)

CREATED_BY_ALREADY_EXISTS = (
    "tasks",
    "inspection_tasks",
    "inspections",
    "to_records",
    "settings_records",
    "schema_records",
    "urza_instruction_versions",
    "rza_instruction_versions",
    "selectivity_scheme_versions",
)
CREATED_BY_TO_ADD = tuple(
    table for table in AUDIT_TABLES if table not in CREATED_BY_ALREADY_EXISTS
)

CREATED_AT_TO_ADD = (
    "schema_forms",
    "schema_records",
    "urza_instructions",
    "rza_instructions",
    "selectivity_schemes",
)
UPDATED_AT_TO_ADD = (
    "settings_records",
    "schema_forms",
    "schema_records",
    "urza_instructions",
    "urza_instruction_versions",
    "rza_instructions",
    "rza_instruction_versions",
    "selectivity_schemes",
    "selectivity_scheme_versions",
)
DELETED_FIELDS_TO_ADD = (
    "settings_records",
    "schema_forms",
    "schema_records",
    "urza_instructions",
    "urza_instruction_versions",
    "rza_instructions",
    "rza_instruction_versions",
    "selectivity_schemes",
    "selectivity_scheme_versions",
    "inspections",
)


def _assert_empty_tables(connection: sa.Connection, tables: Sequence[str]) -> None:
    for table in tables:
        count = connection.scalar(sa.text(f'SELECT count(*) FROM "{table}"'))
        if count:
            raise RuntimeError(
                f"Cannot add audit timestamps: {table} contains {count} rows; "
                "historical timestamps must not be fabricated."
            )


def _assert_system_identity_available(connection: sa.Connection) -> None:
    existing = connection.execute(
        sa.text(
            "SELECT id, email FROM users "
            "WHERE id = :system_id OR email = :system_email"
        ),
        {"system_id": SYSTEM_ID, "system_email": SYSTEM_EMAIL},
    ).all()
    if existing:
        raise RuntimeError(
            "SYSTEM migration identity or email already exists; refusing to "
            "reuse or overwrite an existing user."
        )


def _assert_no_unexpected_deleted_by_orphans(connection: sa.Connection) -> None:
    for table in AUDIT_TABLES:
        if table == "files":
            continue
        if table in DELETED_FIELDS_TO_ADD:
            continue
        count = connection.scalar(
            sa.text(
                f'SELECT count(*) FROM "{table}" AS t '
                "WHERE t.deleted_by IS NOT NULL AND NOT EXISTS "
                "(SELECT 1 FROM users AS u WHERE u.id = t.deleted_by)"
            )
        )
        if count:
            raise RuntimeError(
                f"{table}.deleted_by contains {count} orphan UUID(s); "
                "migration only authorizes cleanup of files.deleted_by."
            )


def _assert_audit_references_valid(connection: sa.Connection) -> None:
    for table in AUDIT_TABLES:
        for column in ("created_by", "updated_by", "deleted_by"):
            nullable = column == "deleted_by"
            where = f't."{column}" IS NULL' if not nullable else "FALSE"
            null_count = connection.scalar(
                sa.text(f'SELECT count(*) FROM "{table}" AS t WHERE {where}')
            )
            if null_count:
                raise RuntimeError(
                    f"{table}.{column} contains NULL values before its FK is added."
                )
            orphan_count = connection.scalar(
                sa.text(
                    f'SELECT count(*) FROM "{table}" AS t '
                    f'WHERE t."{column}" IS NOT NULL AND NOT EXISTS '
                    "(SELECT 1 FROM users AS u WHERE u.id = "
                    f't."{column}")'
                )
            )
            if orphan_count:
                raise RuntimeError(
                    f"{table}.{column} contains {orphan_count} orphan UUID(s)."
                )


def upgrade() -> None:
    connection = op.get_bind()

    # Hold write-blocking locks for the audited tables so the emptiness check
    # and nullable-to-NOT-NULL backfill cannot race with concurrent inserts.
    for table in sorted(AUDIT_TABLES):
        connection.execute(
            sa.text(f'LOCK TABLE "{table}" IN SHARE ROW EXCLUSIVE MODE')
        )

    # Timestamp columns can only be introduced without historical values for
    # empty tables. Fail before changing anything if that factual premise changed.
    _assert_empty_tables(
        connection,
        tuple(dict.fromkeys((*CREATED_AT_TO_ADD, *UPDATED_AT_TO_ADD))),
    )
    _assert_system_identity_available(connection)
    _assert_no_unexpected_deleted_by_orphans(connection)

    for table in CREATED_BY_TO_ADD:
        op.add_column(
            table,
            sa.Column("created_by", sa.Uuid(), nullable=True),
        )

    for table in AUDIT_TABLES:
        op.add_column(
            table,
            sa.Column("updated_by", sa.Uuid(), nullable=True),
        )

    for table in DELETED_FIELDS_TO_ADD:
        op.add_column(
            table,
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("deleted_by", sa.Uuid(), nullable=True),
        )

    for table in CREATED_AT_TO_ADD:
        op.add_column(
            table,
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    for table in UPDATED_AT_TO_ADD:
        op.add_column(
            table,
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    # Bootstrap with nullable self-reference columns. Required User fields and
    # the project's PostgreSQL enum values are taken from the current model.
    connection.execute(
        sa.text(
            "INSERT INTO users (id, full_name, role, email, password_hash, "
            "enterprise_id, access_category, sap_code, active, created_by, "
            "updated_by) VALUES (:id, 'SYSTEM', 'superadmin', :email, :password, "
            "NULL, 'IV', NULL, FALSE, NULL, NULL)"
        ),
        {
            "id": SYSTEM_ID,
            "email": SYSTEM_EMAIL,
            "password": SYSTEM_PASSWORD_HASH,
        },
    )
    connection.execute(
        sa.text(
            "UPDATE users SET created_by = :id, updated_by = :id WHERE id = :id"
        ),
        {"id": SYSTEM_ID},
    )

    for table in AUDIT_TABLES:
        connection.execute(
            sa.text(
                f'UPDATE "{table}" SET created_by = :system_id '
                "WHERE created_by IS NULL"
            ),
            {"system_id": SYSTEM_ID},
        )
        connection.execute(
            sa.text(
                f'UPDATE "{table}" SET updated_by = :system_id '
                "WHERE updated_by IS NULL"
            ),
            {"system_id": SYSTEM_ID},
        )

    # The 37 observed values are orphan UUIDs. Clear any orphan in this column;
    # leave files.deleted_at untouched.
    connection.execute(
        sa.text(
            "UPDATE files AS f SET deleted_by = NULL "
            "WHERE f.deleted_by IS NOT NULL AND NOT EXISTS "
            "(SELECT 1 FROM users AS u WHERE u.id = f.deleted_by)"
        )
    )

    # Existing created_by FKs are retained; add the missing created_by FKs and
    # all updated_by/deleted_by FKs. No audit FK uses ON DELETE CASCADE.
    for table in CREATED_BY_TO_ADD:
        op.create_foreign_key(
            f"fk_{table}_created_by_users_id",
            table,
            "users",
            ["created_by"],
            ["id"],
        )
    for table in AUDIT_TABLES:
        op.create_foreign_key(
            f"fk_{table}_updated_by_users_id",
            table,
            "users",
            ["updated_by"],
            ["id"],
        )
        op.create_foreign_key(
            f"fk_{table}_deleted_by_users_id",
            table,
            "users",
            ["deleted_by"],
            ["id"],
        )

    _assert_audit_references_valid(connection)

    for table in AUDIT_TABLES:
        op.alter_column(table, "created_by", nullable=False)
        op.alter_column(table, "updated_by", nullable=False)


def _system_references(connection: sa.Connection) -> list[tuple[str, str]]:
    rows = connection.execute(
        sa.text(
            "SELECT DISTINCT kcu.table_name, kcu.column_name "
            "FROM information_schema.key_column_usage AS kcu "
            "JOIN information_schema.constraint_column_usage AS ccu "
            "ON ccu.constraint_catalog = kcu.constraint_catalog "
            "AND ccu.constraint_schema = kcu.constraint_schema "
            "AND ccu.constraint_name = kcu.constraint_name "
            "JOIN information_schema.table_constraints AS tc "
            "ON tc.constraint_catalog = kcu.constraint_catalog "
            "AND tc.constraint_schema = kcu.constraint_schema "
            "AND tc.constraint_name = kcu.constraint_name "
            "WHERE ccu.table_schema = current_schema() "
            "AND ccu.table_name = 'users' AND ccu.column_name = 'id' "
            "AND tc.constraint_type = 'FOREIGN KEY'"
        )
    ).all()
    preparer = connection.dialect.identifier_preparer
    references: list[tuple[str, str]] = []
    for table, column in rows:
        table_sql = preparer.quote(table)
        column_sql = preparer.quote(column)
        found = connection.scalar(
            sa.text(
                f"SELECT EXISTS (SELECT 1 FROM {table_sql} "
                f"WHERE {column_sql} = :system_id)"
            ),
            {"system_id": SYSTEM_ID},
        )
        if found:
            references.append((table, column))
    return references


def _retained_system_references(connection: sa.Connection) -> list[tuple[str, str]]:
    # These pre-existing columns are not removed by downgrade. Check them
    # explicitly because their constraints may also be migration-owned or absent.
    retained_columns = {
        **{table: ("created_by",) for table in CREATED_BY_ALREADY_EXISTS},
        "users": ("deleted_by",),
        "enterprises": ("deleted_by",),
        "substations": ("deleted_by",),
        "connections": ("deleted_by",),
        "urzas": ("deleted_by",),
        "otds": ("deleted_by",),
        "otd_versions": ("deleted_by",),
        "settings_forms": ("deleted_by",),
        "files": ("deleted_by",),
        "tasks": ("deleted_by",),
        "inspection_tasks": ("deleted_by",),
        "to_records": ("deleted_by",),
        "programs": ("deleted_by",),
    }
    preparer = connection.dialect.identifier_preparer
    references: list[tuple[str, str]] = []
    for table, columns in retained_columns.items():
        table_sql = preparer.quote(table)
        for column in columns:
            column_sql = preparer.quote(column)
            found = connection.scalar(
                sa.text(
                    f"SELECT EXISTS (SELECT 1 FROM {table_sql} "
                    f"WHERE {column_sql} = :system_id)"
                ),
                {"system_id": SYSTEM_ID},
            )
            if found:
                references.append((table, column))
    return references


def downgrade() -> None:
    # Check every reference before executing any DDL. This includes audit
    # columns removed below and pre-existing columns retained by downgrade.
    connection = op.get_bind()
    references = [
        *_system_references(connection),
        *_retained_system_references(connection),
    ]
    if references:
        formatted = ", ".join(f"{table}.{column}" for table, column in references)
        raise RuntimeError(
            "Refusing to downgrade: SYSTEM is referenced by: " + formatted
        )

    # Remove only constraints introduced by this revision.
    for table in reversed(AUDIT_TABLES):
        op.drop_constraint(
            f"fk_{table}_deleted_by_users_id", table, type_="foreignkey"
        )
        op.drop_constraint(
            f"fk_{table}_updated_by_users_id", table, type_="foreignkey"
        )
    for table in reversed(CREATED_BY_TO_ADD):
        op.drop_constraint(
            f"fk_{table}_created_by_users_id", table, type_="foreignkey"
        )

    for table in reversed(AUDIT_TABLES):
        op.drop_column(table, "updated_by")
    for table in reversed(DELETED_FIELDS_TO_ADD):
        op.drop_column(table, "deleted_by")
        op.drop_column(table, "deleted_at")
    for table in reversed(UPDATED_AT_TO_ADD):
        op.drop_column(table, "updated_at")
    for table in reversed(CREATED_AT_TO_ADD):
        op.drop_column(table, "created_at")
    for table in reversed(CREATED_BY_TO_ADD):
        op.drop_column(table, "created_by")

    connection.execute(
        sa.text("DELETE FROM users WHERE id = :id AND email = :email"),
        {"id": SYSTEM_ID, "email": SYSTEM_EMAIL},
    )
