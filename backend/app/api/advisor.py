from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_staff
from app.database import get_db
from app.services import advisor
from app.services.ai_opinion import ProviderError, ProviderUnavailable

router = APIRouter(prefix="/api/advisor", tags=["advisor"], dependencies=[Depends(require_staff)])


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=advisor.MAX_CHARS)


class ChatBody(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=advisor.MAX_MESSAGES)
    search: bool = False  # add web background (Gemini search grounding), kept apart from the city data


@router.post("/chat")
def chat(body: ChatBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return advisor.chat(db, [m.model_dump() for m in body.messages], search=body.search)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
