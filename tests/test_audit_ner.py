"""
Аудит NER-детектора: падежи, инициалы, edge cases.

pytest tests/test_audit_ner.py -v
"""

import pytest
from detectors.ner_detector import NatashaDetector


@pytest.fixture(scope="module")
def ner():
    """Создаём один раз — инициализация тяжёлая."""
    return NatashaDetector()


class TestNameForms:
    """ФИО в разных формах — ловим ли?"""

    def test_nominative(self, ner):
        """Именительный: Иванов Пётр Сергеевич"""
        entities = ner.detect("Я Иванов Пётр Сергеевич")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        assert len(persons) >= 1

    def test_dative(self, ner):
        """Дательный: Иванову Петру Сергеевичу"""
        entities = ner.detect("Переведите Иванову Петру Сергеевичу")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        if not persons:
            pytest.xfail("NER не ловит ФИО в дательном падеже")
        assert len(persons) >= 1

    def test_genitive(self, ner):
        """Родительный: от Иванова Петра Сергеевича"""
        entities = ner.detect("Заявление от Иванова Петра Сергеевича")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        assert len(persons) >= 1

    def test_instrumental(self, ner):
        """Творительный: Ивановым Петром"""
        entities = ner.detect("Подписано Ивановым Петром Сергеевичем")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        if not persons:
            pytest.xfail("NER не ловит ФИО в творительном падеже")

    def test_first_name_only(self, ner):
        """Только имя: Пётр"""
        entities = ner.detect("Здравствуйте, Пётр!")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        # Одно имя без фамилии — может не определиться
        # Документируем
        if not persons:
            pytest.xfail("Одиночное имя без фамилии не детектируется")

    def test_last_name_only(self, ner):
        """Только фамилия: Иванов"""
        entities = ner.detect("Клиент Иванов обратился в банк")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        if not persons:
            pytest.xfail("Одиночная фамилия не детектируется")

    def test_initials_before_surname(self, ner):
        """И.П. Сергеев"""
        entities = ner.detect("Клиент И.П. Сергеев подал заявку")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        if not persons:
            pytest.xfail("Инициалы + фамилия не детектируются")

    def test_initials_after_surname(self, ner):
        """Сергеев И.П."""
        entities = ner.detect("Получатель: Сергеев И.П.")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        if not persons:
            pytest.xfail("Фамилия + инициалы не детектируются")

    def test_double_surname(self, ner):
        """Двойная фамилия: Петров-Водкин"""
        entities = ner.detect("Клиент Петров-Водкин Александр")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        if not persons:
            pytest.xfail("Двойные фамилии не детектируются")

    def test_female_name(self, ner):
        """Женское ФИО"""
        entities = ner.detect("Козлова Мария Ивановна подала заявку")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        assert len(persons) >= 1

    def test_two_persons_in_text(self, ner):
        """Два разных человека в одном тексте"""
        entities = ner.detect(
            "Переведите от Иванова Петра на счёт Сидоровой Анны"
        )
        persons = [e for e in entities if e.entity_type == "PERSON"]
        assert len(persons) >= 2, f"Нашли только {len(persons)} из 2 персон"


class TestAddressDetection:
    """Адреса — сложнейший тип PII."""

    def test_full_address(self, ner):
        entities = ner.detect("Адрес: г. Москва, ул. Ленина, д. 5, кв. 10")
        addresses = [e for e in entities if e.entity_type == "ADDRESS"]
        if not addresses:
            pytest.xfail("Полный адрес не детектируется через NER")

    def test_city_only(self, ner):
        entities = ner.detect("Я из Москвы")
        addresses = [e for e in entities if e.entity_type == "ADDRESS"]
        # Город один — может или не может быть PII

    def test_address_without_keyword(self, ner):
        """Адрес без слова 'адрес'"""
        entities = ner.detect("Живу на Тверской улице, дом 12")
        addresses = [e for e in entities if e.entity_type == "ADDRESS"]



class TestNERFalsePositives:

    def test_product_name_not_person(self, ner):
        """Глаголы и продукты банка — не ФИО"""
        entities = ner.detect("Подключите мне Альфа-Карту Premium")
        persons = [e for e in entities if e.entity_type == "PERSON"]
        assert len(persons) == 0, (
            f"False positive: {[e.value for e in persons]} определились как персона"
        )

    def test_verbs_not_person(self, ner):
        """Глаголы повелительного наклонения — не ФИО"""
        verbs = [
            "Переведите деньги",
            "Покажите баланс",
            "Проверьте статус",
            "Заблокируйте карту",
        ]
        for text in verbs:
            entities = ner.detect(text)
            persons = [e for e in entities if e.entity_type == "PERSON"]
            assert len(persons) == 0, f"'{text}': {[e.value for e in persons]} = false positive"