"""
Конечный автомат для размаскирования потока от LLM.

Поддерживает два формата токенов:
  - Скобочный:  [PER_1], [PHONE_2], [CARD_1]
  - XML-тег:    <PII_PER_1/>, <PII_PHONE_2/>

Выбор формата задаётся при инициализации.
"""

import re
from enum import Enum, auto
from typing import Optional


class TokenFormat(Enum):
    BRACKET = auto()    # [PER_1]
    XML = auto()        # <PII_PER_1/>
    PREFIX = auto()     # XMASK_a3f7b2c1_PER  (без разделителей)


class StreamInterceptor:
    """
    Принимает чанки (куски текста) из LLM-стрима,
    буферизует потенциальные токены-заглушки,
    заменяет их на реальные данные из mapping.
    """

    # ── Настройки формата ──────────────────────────────────
    FORMAT_CONFIG = {
        TokenFormat.BRACKET: {
            "open": "[",
            "close": "]",
            "pattern": re.compile(r"\[([A-Z]+_\d+)\]"),
            "max_token_len": 30,
        },
        TokenFormat.XML: {
            "open": "<",
            "close": "/>",
            "pattern": re.compile(r"<(PII_[A-Z]+_\d+)/>"),
            "max_token_len": 40,
        },
        TokenFormat.PREFIX: {
            "open": "XMASK_",
            "close": " ",          # токен заканчивается пробелом или концом строки
            "pattern": re.compile(r"(XMASK_[a-f0-9]{8}_[A-Z]+)"),
            "max_token_len": 40,
        },
    }

    def __init__(
            self,
            mapping: dict[str, str],
            fmt: TokenFormat = TokenFormat.BRACKET,
            max_buffer_size: int = 50,
    ):
        """
        Args:
            mapping: {"[PER_1]": "Иванов Пётр", "[PHONE_1]": "+7 999 123-45-67"}
            fmt: формат токенов-заглушек
            max_buffer_size: если буфер длиннее — считаем, что это не токен,
                             сбрасываем буфер клиенту
        """
        self.mapping = mapping
        self.fmt = fmt
        self.cfg = self.FORMAT_CONFIG[fmt]
        self.max_buffer_size = max_buffer_size

        # ── Состояние автомата ──
        self.buffer: str = ""
        self.in_token: bool = False
        self._stats = {"replaced": 0, "passed_through": 0, "buffer_overflows": 0}

    # ── Основной метод ─────────────────────────────────────
    def feed(self, chunk: str) -> str:
        """
        Принимает очередной чанк от LLM.
        Возвращает текст, безопасный для отправки клиенту.
        Может вернуть пустую строку, если идёт буферизация.
        """
        if self.fmt == TokenFormat.BRACKET:
            return self._feed_bracket(chunk)
        elif self.fmt == TokenFormat.XML:
            return self._feed_xml(chunk)
        elif self.fmt == TokenFormat.PREFIX:
            return self._feed_prefix(chunk)

    def flush(self) -> str:
        """Вызывается в конце стрима — отдать всё, что осталось в буфере."""
        if not self.buffer:
            self.in_token = False
            return ""
        remaining = self._resolve_buffer()
        self.buffer = ""
        self.in_token = False
        return remaining

    @property
    def stats(self) -> dict:
        return self._stats.copy()

    # ── Реализация для BRACKET формата ─────────────────────
    def _feed_bracket(self, chunk: str) -> str:
        result = []

        for char in chunk:
            if char == "[":
                # Если уже копили что-то обычное — сбросить
                if self.buffer and not self.in_token:
                    result.append(self.buffer)
                    self.buffer = ""
                # Если уже внутри токена и встретили новый [ —
                # значит предыдущий [ был ложным
                if self.in_token:
                    result.append(self.buffer)
                    self.buffer = ""
                self.in_token = True
                self.buffer = "["

            elif char == "]" and self.in_token:
                self.buffer += "]"
                result.append(self._resolve_buffer())
                self.buffer = ""
                self.in_token = False

            else:
                self.buffer += char

                # Защита: если буфер подозрительно длинный — это не токен
                if self.in_token and len(self.buffer) > self.max_buffer_size:
                    self._stats["buffer_overflows"] += 1
                    result.append(self.buffer)
                    self.buffer = ""
                    self.in_token = False

        # Если мы НЕ внутри токена — отдаём накопленное
        if not self.in_token and self.buffer:
            result.append(self.buffer)
            self.buffer = ""

        return "".join(result)

    # ── Реализация для XML формата ─────────────────────────
    def _feed_xml(self, chunk: str) -> str:
        result = []

        for char in chunk:
            if char == "<" and not self.in_token:
                if self.buffer:
                    result.append(self.buffer)
                    self.buffer = ""
                self.in_token = True
                self.buffer = "<"

            elif self.in_token:
                self.buffer += char
                # XML-тег закрывается на />
                if self.buffer.endswith("/>"):
                    result.append(self._resolve_buffer())
                    self.buffer = ""
                    self.in_token = False
                # Если встретили > без / — это не наш тег
                elif char == ">" and not self.buffer.endswith("/>"):
                    result.append(self.buffer)
                    self.buffer = ""
                    self.in_token = False
                # Overflow
                elif len(self.buffer) > self.max_buffer_size:
                    self._stats["buffer_overflows"] += 1
                    result.append(self.buffer)
                    self.buffer = ""
                    self.in_token = False
            else:
                self.buffer += char

        if not self.in_token and self.buffer:
            result.append(self.buffer)
            self.buffer = ""

        return "".join(result)

    # ── Реализация для PREFIX формата ──────────────────────
    def _feed_prefix(self, chunk: str) -> str:
        """
        PREFIX формат: XMASK_a3f7b2c1_PER
        Сложнее, потому что нет явного закрывающего символа.
        Считаем что токен заканчивается пробелом, запятой, точкой или концом строки.
        """
        result = []
        DELIMITERS = {" ", ",", ".", "!", "?", ";", ":", "\n", "\t"}

        for char in chunk:
            if self.in_token:
                if char in DELIMITERS:
                    # Токен закончился
                    resolved = self._resolve_buffer()
                    result.append(resolved)
                    result.append(char)  # сам разделитель тоже отдаём
                    self.buffer = ""
                    self.in_token = False
                else:
                    self.buffer += char
                    if len(self.buffer) > self.max_buffer_size:
                        self._stats["buffer_overflows"] += 1
                        result.append(self.buffer)
                        self.buffer = ""
                        self.in_token = False
            else:
                self.buffer += char
                # Проверяем, не начался ли PREFIX-токен
                if "XMASK_" in self.buffer:
                    idx = self.buffer.index("XMASK_")
                    # Всё до XMASK_ — отдаём
                    before = self.buffer[:idx]
                    if before:
                        result.append(before)
                    self.buffer = self.buffer[idx:]
                    self.in_token = True

        if not self.in_token and self.buffer:
            # Проверяем, не начинается ли XMASK_ в конце буфера (частичное совпадение)
            partial = self._partial_prefix_match(self.buffer, "XMASK_")
            if partial > 0:
                result.append(self.buffer[:-partial])
                self.buffer = self.buffer[-partial:]
            else:
                result.append(self.buffer)
                self.buffer = ""

        return "".join(result)

    @staticmethod
    def _partial_prefix_match(text: str, prefix: str) -> int:
        """
        Проверяет, заканчивается ли text на начало prefix.
        Возвращает длину совпадения. Например:
          text="abcXM", prefix="XMASK_" → 2  (XM совпадает с началом XMASK_)
        """
        for length in range(min(len(prefix), len(text)), 0, -1):
            if text.endswith(prefix[:length]):
                return length
        return 0

    # ── Резолвер буфера ────────────────────────────────────
    def _resolve_buffer(self) -> str:
        """Проверяет, есть ли буфер в mapping. Если да — заменяет."""
        token = self.buffer.strip()
        if token in self.mapping:
            self._stats["replaced"] += 1
            return self.mapping[token]
        else:
            self._stats["passed_through"] += 1
            return self.buffer