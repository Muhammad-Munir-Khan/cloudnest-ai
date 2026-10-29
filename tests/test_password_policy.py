"""Server-side password policy (UserManager.validate_password)."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi_users.exceptions import InvalidPasswordException

from app.core.auth import PASSWORD_MAX_LENGTH, UserManager

USER = SimpleNamespace(email="alice.smith@example.com")


def _validate(password: str, user=USER):
    return asyncio.run(UserManager(user_db=None).validate_password(password, user))


@pytest.mark.parametrize(
    "password",
    [
        "short",                                  # too short
        "x" * (PASSWORD_MAX_LENGTH + 1),          # too long
        "          ",                             # whitespace only
        "my-alice.smith-pass",                    # contains email local part
        "ALICE.SMITH@EXAMPLE.COM!1",              # contains full email (case-insensitive)
    ],
)
def test_rejected(password):
    with pytest.raises(InvalidPasswordException):
        _validate(password)


@pytest.mark.parametrize("password", ["correct horse battery", "Tr0ub4dor&3", "x" * PASSWORD_MAX_LENGTH])
def test_accepted(password):
    _validate(password)  # does not raise


def test_short_local_part_not_overmatched():
    # A 2-char local part like "al" must not block passwords containing "al".
    _validate("totally-valid-pass", SimpleNamespace(email="al@example.com"))


def test_works_without_email_attribute():
    _validate("long-enough-password", SimpleNamespace())
