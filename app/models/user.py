"""User model + OAuth account model for fastapi-users authentication."""
import uuid
from datetime import datetime

from fastapi_users.db import SQLAlchemyBaseOAuthAccountTableUUID
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.roles import UserRole


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    """One external OAuth account (Google/GitHub) linked to a User."""
    __tablename__ = "oauth_account"

    # Explicit FK to users.id. The base class declares user_id, but we
    # re-declare it here with an explicit ForeignKey so SQLAlchemy can
    # resolve the User.oauth_accounts relationship join condition.
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="cascade"),
        nullable=False,
    )


class User(SQLAlchemyBaseUserTableUUID, Base):
    """Application user."""
    __tablename__ = "users"

    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Admin role tier. Source of truth for admin access; is_superuser (from the
    # fastapi-users base) is kept in sync (super_admin <-> is_superuser=True)
    # by the user manager so built-in superuser checks stay consistent.
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserRole.user.value,
        server_default=UserRole.user.value,
    )

    # When the user account was created. Backfilled to now() for users that
    # existed before this column was added; auto-set for all new signups.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Force-logout support. When an admin force-logs out a user, this is set
    # to now(). JWTs whose iat claim predates this timestamp are rejected by
    # current_active_fresh_user (app/core/auth.py).
    jwt_invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        "OAuthAccount",
        lazy="joined",
    )
