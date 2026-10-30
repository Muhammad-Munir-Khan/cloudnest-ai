"""Structured audit logging for security-relevant events.

Emits one structured (JSON) line per event to a dedicated `audit` logger, so
these events can be filtered and shipped separately from normal application
logs. In Phase 2 the `audit` logger is routed to a centralized aggregator
(append-only / WORM storage) where the trail becomes tamper-evident; for now it
lands in the container's stdout alongside other logs but is cleanly
distinguishable by the `"event": "audit"` marker and the `audit` logger name.

Events emitted today:
  - app/core/auth.py: login (success / failure / blocked), register,
    verify.request / verify.success, password.forgot / password.reset /
    password.change, credentials.change
  - app/api/admin_routes.py: user.role_change, user.suspend / user.unsuspend,
    user.force_logout, user.edit, user.send_reset, user.delete, and
    kb.ingest / kb.upload / kb.delete

Call it as, e.g.:

    from app.core.audit import audit_event
    audit_event("user.role_change", actor=admin.email, target=user.email,
                old_role=old, new_role=new)

Design rule: audit logging must NEVER break the request path. Every call is
wrapped so a serialization or logging error degrades to a plain log line.
"""
import json
import logging
from datetime import datetime, timezone

# Dedicated logger so audit events can be routed/filtered independently of
# application logs (e.g. a separate handler shipping to a SIEM in Phase 2).
_audit_logger = logging.getLogger("audit")


def audit_event(
    action: str,
    *,
    actor: str | None = None,
    target: str | None = None,
    status: str = "success",
    **fields,
) -> None:
    """Record a security-relevant event as a structured audit log line.

    Args:
        action: dotted event name, e.g. "login", "user.suspend", "kb.delete".
        actor: who performed it (email / user id), if known.
        target: who/what it affected (email / resource id), if applicable.
        status: "success" | "failure" | "blocked" | etc.
        **fields: any extra structured context (reason, old/new values, ...).
                  Avoid putting secrets or full PII here.
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "audit",
        "action": action,
        "actor": actor,
        "target": target,
        "status": status,
    }
    if fields:
        record["meta"] = fields

    try:
        _audit_logger.info(json.dumps(record, default=str, ensure_ascii=False))
    except Exception:
        # Last-resort fallback: never let audit logging raise into the caller.
        _audit_logger.info(
            "audit action=%s actor=%s target=%s status=%s",
            action, actor, target, status,
        )
