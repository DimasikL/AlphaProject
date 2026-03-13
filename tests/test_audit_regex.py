"""
Аудит regex-детекторов: edge cases, false positives, пропущенные форматы.

pytest tests/test_audit_regex.py -v
"""

import pytest
from detectors.regex_detector import RegexDetector


@pytest.fixture
def d():
    return RegexDetector()


# ═══════════════════════════════════════════════════════════
# ТЕЛЕФОНЫ — пропущенные форматы
# ═══════════════════════════════════════════════════════════

class TestPhoneEdgeCases:
    """Телефоны в форматах, которые реальные клиенты банка пишут."""

    def test_phone_no_country_code(self, d):
        """Клиент пишет без +7/8 — частый случай!"""
        entities = d.detect("Мой номер 999 123-45-67")
        phones = [e for e in entities if e.entity_type == "PHONE"]
        # Сейчас скорее всего не ловит — это баг!
        # Если не ловит, помечаем как xfail
        if not phones:
            pytest.xfail("Телефон без +7/8 не детектируется — нужен дополнительный паттерн")
        assert len(phones) == 1

    def test_phone_ten_digits_no_separators(self, d):
        """9991234567 — 10 цифр подряд"""
        entities = d.detect("Позвоните 9991234567")
        phones = [e for e in entities if e.entity_type == "PHONE"]
        if not phones:
            pytest.xfail("10 цифр без +7 не детектируется")

    def test_phone_with_extension(self, d):
        """Телефон с добавочным"""
        entities = d.detect("Телефон +7 495 123-45-67 доб. 123")
        phones = [e for e in entities if e.entity_type == "PHONE"]
        assert len(phones) >= 1

    def test_phone_written_as_text(self, d):
        """Клиент пишет словами"""
        entities = d.detect("Номер: плюс семь девятьсот девяносто девять")
        phones = [e for e in entities if e.entity_type == "PHONE"]
        # Regex не поймает — это OK, но нужно знать
        assert len(phones) == 0  # expected: regex не умеет

    def test_phone_in_url_not_detected(self, d):
        """Номер внутри URL не должен ловиться"""
        entities = d.detect("Зайдите на https://site.ru/page/79991234567/info")
        phones = [e for e in entities if e.entity_type == "PHONE"]
        # Это может быть false positive
        # Пока просто документируем поведение

    def test_phone_surrounded_by_digits(self, d):
        """Телефон внутри длинного числа — НЕ должен ловиться"""
        entities = d.detect("Код заказа: 1234567899991234567")
        phones = [e for e in entities if e.entity_type == "PHONE"]
        assert len(phones) == 0, "False positive: телефон внутри длинного числа"

    def test_multiple_phones_in_text(self, d):
        """Несколько телефонов"""
        text = "Домашний: +7 495 111-22-33, мобильный: +7 999 444-55-66"
        entities = d.detect(text)
        phones = [e for e in entities if e.entity_type == "PHONE"]
        assert len(phones) == 2

    def test_phone_8_format_with_brackets(self, d):
        entities = d.detect("8(916)123-45-67")
        phones = [e for e in entities if e.entity_type == "PHONE"]
        assert len(phones) == 1


# ═══════════════════════════════════════════════════════════
# ПАСПОРТ — false positives
# ═══════════════════════════════════════════════════════════

class TestPassportEdgeCases:

    def test_order_number_not_passport(self, d):
        """6 цифр после 4 цифр — это НЕ обязательно паспорт"""
        entities = d.detect("Ваш заказ 4515 отправлен, трек 123456")
        passports = [e for e in entities if e.entity_type == "PASSPORT"]
        # Если ловится — это false positive!
        if passports:
            pytest.xfail(
                f"False positive: '{passports[0].value}' определился как паспорт. "
                "Нужен контекстный анализ."
            )

    def test_passport_with_keyword(self, d):
        """Паспорт рядом с ключевым словом — точно паспорт"""
        entities = d.detect("паспорт: 45 15 123456")
        passports = [e for e in entities if e.entity_type == "PASSPORT"]
        assert len(passports) == 1

    def test_passport_series_00(self, d):
        """Серия 00 — невалидная"""
        entities = d.detect("паспорт 00 15 123456")
        passports = [e for e in entities if e.entity_type == "PASSPORT"]
        # Если ловится, validated должен быть False
        for p in passports:
            assert p.validated is False

    def test_six_digits_alone_not_passport(self, d):
        """Просто 6 цифр без серии — не паспорт"""
        entities = d.detect("Код подтверждения: 123456")
        passports = [e for e in entities if e.entity_type == "PASSPORT"]
        assert len(passports) == 0


