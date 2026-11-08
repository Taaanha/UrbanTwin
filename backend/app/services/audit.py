from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def audit(
    db: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str | int,
    detail: dict[str, Any] | None = None,
    note: str | None = None,
) -> None:
    """Adds an audit row to the caller's transaction (commit is the caller's)."""
    db.add(
        AuditLog(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            detail=detail or {},
            note=note,
        )
    )
