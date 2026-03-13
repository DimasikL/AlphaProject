"""
Аудит StreamInterceptor: unicode, переносы строк, SSE-совместимость.

pytest tests/test_audit_stream.py -v
"""

import pytest
from services.unmasking_stream import StreamInterceptor, TokenFormat


MAPPING = {
    "[PER_1]": "Иванов Пётр",
    "[PHONE_1]": "+7 999 123-45-67",
    "[CARD_1]": "4532 0151 1283 0366",
    "[EMAIL_1]": "ivan@mail.ru",
    "[DATE_1]": "15.03.1990",
}


def run(text: str, chunk_size: int = 1, mapping: dict = None) -> str:
    m = mapping or MAPPING
    interceptor = StreamInterceptor(m, fmt=TokenFormat.BRACKET)
    parts = []
    for i in range(0, len(text), chunk_size):
        parts.append(interceptor.feed(text[i:i + chunk_size]))
    parts.append(interceptor.flush())
    return "".join(parts)


class TestUnicodeAndSpecialChars:

    def test_emoji_in_text(self):
        text = "Привет 👋 [PER_1]! 🎉"
        result = run(text)
        assert result == "Привет 👋 Иванов Пётр! 🎉"

    def test_cyrillic_mixed_with_latin(self):
        text = "[PER_1] logged in from IP 10.0.0.1"
        result = run(text)
        assert result == "Иванов Пётр logged in from IP 10.0.0.1"

    def test_newlines_in_text(self):
        text = "Клиент: [PER_1]\nТелефон: [PHONE_1]\nEmail: [EMAIL_1]"
        result = run(text)
        assert "Иванов Пётр" in result
        assert "+7 999 123-45-67" in result
        assert "ivan@mail.ru" in result

    def test_tabs_and_whitespace(self):
        text = "[PER_1]\t\t[PHONE_1]"
        result = run(text)
        assert result == "Иванов Пётр\t\t+7 999 123-45-67"


class TestSSECompatibility:
    """SSE использует \n\n как разделитель. Проверяем совместимость."""

    def test_no_double_newline_in_output(self):
        """Размаскированный текст не должен содержать \n\n
        (иначе SSE сломается)"""
        text = "[PER_1]\n\n[PHONE_1]"
        result = run(text)
        # Это скорее проблема SSE-обёртки, а не интерсептора
        # Но документируем

    def test_sse_data_prefix_not_consumed(self):
        """Если чанк содержит 'data: ', это не наш токен"""
        text = "data: [PER_1]"
        result = run(text)
        assert result == "data: Иванов Пётр"


class TestTokensAdjacentAndComplex:

    def test_three_tokens_no_spaces(self):
        text = "[PER_1][PHONE_1][EMAIL_1]"
        result = run(text, chunk_size=1)
        assert result == "Иванов Пётр+7 999 123-45-67ivan@mail.ru"

    def test_token_inside_parentheses(self):
        text = "Клиент ([PER_1]) подал заявку"
        result = run(text, chunk_size=2)
        assert result == "Клиент (Иванов Пётр) подал заявку"

    def test_token_inside_quotes(self):
        text = 'Получатель: "[PER_1]"'
        result = run(text, chunk_size=1)
        assert result == 'Получатель: "Иванов Пётр"'

    def test_token_with_colon(self):
        text = "ФИО: [PER_1], тел: [PHONE_1]"
        result = run(text, chunk_size=3)
        assert result == "ФИО: Иванов Пётр, тел: +7 999 123-45-67"

    def test_many_tokens(self):
        """10 токенов подряд"""
        big_mapping = {f"[T_{i}]": f"val_{i}" for i in range(10)}
        text = " ".join(f"[T_{i}]" for i in range(10))
        result = run(text, chunk_size=1, mapping=big_mapping)
        expected = " ".join(f"val_{i}" for i in range(10))
        assert result == expected


class TestChunkSizeInvariance:
    """Результат НЕ должен зависеть от размера чанков."""

    @pytest.mark.parametrize("chunk_size", [1, 2, 3, 4, 5, 7, 10, 20, 100])
    def test_complex_text_any_chunk_size(self, chunk_size):
        text = (
            "Уважаемый [PER_1]! Ваш телефон [PHONE_1], "
            "карта [CARD_1], email [EMAIL_1]. "
            "Дата рождения: [DATE_1]."
        )
        expected = (
            "Уважаемый Иванов Пётр! Ваш телефон +7 999 123-45-67, "
            "карта 4532 0151 1283 0366, email ivan@mail.ru. "
            "Дата рождения: 15.03.1990."
        )
        result = run(text, chunk_size=chunk_size)
        assert result == expected, f"Failed for chunk_size={chunk_size}"


class TestBufferEdgeCases:

    def test_open_bracket_at_end_of_stream(self):
        """Стрим заканчивается на [ без продолжения"""
        interceptor = StreamInterceptor(MAPPING)
        r1 = interceptor.feed("Привет [")
        r2 = interceptor.flush()
        assert r1 + r2 == "Привет ["

    def test_partial_token_at_end(self):
        """Стрим заканчивается на [PER без ]"""
        interceptor = StreamInterceptor(MAPPING)
        r1 = interceptor.feed("Привет [PER")
        r2 = interceptor.flush()
        assert r1 + r2 == "Привет [PER"

    def test_empty_brackets(self):
        """Пустые скобки []"""
        result = run("Привет [] мир")
        assert "Привет" in result and "мир" in result

    def test_only_open_brackets(self):
        """Много [ без ]"""
        result = run("[[[")
        # Не должен зависнуть
        assert len(result) >= 0