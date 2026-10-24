import pytest

from app.infrastructure.database.test_safety import assert_test_database


def test_allows_only_expected_test_database():
    assert_test_database("postgresql+asyncpg://user:secret@localhost/rzadb_test")


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+asyncpg://user:secret@localhost/rzadb",
        "postgresql+asyncpg://user:secret@localhost/another_database",
    ],
)
def test_rejects_other_database_names(database_url):
    with pytest.raises(RuntimeError, match="rzadb_test") as error:
        assert_test_database(database_url)
    assert "secret" not in str(error.value)


def test_rejects_missing_database_name():
    with pytest.raises(RuntimeError, match="rzadb_test"):
        assert_test_database("postgresql+asyncpg://user:secret@localhost")
