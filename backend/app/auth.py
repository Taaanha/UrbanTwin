"""Minimal role gate for the government dashboard.

Citizens can submit and track reports without a login. Everything else
(queues, verification, planning, projects, audit) needs the shared staff token
sent as the ``X-Staff-Token`` header. If ``STAFF_TOKEN`` is empty the gate is
open, which is only acceptable on a lab laptop; /api/health reports this.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from app.config import get_settings


def auth_enabled() -> bool:
    return bool(get_settings().staff_token)


def require_staff(
    x_staff_token: str | None = Header(default=None),
    x_staff_name: str | None = Header(default=None),
) -> str:
    """Returns the acting staff name (used in audit logs)."""
    expected = get_settings().staff_token
    actor = (x_staff_name or "").strip()[:64] or "staff"
    if not expected:
        return actor
    if not x_staff_token or not secrets.compare_digest(x_staff_token, expected):
        raise HTTPException(status_code=401, detail="Staff login required.")
    return actor