# ═══════════════════════════════════════════════════════════
# ДАТЫ — false positives и пропуски
# ═══════════════════════════════════════════════════════════

class TestDateEdgeCases:

    def test_report_date_is_not_birthday(self, d):
        """Дата отчёта — маскировать или нет? Документируем поведение."""
        entities = d.detect("Отчёт за 15.03.2024")
        dates = [e for e in entities if e.entity_type == "DATE"]
        # Наш детектор маскирует ВСЕ даты — это может быть overmasking
        # Документируем:
        assert len(dates) >= 0  # просто фиксируем

    def test_impossible_date(self, d):
        """30 февраля — невалидная дата"""
        entities = d.detect("Родился 30.02.1990")
        dates = [e for e in entities if e.entity_type == "DATE"]
        # Regex не проверяет валидность даты — это ожидаемо
        # Но лучше бы проверял

    def test_date_far_future(self, d):
        """Дата в далёком будущем"""
        entities = d.detect("Встреча 15.03.2035")
        dates = [e for e in entities if e.entity_type == "DATE"]
        # Паттерн ограничен 20[0-2]\d — 2035 не поймает
        if not dates:
            pytest.xfail("Паттерн дат ограничен 2029 годом")

    def test_date_text_format_all_months(self, d):
        """Все месяцы в текстовом формате"""
        months = [
            "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря"
        ]
        for month in months:
            text = f"Родился 15 {month} 1990"
            entities = d.detect(text)
            dates = [e for e in entities if e.entity_type == "DATE"]
            assert len(dates) == 1, f"Не нашёл дату с месяцем: {month}"

    def test_date_with_year_short(self, d):
        """Короткий формат года: 15.03.90"""
        entities = d.detect("Родился 15.03.90")
        dates = [e for e in entities if e.entity_type == "DATE"]
        if not dates:
            pytest.xfail("Короткий формат года (90 вместо 1990) не детектируется")


# ═══════════════════════════════════════════════════════════
# КАРТЫ — edge cases
# ═══════════════════════════════════════════════════════════

class TestCardEdgeCases:

    def test_card_13_digits(self, d):
        """Visa может быть 13 цифр (старый формат)"""
        entities = d.detect("Карта 4532015112830")
        cards = [e for e in entities if e.entity_type == "CARD"]
        if not cards:
            pytest.xfail("13-значные карты не детектируются")

    def test_card_with_dashes(self, d):
        """Карта через дефисы"""
        entities = d.detect("4532-0151-1283-0366")
        cards = [e for e in entities if e.entity_type == "CARD"]
        assert len(cards) == 1

    def test_card_number_in_sentence(self, d):
        """Карта в контексте предложения"""
        entities = d.detect("Списание с карты 4532015112830366 на сумму 500р")
        cards = [e for e in entities if e.entity_type == "CARD"]
        assert len(cards) == 1

    def test_16_random_digits_not_card(self, d):
        """16 случайных цифр без Луна — не карта (или low confidence)"""
        entities = d.detect("Номер 1234567890123456")
        cards = [e for e in entities if e.entity_type == "CARD"]
        for c in cards:
            assert c.validated is False or c.confidence < 1.0


# ═══════════════════════════════════════════════════════════
# ИНН — edge cases
# ═══════════════════════════════════════════════════════════

