"""pytest tests/test_regex_detector.py -v"""

import pytest
from detectors.regex_detector import RegexDetector


@pytest.fixture
def detector():
    return RegexDetector()


class TestPhoneDetection:
    def test_plus7_format(self, detector):
        entities = detector.detect("Звоните: +7 999 123-45-67")
        phones = [e for e in entities if e.entity_type == "PHONE"]
        assert len(phones) == 1
        assert "999" in phones[0].value

    def test_8_format(self, detector):
        entities = detector.detect("Телефон: 8(495)123-45-67")
        phones = [e for e in entities if e.entity_type == "PHONE"]
        assert len(phones) == 1

    def test_no_false_positive_short_number(self, detector):
        entities = detector.detect("Код 12345")
        phones = [e for e in entities if e.entity_type == "PHONE"]
        assert len(phones) == 0

    def test_phone_with_brackets(self, detector):
        entities = detector.detect("+7(916)555-44-33")
        phones = [e for e in entities if e.entity_type == "PHONE"]
        assert len(phones) == 1


class TestEmailDetection:
    def test_simple_email(self, detector):
        entities = detector.detect("Пишите на ivan@mail.ru")
        emails = [e for e in entities if e.entity_type == "EMAIL"]
        assert len(emails) == 1
        assert emails[0].value == "ivan@mail.ru"

    def test_complex_email(self, detector):
        entities = detector.detect("email: user.name+tag@example.co.uk")
        emails = [e for e in entities if e.entity_type == "EMAIL"]
        assert len(emails) == 1


class TestPassportDetection:
    def test_passport_with_space(self, detector):
        entities = detector.detect("Паспорт 45 15 123456")
        passports = [e for e in entities if e.entity_type == "PASSPORT"]
        assert len(passports) == 1

    def test_passport_series_space_number(self, detector):
        """Серия слитно + пробел + номер"""
        entities = detector.detect("Паспорт 4515 123456")
        passports = [e for e in entities if e.entity_type == "PASSPORT"]
        assert len(passports) == 1

    def test_passport_no_space_at_all(self, detector):
        """10 цифр подряд БЕЗ пробелов — НЕ должен быть паспортом
        (слишком много false positives)"""
        entities = detector.detect("Номер 4515123456")
        passports = [e for e in entities if e.entity_type == "PASSPORT"]
        assert len(passports) == 0, "10 цифр подряд ошибочно определились как паспорт"


class TestSNILSDetection:
    def test_snils_standard(self, detector):
        entities = detector.detect("СНИЛС 112-233-445 95")
        snils = [e for e in entities if e.entity_type == "SNILS"]
        assert len(snils) == 1

    def test_snils_dashes(self, detector):
        entities = detector.detect("СНИЛС: 112-233-445-95")
        snils = [e for e in entities if e.entity_type == "SNILS"]
        assert len(snils) == 1


class TestDateDetection:
    def test_dot_format(self, detector):
        entities = detector.detect("Дата рождения: 15.03.1990")
        dates = [e for e in entities if e.entity_type == "DATE"]
        assert len(dates) == 1
        assert dates[0].value == "15.03.1990"

    def test_text_format(self, detector):
        entities = detector.detect("Родился 1 января 1990 года")
        dates = [e for e in entities if e.entity_type == "DATE"]
        assert len(dates) == 1

    def test_slash_format(self, detector):
        entities = detector.detect("DOB: 25/12/1985")
        dates = [e for e in entities if e.entity_type == "DATE"]
        assert len(dates) == 1


class TestCardDetection:
    def test_card_with_spaces(self, detector):
        entities = detector.detect("Карта: 4532 0151 1283 0366")
        cards = [e for e in entities if e.entity_type == "CARD"]
        assert len(cards) == 1
        assert cards[0].validated is True

    def test_card_no_spaces(self, detector):
        entities = detector.detect("Карта 4532015112830366")
        cards = [e for e in entities if e.entity_type == "CARD"]
        assert len(cards) == 1


class TestComplexText:
    def test_multiple_pii_types(self, detector):
        text = (
            "Здравствуйте, мой паспорт 45 15 123456, "
            "телефон +7 999 123-45-67, "
            "email test@mail.ru, "
            "дата рождения 15.03.1990"
        )
        entities = detector.detect(text)
        types = {e.entity_type for e in entities}
        assert "PASSPORT" in types
        assert "PHONE" in types
        assert "EMAIL" in types
        assert "DATE" in types

    def test_no_pii(self, detector):
        text = "Добрый день, хочу узнать курс доллара."
        entities = detector.detect(text)
        assert len(entities) == 0


class TestINNEdgeCases:

    def test_inn_inside_longer_number(self, detector):
        """ИНН внутри более длинного числа"""
        entities = detector.detect("Код: 99770708389399")
        inn = [e for e in entities if e.entity_type == "INN"]
        assert len(inn) == 0, "ИНН не должен ловиться внутри 14-значного числа"

    def test_inn_12_valid(self, detector):
        """Валидный ИНН 12 цифр"""
        entities = detector.detect("ИНН: 500100732259")
        inn = [e for e in entities if e.entity_type == "INN"]
        assert len(inn) == 1
        assert inn[0].validated is True

    def test_inn_10_valid(self, detector):
        """Валидный ИНН 10 цифр — должен побеждать паспорт при пересечении"""
        entities = detector.detect("ИНН организации: 7707083893")
        inn = [e for e in entities if e.entity_type == "INN"]
        assert len(inn) == 1
        assert inn[0].validated is True
        passports = [e for e in entities if e.entity_type == "PASSPORT"]
        assert len(passports) == 0, "ИНН определился как паспорт вместо ИНН"

    def test_inn_beats_passport_on_overlap(self, detector):
        """Когда 10 цифр подряд — ИНН с чексуммой побеждает паспорт без чексуммы"""
        entities = detector.detect("7707083893")
        types = [e.entity_type for e in entities]
        if "INN" in types:
            assert "PASSPORT" not in types, "И ИНН и паспорт одновременно"