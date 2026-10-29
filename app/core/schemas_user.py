"""Pydantic schemas for user create / read / update.

Required by fastapi-users for its auto-generated routes.
"""
import uuid

from fastapi_users import schemas


class UserRead(schemas.BaseUser[uuid.UUID]):
    display_name: str | None = None
    role: str = "user"


class UserCreate(schemas.BaseUserCreate):
    display_name: str | None = None


class UserUpdate(schemas.BaseUserUpdate):
    display_name: str | None = None
    # Required by PATCH /users/me when changing email or password, so a
    # stolen session token alone cannot take over the account. Never stored.
    current_password: str | None = None