"""pytest tests/test_masking_service.py -v"""

import pytest
from services.masking_service import MaskingService


@pytest.fixture
def service():
    # use_ner=False для быстрых тестов (без Natasha)
    return MaskingService(use_ner=False)


@pytest.fixture
def service_with_ner():
    return MaskingService(use_ner=True)


class TestMaskingBasic:
    def test_mask_phone(self, service):
        result = service.mask("Звоните +7 999 123-45-67")
        assert "+7 999 123-45-67" not in result.masked_text
        assert "[PHONE_1]" in result.masked_text
        assert result.mapping["[PHONE_1]"] == "+7 999 123-45-67"

    def test_mask_email(self, service):
        result = service.mask("Пишите на ivan@mail.ru")
        assert "ivan@mail.ru" not in result.masked_text
        assert "[EMAIL_1]" in result.masked_text

    def test_mask_date(self, service):
        result = service.mask("Родился 15.03.1990")
        assert "15.03.1990" not in result.masked_text
        assert "[DATE_1]" in result.masked_text

    def test_no_pii(self, service):
        text = "Какой курс доллара?"
        result = service.mask(text)
        assert result.masked_text == text
        assert result.mapping == {}

    def test_multiple_pii(self, service):
        text = "Телефон +7 999 123-45-67, email test@mail.ru"
        result = service.mask(text)
        assert "+7 999 123-45-67" not in result.masked_text
        assert "test@mail.ru" not in result.masked_text
        assert len(result.mapping) == 2

    def test_stats(self, service):
        text = "Телефон +7 999 123-45-67, ещё +7 916 555-44-33"
        result = service.mask(text)
        assert result.stats["total_found"] == 2
        assert result.stats["by_type"]["PHONE"] == 2

    def test_mapping_is_reversible(self, service):
        text = "Позвоните +7 999 123-45-67 пожалуйста"
        result = service.mask(text)
        # Восстанавливаем текст из маскированного + mapping
        restored = result.masked_text
        for token, original in result.mapping.items():
            restored = restored.replace(token, original)
        assert restored == text


class TestMaskingWithNER:
    def test_mask_person_name(self, service_with_ner):
        result = service_with_ner.mask("Здравствуйте, я Иванов Пётр Сергеевич")
        assert "Иванов" not in result.masked_text
        assert any("PERSON" in key for key in result.mapping)

    def test_mask_person_and_phone(self, service_with_ner):
        text = "Я Иванов Пётр, мой телефон +7 999 123-45-67"
        result = service_with_ner.mask(text)
        assert "Иванов" not in result.masked_text
        assert "+7 999 123-45-67" not in result.masked_text
        assert len(result.mapping) >= 2

    def test_full_bank_request(self, service_with_ner):
        text = (
            "Здравствуйте, я Петров Алексей Сергеевич, "
            "паспорт 45 15 123456, "
            "телефон +7 916 555-44-33, "
            "email petrov@gmail.com, "
            "дата рождения 01.05.1985. "
            "Переведите на карту 4532 0151 1283 0366"
        )
        result = service_with_ner.mask(text)

        # Ничего личного не должно остаться
        assert "Петров" not in result.masked_text
        assert "Алексей" not in result.masked_text
        assert "45 15 123456" not in result.masked_text
        assert "+7 916 555-44-33" not in result.masked_text
        assert "petrov@gmail.com" not in result.masked_text
        assert "01.05.1985" not in result.masked_text
        assert "4532 0151 1283 0366" not in result.masked_text

        # Маппинг должен содержать все замены
        assert len(result.mapping) >= 5

        print("\n=== Результат маскирования ===")
        print(f"Оригинал:     {text}")
        print(f"Маскировано:  {result.masked_text}")
        print(f"Mapping:      {result.mapping}")
        print(f"Статистика:   {result.stats}")