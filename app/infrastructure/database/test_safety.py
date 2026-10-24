from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

EXPECTED_TEST_DATABASE = "rzadb_test"


def assert_test_database(database_url: str) -> None:
    """Fail closed unless a test-only operation targets the dedicated DB."""
    try:
        database_name = make_url(database_url).database
    except ArgumentError:
        raise RuntimeError(
            "Test database URL is invalid; refusing to continue."
        ) from None

    if database_name != EXPECTED_TEST_DATABASE:
        raise RuntimeError(
            "Test database must be named 'rzadb_test'; refusing to continue."
        )
