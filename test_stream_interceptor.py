"""
pytest test_stream_interceptor.py -v

Тестируем StreamInterceptor на:
  1. Нормальных чанках
  2. Чанках по 1 символу (worst case)
  3. Ложных скобках (не наши токены)
  4. Множественных токенах подряд
  5. Злом симуляторе
"""

import pytest
from stream_interceptor import StreamInterceptor, TokenFormat
from llm_simulator import simulate_llm_stream_adversarial


# ── Фикстуры ──────────────────────────────────────────────

MAPPING_BRACKET = {
    "[PER_1]": "Иванов Пётр",
    "[PHONE_1]": "+7 999 123-45-67",
    "[CARD_1]": "4276 1234 5678 9012",
    "[ADDR_1]": "г. Москва, ул. Ленина, д. 5",
}

MAPPING_XML = {
    "<PII_PER_1/>": "Иванов Пётр",
    "<PII_PHONE_1/>": "+7 999 123-45-67",
}


# ── Хелпер ─────────────────────────────────────────────────

def run_interceptor(
        text: str,
        mapping: dict,
        fmt: TokenFormat = TokenFormat.BRACKET,
        chunk_size: int = 1,
) -> str:
    """Прогоняет текст через интерсептор чанками заданного размера."""
    interceptor = StreamInterceptor(mapping, fmt=fmt)
    result_parts = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i : i + chunk_size]
        output = interceptor.feed(chunk)
        result_parts.append(output)
    result_parts.append(interceptor.flush())
    return "".join(result_parts)


# ── Тесты: BRACKET формат ─────────────────────────────────

class TestBracketFormat:

    def test_single_token_whole_chunk(self):
        """Токен приходит целиком одним чанком"""
        interceptor = StreamInterceptor(MAPPING_BRACKET)
        result = interceptor.feed("Привет, [PER_1]!")
        result += interceptor.flush()
        assert result == "Привет, Иванов Пётр!"

    def test_single_token_char_by_char(self):
        """Worst case: каждый символ — отдельный чанк"""
        text = "Привет, [PER_1]!"
        result = run_interceptor(text, MAPPING_BRACKET, chunk_size=1)
        assert result == "Привет, Иванов Пётр!"

    def test_multiple_tokens(self):
        """Несколько токенов в одном тексте"""
        text = "[PER_1], ваш телефон [PHONE_1], карта [CARD_1]."
        result = run_interceptor(text, MAPPING_BRACKET, chunk_size=2)
        assert result == "Иванов Пётр, ваш телефон +7 999 123-45-67, карта 4276 1234 5678 9012."

    def test_unknown_token_passes_through(self):
        """Неизвестный токен проходит как есть"""
        text = "Привет, [UNKNOWN_99]!"
        result = run_interceptor(text, MAPPING_BRACKET, chunk_size=1)
        assert result == "Привет, [UNKNOWN_99]!"

    def test_no_tokens(self):
        """Текст без токенов — проходит без изменений"""
        text = "Просто обычный текст без замен."
        result = run_interceptor(text, MAPPING_BRACKET, chunk_size=3)
        assert result == text

    def test_adjacent_tokens(self):
        """Два токена подряд без пробела"""
        text = "[PER_1][PHONE_1]"
        result = run_interceptor(text, MAPPING_BRACKET, chunk_size=1)
        assert result == "Иванов Пётр+7 999 123-45-67"

    def test_false_bracket_in_text(self):
        """Обычные скобки в тексте (например, в JSON) не должны ломать"""
        text = "Массив [1, 2, 3] и [PER_1]"
        result = run_interceptor(text, MAPPING_BRACKET, chunk_size=2)
        assert "Иванов Пётр" in result
        # [1, 2, 3] — не наш токен, должен пройти как есть
        assert "1, 2, 3" in result

    def test_buffer_overflow_protection(self):
        """Очень длинный 'токен' — сброс буфера"""
        text = "[" + "A" * 100 + "]"
        interceptor = StreamInterceptor(MAPPING_BRACKET, max_buffer_size=50)
        result = interceptor.feed(text)
        result += interceptor.flush()
        assert interceptor.stats["buffer_overflows"] == 1

    def test_stats_counting(self):
        """Проверяем счётчики"""
        text = "[PER_1] и [UNKNOWN_1]"
        interceptor = StreamInterceptor(MAPPING_BRACKET)
        interceptor.feed(text)
        interceptor.flush()
        assert interceptor.stats["replaced"] == 1
        assert interceptor.stats["passed_through"] == 1

    @pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 7, 10, 50])
    def test_various_chunk_sizes(self, chunk_size):
        """Результат не должен зависеть от размера чанков"""
        text = "Здравствуйте, [PER_1]! Ваш номер [PHONE_1]. Адрес: [ADDR_1]."
        expected = "Здравствуйте, Иванов Пётр! Ваш номер +7 999 123-45-67. Адрес: г. Москва, ул. Ленина, д. 5."
        result = run_interceptor(text, MAPPING_BRACKET, chunk_size=chunk_size)
        assert result == expected


