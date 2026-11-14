import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_staff
from app.database import SessionLocal, get_db
from app.services import insights

router = APIRouter(prefix="/api/insights", tags=["insights"], dependencies=[Depends(require_staff)])

POLL_SECONDS = 3.0
MAX_STREAM_SECONDS = 25.0  # streams end by themselves so a server restart never waits on them; the browser reconnects with since_id
HEARTBEAT_EVERY = 5  # polls between keep-alive comments


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    use_ai: bool = True  # only used when the fixed rules cannot read the question; falls back silently if no provider is set


@router.get("/quality")
def quality(db: Session = Depends(get_db)) -> dict[str, Any]:
    return insights.quality(db)


@router.get("/timelapse")
def timelapse(days: int = Query(30, ge=1, le=90), db: Session = Depends(get_db)) -> dict[str, Any]:
    return insights.timelapse(db, days)


@router.post("/ask")
def ask(body: AskBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    return insights.ask(db, body.question.strip(), use_ai=body.use_ai)


@router.get("/alerts")
def alerts(since_id: int | None = Query(default=None, ge=0), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Polling fallback. Without since_id it only reports the current high-water mark."""
    latest = insights.max_report_id(db)
    if since_id is None:
        return {"latest_id": latest, "items": []}
    items = insights.alerts_since(db, since_id)
    return {"latest_id": max([latest] + [i["id"] for i in items]), "items": items}


def _event(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"


async def _stream(since_id: int | None, max_polls: int | None):
    """Server-sent events. Polls the database; sends only high/critical reports newer than the last one seen."""
    with SessionLocal() as db:
        last = since_id if since_id is not None else insights.max_report_id(db)
    yield _event("ready", {"latest_id": last})
    polls = 0
    started = time.monotonic()
    while max_polls is None or polls < max_polls:
        if max_polls is None and time.monotonic() - started > MAX_STREAM_SECONDS:
            yield _event("bye", {"latest_id": last, "reconnect": True})
            return
        polls += 1

        def fetch() -> tuple[list[dict[str, Any]], int]:
            with SessionLocal() as db:
                return insights.alerts_since(db, last), insights.max_report_id(db)

        items, latest = await asyncio.to_thread(fetch)
        for item in items:
            yield _event("alert", item)
        last = max([last, latest if not items else 0] + [i["id"] for i in items])
        if not items and polls % HEARTBEAT_EVERY == 0:
            yield ": keep-alive\n\n"
        if max_polls is not None and polls >= max_polls:
            break
        await asyncio.sleep(POLL_SECONDS if max_polls is None else 0.05)


@router.get("/alerts/stream")
async def alerts_stream(
    since_id: int | None = Query(default=None, ge=0),
    max_polls: int | None = Query(default=None, ge=1, le=100, include_in_schema=False),
) -> StreamingResponse:
    return StreamingResponse(
        _stream(since_id, max_polls),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
