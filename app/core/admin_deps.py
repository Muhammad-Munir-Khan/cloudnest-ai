"""Role-gated dependencies for admin endpoints.

Built on top of current_active_fresh_user (auth.py) so that any admin who has
been force-logged-out is rejected immediately even if their JWT hasn't expired.
"""
from fastapi import Depends, HTTPException, status

from app.core.auth import current_active_fresh_user
from app.core.roles import UserRole, has_at_least
from app.models.user import User


def require_role(minimum: UserRole):
    """Return a dependency that requires `minimum` role or higher."""
    async def _checker(
        user: User = Depends(current_active_fresh_user),
    ) -> User:
        role = getattr(user, "role", UserRole.user.value)
        if not has_at_least(UserRole(role), minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum.value} or higher",
            )
        return user

    return _checker


require_corpus_admin = require_role(UserRole.corpus_admin)
require_super_admin = require_role(UserRole.super_admin)
