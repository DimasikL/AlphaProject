"""Pydantic-модели для API."""

from pydantic import BaseModel, ConfigDict, Field
import uuid


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Здравствуйте, я Иванов Пётр, мой телефон +7 999 123-45-67",
                "session_id": "user-123",
                "stream": True,
            }
        }
    )

    message: str = Field(..., min_length=1, max_length=5000)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    stream: bool = Field(default=True)


class ChatResponseSync(BaseModel):
    original_message: str
    masked_message: str
    llm_response_masked: str
    llm_response_clean: str
    mapping: dict[str, str]
    entities_found: int
    stats: dict


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    active_sessions: int = 0


class SessionInfo(BaseModel):
    session_id: str
    mapping: dict[str, str]
    request_count: int
    age_seconds: float