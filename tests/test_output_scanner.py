"""pytest tests/test_output_scanner.py -v"""

import pytest
from services.output_scanner import OutputScanner


@pytest.fixture
def scanner():
    return OutputScanner(use_ner=False)


class TestOutputScanning:

    def test_no_leak(self, scanner):
        response = "Ваш баланс: 45 000 руб."
        mapping = {"[PHONE_1]": "+7 999 123-45-67"}
        leaked = scanner.scan(response, mapping)
        assert len(leaked) == 0

    def test_known_pii_not_flagged(self, scanner):
        """PII которые были в запросе клиента — не считаются утечкой"""
        response = "Ваш телефон +7 999 123-45-67 подтверждён"
        mapping = {"[PHONE_1]": "+7 999 123-45-67"}
        leaked = scanner.scan(response, mapping)
        assert len(leaked) == 0

    def test_unknown_phone_flagged(self, scanner):
        """Новый телефон в ответе LLM — утечка"""
        response = "Позвоните по номеру +7 495 111-22-33"
        mapping = {"[PHONE_1]": "+7 999 123-45-67"}
        leaked = scanner.scan(response, mapping)
        assert len(leaked) >= 1
        assert leaked[0].entity_type == "PHONE"

    def test_unknown_email_flagged(self, scanner):
        response = "Пишите на support@secret-bank.ru"
        mapping = {}
        leaked = scanner.scan(response, mapping)
        assert any(e.entity_type == "EMAIL" for e in leaked)

    def test_mask_leaked_pii(self, scanner):
        response = "Позвоните +7 495 111-22-33 для уточнения"
        mapping = {}
        leaked = scanner.scan(response, mapping)
        cleaned = scanner.mask_leaked(response, leaked)
        assert "+7 495 111-22-33" not in cleaned
        assert "[ДАННЫЕ СКРЫТЫ]" in cleaned

    def test_empty_response(self, scanner):
        leaked = scanner.scan("", {})
        assert len(leaked) == 0

    def test_no_leak_plain_text(self, scanner):
        response = "Спасибо за обращение. Хорошего дня!"
        leaked = scanner.scan(response, {})
        assert len(leaked) == 0