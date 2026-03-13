"""
End-to-end тесты: полный цикл маскирование → LLM → размаскирование.

pytest tests/test_audit_e2e.py -v
"""

import re
import pytest
from services.masking_service import MaskingService
from services.unmasking_stream import StreamInterceptor, TokenFormat
from mocks.llm_simulator import generate_llm_response


class TestFullPipeline:
    """Полный цикл без API."""

    def _run_pipeline(self, user_message: str) -> dict:
        """Прогоняет полный цикл: mask → LLM → unmask."""
        service = MaskingService(use_ner=True)
        mask_result = service.mask(user_message)

        llm_response = generate_llm_response(mask_result.masked_text)

        interceptor = StreamInterceptor(mask_result.mapping)
        clean_response = interceptor.feed(llm_response)
        clean_response += interceptor.flush()

        return {
            "original": user_message,
            "masked": mask_result.masked_text,
            "llm_raw": llm_response,
            "clean": clean_response,
            "mapping": mask_result.mapping,
            "stats": mask_result.stats,
            "interceptor_stats": interceptor.stats,
        }

    def test_balance_query(self):
        result = self._run_pipeline(
            "Здравствуйте, я Иванов Пётр, телефон +7 999 123-45-67. Какой баланс?"
        )
        # Оригинальные PII НЕ должны быть в masked
        assert "Иванов" not in result["masked"]
        assert "+7 999 123-45-67" not in result["masked"]

        # Токены НЕ должны быть в clean ответе
        tokens = re.findall(r'\[[A-Z]+_\d+\]', result["clean"])
        assert len(tokens) == 0, f"Утечка: {tokens}"

    def test_transfer_query(self):
        result = self._run_pipeline(
            "Переведите 5000 рублей Сидорову Алексею на карту 4532 0151 1283 0366"
        )
        assert "Сидоров" not in result["masked"]
        tokens = re.findall(r'\[[A-Z]+_\d+\]', result["clean"])
        assert len(tokens) == 0

    def test_complex_query(self):
        result = self._run_pipeline(
            "Я Петров Алексей Сергеевич, паспорт 45 15 123456, "
            "телефон +7 916 555-44-33, email petrov@gmail.com, "
            "дата рождения 01.05.1985"
        )
        assert result["stats"]["total_found"] >= 4

        # Ни один PII не должен утечь
        for token, original in result["mapping"].items():
            assert original not in result["masked"], \
                f"PII '{original}' утёк в masked text"

    def test_no_pii_passthrough(self):
        """Текст без PII проходит без изменений"""
        result = self._run_pipeline("Какой курс доллара сегодня?")
        assert result["masked"] == "Какой курс доллара сегодня?"
        assert result["stats"]["total_found"] == 0

    def test_pipeline_idempotent(self):
        """Повторное маскирование уже замаскированного текста"""
        service = MaskingService(use_ner=True)
        r1 = service.mask("Я Иванов, тел +7 999 123-45-67")

        # Маскируем ещё раз уже замаскированный текст
        r2 = service.mask(r1.masked_text)
        # Токены [PERSON_1] не должны определяться как PII
        assert r2.stats["total_found"] == 0, \
            f"Замаскированные токены определились как PII: {r2.entities_found}"


class TestPIILeakageAudit:
    """Проверяем что PII НИКОГДА не утекают."""

    DANGEROUS_MESSAGES = [
        "Иванов Пётр Сергеевич, +7 999 123-45-67",
        "Паспорт 4515 123456, СНИЛС 112-233-445 95",
        "Карта 4532 0151 1283 0366, email test@mail.ru",
        "Дата рождения 15.03.1990, ИНН 7707083893",
        "Козлова Мария, адрес: г. Москва, ул. Ленина, д. 5",
    ]

    @pytest.mark.parametrize("message", DANGEROUS_MESSAGES)
    def test_no_pii_in_masked_text(self, message):
        service = MaskingService(use_ner=True)
        result = service.mask(message)

        for token, original in result.mapping.items():
            assert original not in result.masked_text, \
                f"УТЕЧКА! '{original}' осталась в замаскированном тексте"

    @pytest.mark.parametrize("message", DANGEROUS_MESSAGES)
    def test_no_tokens_in_clean_response(self, message):
        service = MaskingService(use_ner=True)
        result = service.mask(message)

        llm_response = generate_llm_response(result.masked_text)

        interceptor = StreamInterceptor(result.mapping)
        clean = interceptor.feed(llm_response)
        clean += interceptor.flush()

        tokens = re.findall(r'\[[A-Z]+_\d+\]', clean)
        assert len(tokens) == 0, \
            f"УТЕЧКА ТОКЕНОВ в ответе: {tokens}"