"""File-aware secrets loader.

In development, secrets come from the `.env` file via plain environment
variables — convenient, but `.env` on disk is not how you want to hold
production secrets. This module lets production supply each secret as a *file*
(Docker / Kubernetes secrets, or any mounted secret store) without changing
application code, while falling back to the plain env var everywhere else.

Resolution order for `get_secret("JWT_SECRET")`:
  1. `JWT_SECRET_FILE` env points at a file  -> read & strip its contents
  2. `/run/secrets/jwt_secret` exists          -> read & strip (Docker secrets
                                                  convention: lowercased name)
  3. `JWT_SECRET` env var                       -> use directly
  4. otherwise                                  -> `default` (or raise if required)

Wiring (in app/core/config.py), change e.g.:

    jwt_secret: str = Field(...)
to load through this helper, for example in a validator or a factory:

    from app.core.secrets import get_secret
    jwt_secret: str = Field(default_factory=lambda: get_secret("JWT_SECRET", required=False) or "")

or simply call get_secret(...) where the value is consumed. Keeping it optional
in dev means nothing breaks before you adopt a secret store.

Example docker-compose.prod.yml addition to mount a Docker secret:

    secrets:
      jwt_secret:
        file: ./secrets/jwt_secret.txt
    services:
      api:
        secrets: [jwt_secret]    # -> available at /run/secrets/jwt_secret
"""
import os
from pathlib import Path

_DOCKER_SECRETS_DIR = Path("/run/secrets")


class SecretNotFoundError(RuntimeError):
    """Raised when a required secret can't be resolved from any source."""


def get_secret(name: str, *, default: str | None = None, required: bool = False) -> str | None:
    """Resolve a secret by name (see module docstring for the lookup order).

    Args:
        name: the logical secret name, e.g. "JWT_SECRET".
        default: value to return if nothing is found and not required.
        required: if True and nothing is found, raise SecretNotFoundError.
    """
    # 1. Explicit *_FILE pointer (most flexible; works for any orchestrator).
    file_env = os.getenv(f"{name}_FILE")
    if file_env:
        p = Path(file_env)
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()

    # 2. Docker/K8s secrets convention: /run/secrets/<lowercased name>.
    docker_path = _DOCKER_SECRETS_DIR / name.lower()
    if docker_path.is_file():
        return docker_path.read_text(encoding="utf-8").strip()

    # 3. Plain environment variable (the dev path).
    env_val = os.getenv(name)
    if env_val is not None:
        return env_val

    # 4. Nothing found.
    if required:
        raise SecretNotFoundError(
            f"Secret '{name}' not found via {name}_FILE, "
            f"/run/secrets/{name.lower()}, or the {name} env var."
        )
    return default
