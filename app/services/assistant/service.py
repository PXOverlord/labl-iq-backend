"""Assistant service orchestrating session storage and provider calls."""
from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any, Dict, Iterable, Optional

from app.core.config import settings

from .models import AssistantMessage, AssistantSession
from .provider import AssistantCompletion, AssistantProvider, LocalAssistantProvider, OpenAIChatProvider
from .session_store import AssistantSessionStore


class AssistantService:
    """High level facade for conversational assistant interactions."""

    def __init__(
        self,
        store: AssistantSessionStore,
        provider: AssistantProvider,
        *,
        max_history: int = 20,
    ) -> None:
        self.store = store
        self.provider = provider
        self.max_history = max(4, max_history)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------
    async def create_session(
        self,
        *,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AssistantSession:
        session = self.store.create_session(user_id=user_id, config=context or {})
        if context:
            session.config.update(context)
            self.store.save_session(session)
        return session

    async def get_session(self, session_id: str) -> Optional[AssistantSession]:
        return self.store.load_session(session_id)

    async def list_messages(self, session_id: str) -> Iterable[AssistantMessage]:
        session = await self.get_session(session_id)
        return session.messages if session else []

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------
    async def send_message(
        self,
        session_id: str,
        content: str,
        *,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AssistantMessage:
        if not content.strip():
            raise ValueError("Message content must not be empty")

        session = self.store.load_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        if user_id and not session.user_id:
            session.user_id = user_id

        if context:
            session.config.update(context)

        user_message = AssistantMessage(
            id=uuid.uuid4().hex,
            role="user",
            content=content.strip(),
            context=context,
        )
        session.append_message(user_message, max_messages=self._max_messages())
        self.store.save_session(session)

        response = await self._generate_response(session, context=context)
        session.append_message(response, max_messages=self._max_messages())
        self.store.save_session(session)

        return response

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _generate_response(
        self,
        session: AssistantSession,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> AssistantMessage:
        merged_context = _merge_context(session.config, context)
        recent_history = session.messages[-self.max_history :]
        completion: AssistantCompletion = await self.provider.complete_chat(
            recent_history,
            context=merged_context,
        )
        return AssistantMessage(
            id=uuid.uuid4().hex,
            role="assistant",
            content=completion.content,
            suggestions=completion.suggestions,
            context={"suggestions": completion.suggestions} if completion.suggestions else None,
        )

    def _max_messages(self) -> int:
        # store both assistant and user turns
        return self.max_history * 2


def _merge_context(session_context: Dict[str, Any], new_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(session_context or {})
    if new_context:
        for key, value in new_context.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)  # type: ignore[index]
            else:
                merged[key] = value
    return merged


def _build_provider() -> AssistantProvider:
    provider_name = (settings.AI_ASSISTANT_PROVIDER or "local").lower()
    base_prompt = settings.AI_ASSISTANT_SYSTEM_PROMPT

    if provider_name == "openai" and settings.OPENAI_API_KEY:
        return OpenAIChatProvider(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
            api_base=settings.OPENAI_API_BASE,
            base_prompt=base_prompt,
            history_limit=settings.AI_ASSISTANT_MAX_HISTORY,
        )

    return LocalAssistantProvider(base_prompt)


@lru_cache(maxsize=1)
def get_assistant_service() -> AssistantService:
    store = AssistantSessionStore(settings.AI_ASSISTANT_DATA_DIR)
    provider = _build_provider()
    return AssistantService(
        store,
        provider,
        max_history=settings.AI_ASSISTANT_MAX_HISTORY,
    )
