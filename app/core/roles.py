"""User roles for the admin system.

Three tiers (source of truth = the `role` column on User):
  user         - regular end user; no admin access
  corpus_admin - can manage the Global Islamic corpus (ingest, delete content)
  super_admin  - everything corpus_admin can do, PLUS user/role management

`is_superuser` (fastapi-users built-in) is kept auto-synced: a user is a
superuser iff role == super_admin. Nothing authorizes on it: the
fastapi-users /users/{id} routes that did are not mounted, so `role` is the
only source of admin rights.

This deliberately uses a single `role` field rather than a full
permissions table. If granular per-permission control is needed later, this
enum migrates cleanly into a roles/permissions schema without breaking the
column (the values just become role identifiers).
"""
from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    user = "user"
    corpus_admin = "corpus_admin"
    super_admin = "super_admin"


# Numeric rank for "at least this role" comparisons. Higher = more privileged.
_RANK: dict[str, int] = {
    UserRole.user.value: 0,
    UserRole.corpus_admin.value: 1,
    UserRole.super_admin.value: 2,
}


def role_rank(role: str | UserRole) -> int:
    """Return the privilege rank of a role (unknown roles rank as 0)."""
    val = role.value if isinstance(role, UserRole) else str(role)
    return _RANK.get(val, 0)


def has_at_least(role: str | UserRole, minimum: str | UserRole) -> bool:
    """True if `role` is at least as privileged as `minimum`."""
    return role_rank(role) >= role_rank(minimum)
