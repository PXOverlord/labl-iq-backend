"""Data models used by the AI assistant service."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

AssistantRole = Literal["system", "user", "assistant"]


class AssistantMessage(BaseModel):
    """Represents a single message that is part of a session."""

    id: str
    role: AssistantRole
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    suggestions: Optional[List[str]] = None
    context: Optional[Dict[str, Any]] = None


class AssistantSession(BaseModel):
    """Conversation container stored on disk for persistence."""

    id: str
    user_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    config: Dict[str, Any] = Field(default_factory=dict)
    messages: List[AssistantMessage] = Field(default_factory=list)

    def append_message(self, message: AssistantMessage, max_messages: Optional[int] = None) -> None:
        """Append a message and optionally trim history."""
        self.messages.append(message)
        if max_messages is not None and max_messages > 0:
            excess = len(self.messages) - max_messages
            if excess > 0:
                self.messages = self.messages[excess:]
        self.updated_at = datetime.utcnow()
