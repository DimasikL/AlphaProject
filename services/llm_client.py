"""
Клиент для подключения к реальному LLM API.
Поддерживает OpenAI-совместимый формат (OpenAI, YandexGPT, GigaChat, и др.)
"""

import httpx
import json
import os
import logging
from typing import AsyncGenerator
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Настройки LLM."""
    api_url: str = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    api_key: str = os.getenv("LLM_API_KEY", "")
    model: str = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    temperature: float = 0.7
    max_tokens: int = 1024
    timeout: float = 30.0


class LLMClient:
    """
    Универсальный async-клиент для LLM.
    Поддерживает streaming (SSE) и обычные запросы.
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._client = httpx.AsyncClient(timeout=self.config.timeout)

    async def close(self):
        await self._client.aclose()

    async def chat_stream(
            self,
            messages: list[dict],
            system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Стриминг ответа от LLM.
        Yields: чанки текста (по мере генерации).
        """
        payload = self._build_payload(messages, system_prompt, stream=True)
        headers = self._build_headers()

        try:
            async with self._client.stream(
                    "POST",
                    self.config.api_url,
                    json=payload,
                    headers=headers,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API error: {e.response.status_code} {e.response.text}")
            yield f"[Ошибка LLM: {e.response.status_code}]"
        except httpx.ConnectError:
            logger.error("Не удалось подключиться к LLM API")
            yield "[Ошибка: LLM недоступен]"
        except Exception as e:
            logger.error(f"LLM unexpected error: {e}")
            yield f"[Ошибка: {str(e)}]"

    async def chat_sync(
            self,
            messages: list[dict],
            system_prompt: str | None = None,
    ) -> str:
        """Синхронный запрос (полный ответ разом)."""
        payload = self._build_payload(messages, system_prompt, stream=False)
        headers = self._build_headers()

        try:
            response = await self._client.post(
                self.config.api_url,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM sync error: {e}")
            return f"[Ошибка LLM: {str(e)}]"

    def _build_payload(
            self,
            messages: list[dict],
            system_prompt: str | None,
            stream: bool,
    ) -> dict:
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        return {
            "model": self.config.model,
            "messages": all_messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": stream,
        }

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers


# ── Системный промпт для маскированных запросов ────────────

SYSTEM_PROMPT_MASKED = """Ты — банковский ассистент. 
В запросе клиента некоторые персональные данные заменены на токены вида [PERSON_1], [PHONE_1] и т.д.
Используй эти токены КАК ЕСТЬ в своём ответе. НЕ пытайся их расшифровать, изменить формат или удалить.
Если видишь [PERSON_1] — пиши [PERSON_1], не меняй регистр, не убирай скобки.
Отвечай на русском языке, кратко и по делу."""