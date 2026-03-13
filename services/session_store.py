import time
import threading
from dataclasses import dataclass, field
from services.chat_history import ChatHistory


@dataclass
class Session:
    session_id: str
    mapping: dict[str, str] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)  # ← НОВОЕ
    history: ChatHistory = field(default_factory=ChatHistory)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    request_count: int = 0

    def merge_mapping(self, new_mapping: dict[str, str]):
        self.mapping.update(new_mapping)
        self.updated_at = time.time()
        self.request_count += 1

    def next_token(self, entity_type: str) -> str:
        """Генерирует уникальный токен в рамках сессии."""
        count = self.counters.get(entity_type, 0) + 1
        self.counters[entity_type] = count
        return f"[{entity_type}_{count}]"

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


class SessionStore:

    def __init__(self, ttl_seconds: int = 3600):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_seconds

    def get_or_create(self, session_id: str) -> Session:
        with self._lock:
            self._cleanup_expired()
            if session_id not in self._sessions:
                self._sessions[session_id] = Session(session_id=session_id)
            return self._sessions[session_id]

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def save_mapping(self, session_id: str, mapping: dict[str, str]):
        session = self.get_or_create(session_id)
        session.merge_mapping(mapping)

    def get_mapping(self, session_id: str) -> dict[str, str]:
        session = self.get(session_id)
        return session.mapping if session else {}

    def get_history(self, session_id: str) -> ChatHistory:
        session = self.get_or_create(session_id)
        return session.history

    def delete(self, session_id: str):
        with self._lock:
            self._sessions.pop(session_id, None)

    def list_sessions(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "session_id": s.session_id,
                    "request_count": s.request_count,
                    "age_seconds": round(s.age_seconds, 1),
                    "mapping_size": len(s.mapping),
                    "history_length": len(s.history),
                }
                for s in self._sessions.values()
            ]

    def _cleanup_expired(self):
        now = time.time()
        expired = [
            sid for sid, session in self._sessions.items()
            if now - session.updated_at > self.ttl_seconds
        ]
        for sid in expired:
            del self._sessions[sid]