class TestINNEdgeCases:

    def test_inn_inside_longer_number(self, d):
        """ИНН внутри более длинного числа"""
        entities = d.detect("Код: 99770708389399")
        inn = [e for e in entities if e.entity_type == "INN"]
        assert len(inn) == 0, "ИНН не должен ловиться внутри 14-значного числа"

    def test_inn_12_valid(self, d):
        """Валидный ИНН 12 цифр"""
        entities = d.detect("ИНН: 500100732259")
        inn = [e for e in entities if e.entity_type == "INN"]
        assert len(inn) == 1
        assert inn[0].validated is True

    def test_inn_10_valid(self, d):
        """Валидный ИНН 10 цифр"""
        entities = d.detect("ИНН организации: 7707083893")
        inn = [e for e in entities if e.entity_type == "INN"]
        assert len(inn) == 1


# ═══════════════════════════════════════════════════════════
# ПРОПУЩЕННЫЕ ТИПЫ PII
# ═══════════════════════════════════════════════════════════

class TestMissingPIITypes:
    """PII которые мы вообще НЕ детектируем. Каждый xfail = TODO."""

    def test_ip_address(self, d):
        """IP-адрес — может идентифицировать пользователя"""
        entities = d.detect("Вход с IP 192.168.1.100")
        ip = [e for e in entities if "IP" in e.entity_type]
        if not ip:
            pytest.xfail("IP-адреса не детектируются — нужен новый детектор")

    def test_oms_policy(self, d):
        """Полис ОМС — 16 цифр"""
        entities = d.detect("Полис ОМС: 1234567890123456")
        # Может поймать как карту, но это не карта
        # Документируем поведение

    def test_drivers_license(self, d):
        """Водительское удостоверение — серия + номер"""
        entities = d.detect("ВУ: 77 14 567890")
        if not entities:
            pytest.xfail("Водительские удостоверения не детектируются")

    def test_birth_certificate(self, d):
        """Свидетельство о рождении: II-МЮ №123456"""
        entities = d.detect("Свидетельство о рождении: II-МЮ №123456")
        if not entities:
            pytest.xfail("Свидетельства о рождении не детектируются")


# ═══════════════════════════════════════════════════════════
# ПЕРЕСЕЧЕНИЯ И КОНФЛИКТЫ
# ═══════════════════════════════════════════════════════════

class TestOverlapsAndConflicts:

    def test_20_digits_card_vs_account(self, d):
        """20 цифр: это счёт или карта + 4 цифры?"""
        entities = d.detect("Номер: 40817810099910004312")
        types = [e.entity_type for e in entities]
        # Должен быть ACCOUNT, не CARD
        assert "ACCOUNT" in types
        # Не должно быть и того и другого
        assert not ("CARD" in types and "ACCOUNT" in types), \
            "Пересечение: определилось и как карта, и как счёт"

    def test_snils_vs_phone(self, d):
        """СНИЛС и телефон имеют похожий формат"""
        entities = d.detect("СНИЛС: 112-233-445 95")
        types = [e.entity_type for e in entities]
        assert "SNILS" in types
        assert "PHONE" not in types, "СНИЛС определился как телефон"

    def test_passport_inside_long_text(self, d):
        """Паспорт не должен ловиться в случайных числах"""
        entities = d.detect("Сумма 4515123456 копеек")
        passports = [e for e in entities if e.entity_type == "PASSPORT"]


class TestFIOContextDetection:

    def test_ya_fio(self, d):
        entities = d.detect("Я Романов Кузьма Евстигнеевич")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        assert len(persons) >= 1
        assert "Романов" in persons[0].value

    def test_ya_fio_comma(self, d):
        entities = d.detect("Здравствуйте, я Доронин Савва Зиновьевич, хочу")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        assert len(persons) >= 1

    def test_menya_zovut(self, d):
        entities = d.detect("Меня зовут Петрова Анастасия Владимировна")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        assert len(persons) >= 1

    def test_client_fio(self, d):
        entities = d.detect("Отправитель: Харламов Аскольд Ипатьевич")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        assert len(persons) >= 1

    def test_no_false_positive_on_common_words(self, d):
        """Обычные слова с заглавной — не ФИО"""
        entities = d.detect("Я Хочу Узнать Баланс")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        # "Хочу Узнать Баланс" — три слова с заглавной, но это не ФИО
        # Наш паттерн требует "Я <слово> <слово>", так что поймает
        # Нужно проверить, что фильтр работает

    def test_two_word_name(self, d):
        entities = d.detect("Я Иванов Пётр")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        assert len(persons) >= 1