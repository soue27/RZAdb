from app.application.auth.password import PasswordService


def test_password_hash_and_verify() -> None:
    service = PasswordService()

    password = "StrongPassword123!"
    password_hash = service.hash(password)

    assert password_hash != password
    assert service.verify(password, password_hash) is True


def test_wrong_password_does_not_verify() -> None:
    service = PasswordService()

    password_hash = service.hash("StrongPassword123!")

    assert service.verify("WrongPassword123!", password_hash) is False