"""Self-service email/password changes require the current password (SEC-16)."""
import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi_users.exceptions import InvalidPasswordException

from app.core.auth import UserManager
from app.core.schemas_user import UserUpdate

CURRENT = "Correct-pass-1"


class _FakeUserDB:
    def __init__(self):
        self.updates: list[dict] = []

    async def get_by_email(self, email):
        return None  # email not taken

    async def update(self, user, update_dict):
        self.updates.append(dict(update_dict))
        for key, value in update_dict.items():
            setattr(user, key, value)
        return user


def _setup():
    db = _FakeUserDB()
    manager = UserManager(db)
    user = SimpleNamespace(
        id=uuid.uuid4(), email="alice@example.com", role="user", is_superuser=False,
        hashed_password=manager.password_helper.hash(CURRENT),
    )
    return manager, user, db


def _update(manager, user, safe=True, **fields):
    return asyncio.run(manager.update(UserUpdate(**fields), user, safe=safe))


def _stored_keys(db):
    return {k for u in db.updates for k in u}


@pytest.mark.parametrize(
    "fields",
    [
        {"password": "Brand-new-pass-2"},
        {"password": "Brand-new-pass-2", "current_password": "wrong"},
        {"email": "attacker@example.com"},
        {"email": "attacker@example.com", "current_password": ""},
    ],
)
def test_credential_change_without_correct_current_password_is_rejected(fields):
    manager, user, db = _setup()
    with pytest.raises(InvalidPasswordException):
        _update(manager, user, **fields)
    assert db.updates == []  # nothing written


def test_password_change_with_current_password_succeeds():
    manager, user, db = _setup()
    _update(manager, user, password="Brand-new-pass-2", current_password=CURRENT)
    assert manager.password_helper.verify_and_update("Brand-new-pass-2", user.hashed_password)[0]
    assert "current_password" not in _stored_keys(db)
    assert "jwt_invalidated_at" in _stored_keys(db)  # SEC-02 revocation still runs


def test_email_change_with_current_password_succeeds():
    manager, user, db = _setup()
    _update(manager, user, email="new@example.com", current_password=CURRENT)
    assert user.email == "new@example.com"
    assert "current_password" not in _stored_keys(db)


def test_display_name_change_needs_no_password():
    manager, user, db = _setup()
    _update(manager, user, display_name="Alice")
    assert user.display_name == "Alice"


def test_same_email_is_not_a_change():
    manager, user, _ = _setup()
    _update(manager, user, email="ALICE@example.com", display_name="A")  # no raise


def test_superuser_update_is_not_gated():
    manager, user, _ = _setup()
    _update(manager, user, safe=False, password="Admin-set-pass-3")
    assert manager.password_helper.verify_and_update("Admin-set-pass-3", user.hashed_password)[0]


def test_self_update_cannot_grant_superuser_or_reactivate():
    """PATCH /users/me uses safe=True, which drops privileged fields (SEC-13)."""
    manager, user, db = _setup()
    _update(manager, user, is_superuser=True, is_active=True, is_verified=True,
            display_name="Alice")
    assert user.is_superuser is False
    assert _stored_keys(db) == {"display_name"}