# ── Тесты: XML формат ─────────────────────────────────────

class TestXMLFormat:

    def test_xml_single_token(self):
        text = "Привет, <PII_PER_1/>!"
        result = run_interceptor(text, MAPPING_XML, fmt=TokenFormat.XML, chunk_size=1)
        assert result == "Привет, Иванов Пётр!"

    def test_xml_multiple_tokens(self):
        text = "<PII_PER_1/>, телефон <PII_PHONE_1/>"
        result = run_interceptor(text, MAPPING_XML, fmt=TokenFormat.XML, chunk_size=2)
        assert result == "Иванов Пётр, телефон +7 999 123-45-67"

    def test_xml_normal_tags_pass_through(self):
        """Обычные HTML-теги не должны ломаться"""
        text = "<b>Жирный</b> и <PII_PER_1/>"
        result = run_interceptor(text, MAPPING_XML, fmt=TokenFormat.XML, chunk_size=1)
        assert "Иванов Пётр" in result


# ── Тесты: Adversarial (злой симулятор) ────────────────────

class TestAdversarial:

    def test_adversarial_stream(self):
        """Злой симулятор режет токены в самых неудобных местах"""
        text = "Привет, [PER_1]! Звоните: [PHONE_1]. Карта: [CARD_1]."
        expected = "Привет, Иванов Пётр! Звоните: +7 999 123-45-67. Карта: 4276 1234 5678 9012."

        interceptor = StreamInterceptor(MAPPING_BRACKET)
        result_parts = []
        for chunk in simulate_llm_stream_adversarial(text):
            output = interceptor.feed(chunk)
            result_parts.append(output)
        result_parts.append(interceptor.flush())
        result = "".join(result_parts)

        assert result == expected


# ── Тесты: Edge cases ─────────────────────────────────────

class TestEdgeCases:

    def test_empty_input(self):
        interceptor = StreamInterceptor(MAPPING_BRACKET)
        assert interceptor.feed("") == ""
        assert interceptor.flush() == ""

    def test_only_token(self):
        result = run_interceptor("[PER_1]", MAPPING_BRACKET, chunk_size=1)
        assert result == "Иванов Пётр"

    def test_nested_brackets(self):
        """[[PER_1]] — внутренний токен должен отработать"""
        text = "[[PER_1]]"
        result = run_interceptor(text, MAPPING_BRACKET, chunk_size=1)
        # Внешние скобки — мусор, внутренний [PER_1] — наш токен
        assert "Иванов Пётр" in result

    def test_cyrillic_around_token(self):
        """Кириллица вокруг токена"""
        text = "Уважаемый [PER_1], добрый день!"
        result = run_interceptor(text, MAPPING_BRACKET, chunk_size=3)
        assert result == "Уважаемый Иванов Пётр, добрый день!"

    def test_token_at_very_end(self):
        text = "Ваш клиент — [PER_1]"
        result = run_interceptor(text, MAPPING_BRACKET, chunk_size=2)
        assert result == "Ваш клиент — Иванов Пётр"

    def test_repeated_feed_flush_cycle(self):
        """Несколько циклов feed/flush на одном объекте"""
        interceptor = StreamInterceptor(MAPPING_BRACKET)

        r1 = interceptor.feed("Привет, [PER_1]!")
        r1 += interceptor.flush()
        assert r1 == "Привет, Иванов Пётр!"

        r2 = interceptor.feed("Звоните [PHONE_1].")
        r2 += interceptor.flush()
        assert r2 == "Звоните +7 999 123-45-67."