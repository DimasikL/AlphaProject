"""
Управление историей чата с маскированием.
Хранит и маскированную, и оригинальную версию каждого сообщения.
"""

from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    """Одно сообщение в диалоге."""
    role: str                   # "user" или "assistant"
    original_content: str       # с PII (хранится только на сервере)
    masked_content: str         # без PII (отправляется в LLM)


class ChatHistory:
    """
    История диалога для одной сессии.
    Хранит два вида каждого сообщения:
    - original (с PII) — для отображения клиенту
    - masked (без PII) — для отправки в LLM
    """

    def __init__(self, max_messages: int = 20):
        self.messages: list[ChatMessage] = []
        self.max_messages = max_messages

    def add_user_message(self, original: str, masked: str):
        """Добавляет сообщение пользователя."""
        self.messages.append(ChatMessage(
            role="user",
            original_content=original,
            masked_content=masked,
        ))
        self._trim()

    def add_assistant_message(self, masked_response: str, clean_response: str):
        """Добавляет ответ ассистента."""
        self.messages.append(ChatMessage(
            role="assistant",
            original_content=clean_response,    # размаскированный
            masked_content=masked_response,      # как получили от LLM
        ))
        self._trim()

    def get_messages_for_llm(self) -> list[dict]:
        """
        Возвращает историю в формате OpenAI/Mistral.
        ВСЕ сообщения — замаскированные.
        """
        return [
            {"role": msg.role, "content": msg.masked_content}
            for msg in self.messages
        ]

    def get_messages_for_client(self) -> list[dict]:
        """Возвращает историю с оригинальными (реальными) данными."""
        return [
            {"role": msg.role, "content": msg.original_content}
            for msg in self.messages
        ]

    def _trim(self):
        """Обрезает историю до max_messages."""
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

    def __len__(self):
        return len(self.messages)