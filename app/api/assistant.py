"""API routes for the LABL IQ conversational assistant."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import get_current_active_user
from app.schemas.auth import UserResponse
from app.services.assistant import AssistantMessage, AssistantSession, get_assistant_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class AssistantMessageOut(BaseModel):
    id: str
    role: str
    content: str
    createdAt: datetime = Field(alias="created_at")
    suggestions: Optional[List[str]] = None

    @classmethod
    def from_model(cls, message: AssistantMessage) -> "AssistantMessageOut":
        return cls(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            suggestions=message.suggestions,
        )

    class Config:
        populate_by_name = True


class AssistantSessionOut(BaseModel):
    sessionId: str = Field(alias="session_id")
    createdAt: datetime = Field(alias="created_at")
    updatedAt: datetime = Field(alias="updated_at")
    messages: List[AssistantMessageOut]

    @classmethod
    def from_model(cls, session: AssistantSession) -> "AssistantSessionOut":
        return cls(
            session_id=session.id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            messages=[AssistantMessageOut.from_model(msg) for msg in session.messages],
        )

    class Config:
        populate_by_name = True


class CreateSessionRequest(BaseModel):
    context: Optional[Dict[str, Any]] = None


class SendMessageRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None


class SendMessageResponse(BaseModel):
    message: AssistantMessageOut
    session: AssistantSessionOut


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/sessions", response_model=AssistantSessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: CreateSessionRequest,
    current_user: UserResponse = Depends(get_current_active_user),
):
    service = get_assistant_service()
    session = await service.create_session(user_id=current_user.id, context=payload.context)
    return AssistantSessionOut.from_model(session)


@router.get("/sessions/{session_id}", response_model=AssistantSessionOut)
async def get_session(
    session_id: str,
    current_user: UserResponse = Depends(get_current_active_user),
):
    service = get_assistant_service()
    session = await service.get_session(session_id)
    if session is None or (session.user_id and session.user_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return AssistantSessionOut.from_model(session)


@router.post("/sessions/{session_id}/messages", response_model=SendMessageResponse)
async def send_message(
    session_id: str,
    payload: SendMessageRequest,
    current_user: UserResponse = Depends(get_current_active_user),
):
    service = get_assistant_service()
    session = await service.get_session(session_id)
    if session is None or (session.user_id and session.user_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    response = await service.send_message(
        session_id,
        payload.message,
        user_id=current_user.id,
        context=payload.context,
    )
    updated_session = await service.get_session(session_id)
    if updated_session is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Session unavailable")
    return SendMessageResponse(
        message=AssistantMessageOut.from_model(response),
        session=AssistantSessionOut.from_model(updated_session),
    )
