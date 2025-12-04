"""Filesystem-backed session storage for the AI assistant."""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Dict, Optional

from .models import AssistantMessage, AssistantSession


class AssistantSessionStore:
    """Store assistant sessions as JSON files for simple persistence."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def create_session(self, *, user_id: Optional[str] = None, config: Optional[dict] = None) -> AssistantSession:
        session_id = uuid.uuid4().hex
        session = AssistantSession(id=session_id, user_id=user_id, config=config or {})
        self._write_session(session)
        return session

    def load_session(self, session_id: str) -> Optional[AssistantSession]:
        path = self._session_path(session_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return AssistantSession.model_validate(data)

    def save_session(self, session: AssistantSession) -> None:
        self._write_session(session)

    def append_message(
        self,
        session_id: str,
        message: AssistantMessage,
        *,
        max_messages: Optional[int] = None,
    ) -> AssistantSession:
        with self._lock_for_session(session_id):
            session = self.load_session(session_id)
            if session is None:
                raise ValueError(f"Session {session_id} not found")
            session.append_message(message, max_messages=max_messages)
            self._write_session(session)
            return session

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _session_path(self, session_id: str) -> Path:
        return self.base_dir / f"{session_id}.json"

    def _write_session(self, session: AssistantSession) -> None:
        payload = session.model_dump(mode="json")
        path = self._session_path(session.id)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def _lock_for_session(self, session_id: str) -> threading.Lock:
        with self._global_lock:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[session_id] = lock
            return lock
