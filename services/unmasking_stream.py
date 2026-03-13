"""
StreamInterceptor — перенесён в services/ для чистоты архитектуры.
Размаскирование потока от LLM в реальном времени.
"""

import re
from enum import Enum, auto


class TokenFormat(Enum):
    BRACKET = auto()    # [PER_1]
    XML = auto()        # <PII_PER_1/>


class StreamInterceptor:
    """
    Принимает чанки от LLM, буферизует токены-заглушки,
    заменяет на реальные данные из mapping.
    """

    def __init__(
            self,
            mapping: dict[str, str],
            fmt: TokenFormat = TokenFormat.BRACKET,
            max_buffer_size: int = 50,
    ):
        self.mapping = mapping
        self.fmt = fmt
        self.max_buffer_size = max_buffer_size
        self.buffer: str = ""
        self.in_token: bool = False
        self._stats = {"replaced": 0, "passed_through": 0, "buffer_overflows": 0}

    def feed(self, chunk: str) -> str:
        if self.fmt == TokenFormat.BRACKET:
            return self._feed_bracket(chunk)
        elif self.fmt == TokenFormat.XML:
            return self._feed_xml(chunk)

    def flush(self) -> str:
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

    def _feed_bracket(self, chunk: str) -> str:
        result = []
        for char in chunk:
            if char == "[":
                if self.buffer and not self.in_token:
                    result.append(self.buffer)
                    self.buffer = ""
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
                if self.in_token and len(self.buffer) > self.max_buffer_size:
                    self._stats["buffer_overflows"] += 1
                    result.append(self.buffer)
                    self.buffer = ""
                    self.in_token = False

        if not self.in_token and self.buffer:
            result.append(self.buffer)
            self.buffer = ""

        return "".join(result)

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
                if self.buffer.endswith("/>"):
                    result.append(self._resolve_buffer())
                    self.buffer = ""
                    self.in_token = False
                elif char == ">" and not self.buffer.endswith("/>"):
                    result.append(self.buffer)
                    self.buffer = ""
                    self.in_token = False
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

    def _resolve_buffer(self) -> str:
        token = self.buffer.strip()
        if token in self.mapping:
            self._stats["replaced"] += 1
            return self.mapping[token]
        else:
            self._stats["passed_through"] += 1
            return self.buffer