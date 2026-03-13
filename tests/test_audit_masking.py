"""
Аудит MaskingService: дубликаты PII, индексы, реверсивность.

pytest tests/test_audit_masking.py -v
"""

import pytest
from services.masking_service import MaskingService
import concurrent.futures


@pytest.fixture
def svc():
    return MaskingService(use_ner=False)


@pytest.fixture
def svc_ner():
    return MaskingService(use_ner=True)


class TestDuplicatePII:
    """Один и тот же PII встречается несколько раз."""

    def test_same_phone_twice(self, svc):
        text = "Телефон +7 999 123-45-67, повторяю: +7 999 123-45-67"
        result = svc.mask(text)
        # Оба вхождения должны быть замаскированы
        assert "+7 999 123-45-67" not in result.masked_text
        # Но это могут быть разные токены [PHONE_1] и [PHONE_2]
        assert result.stats["total_found"] >= 2

    def test_same_name_twice(self, svc_ner):
        text = "Иванов Пётр подал заявку. Иванов Пётр ждёт ответа."
        result = svc_ner.mask(text)
        assert "Иванов" not in result.masked_text

    def test_same_email_different_context(self, svc):
        text = "Email: test@mail.ru. Подтверждение отправлено на test@mail.ru"
        result = svc.mask(text)
        assert "test@mail.ru" not in result.masked_text


class TestReversibility:
    """Маскирование должно быть полностью обратимым."""

    def test_reverse_phone(self, svc):
        text = "Позвоните +7 999 123-45-67 пожалуйста"
        result = svc.mask(text)
        restored = result.masked_text
        for token, original in result.mapping.items():
            restored = restored.replace(token, original)
        assert restored == text

    def test_reverse_complex(self, svc_ner):
        text = (
            "Я Иванов Пётр, телефон +7 999 123-45-67, "
            "email ivan@mail.ru, дата рождения 15.03.1990"
        )
        result = svc_ner.mask(text)
        restored = result.masked_text
        for token, original in result.mapping.items():
            restored = restored.replace(token, original)
        assert restored == text, (
            f"Не удалось восстановить!\n"
            f"Original: {text}\n"
            f"Masked:   {result.masked_text}\n"
            f"Restored: {restored}\n"
            f"Mapping:  {result.mapping}"
        )

    def test_reverse_no_pii(self, svc):
        text = "Какой курс доллара?"
        result = svc.mask(text)
        assert result.masked_text == text
        assert result.mapping == {}


class TestEmptyAndEdgeCases:

    def test_empty_text(self, svc):
        result = svc.mask("")
        assert result.masked_text == ""
        assert result.mapping == {}

    def test_whitespace_only(self, svc):
        result = svc.mask("   \n\t  ")
        assert result.mapping == {}

    def test_only_pii(self, svc):
        """Текст состоит только из PII"""
        result = svc.mask("+7 999 123-45-67")
        assert "+7 999 123-45-67" not in result.masked_text
        assert len(result.mapping) == 1

    def test_very_long_text(self, svc):
        """Длинный текст с множеством PII"""
        base = "Клиент +7 999 {num:03d}-{num:02d}-{num:02d}, email user{num}@mail.ru. "
        text = "".join(base.format(num=i) for i in range(50))
        result = svc.mask(text)
        assert result.stats["total_found"] >= 50  # минимум 50 email

    def test_pii_at_text_boundaries(self, svc):
        """PII в самом начале и в самом конце"""
        text = "+7 999 111-22-33 текст посередине test@mail.ru"
        result = svc.mask(text)
        assert "+7 999 111-22-33" not in result.masked_text
        assert "test@mail.ru" not in result.masked_text

    def test_pii_no_spaces_around(self, svc):
        """PII без пробелов вокруг"""
        text = "тел:+7 999 123-45-67,email:test@mail.ru"
        result = svc.mask(text)
        # Проверяем что хотя бы что-то нашлось
        assert result.stats["total_found"] >= 1


class TestMaskingConsistency:
    """Маскирование должно быть детерминированным в рамках одного вызова."""

    def test_counters_reset_between_calls(self, svc):
        """Счётчики сбрасываются между вызовами mask()"""
        r1 = svc.mask("Телефон +7 999 111-22-33")
        r2 = svc.mask("Телефон +7 999 444-55-66")
        # Оба должны иметь [PHONE_1], не [PHONE_1] и [PHONE_2]
        assert "[PHONE_1]" in r1.masked_text
        assert "[PHONE_1]" in r2.masked_text

    def test_different_pii_get_different_tokens(self, svc):
        """Разные PII → разные токены"""
        result = svc.mask("Телефон +7 999 111-22-33 и email test@mail.ru")
        tokens = list(result.mapping.keys())
        assert len(set(tokens)) == len(tokens), "Дубликаты токенов!"

class TestConcurrentMasking:
    """Проверяем что маскирование потокобезопасно."""

    def test_concurrent_requests(self):
        """10 параллельных запросов не ломают друг друга."""
        service = MaskingService(use_ner=True)
        texts = [
            f"Я Иванов-{i}, телефон +7 999 {i:03d}-{i:02d}-{i:02d}"
            for i in range(10)
        ]
        errors = []
        results = []

        def mask_text(text):
            try:
                result = service.mask(text)
                return result
            except Exception as e:
                errors.append(str(e))
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(mask_text, t) for t in texts]
            results = [f.result() for f in futures]

        assert len(errors) == 0, f"Ошибки при конкурентном маскировании: {errors}"
        assert all(r is not None for r in results)
        # Каждый результат должен содержать замаскированный телефон
        for r in results:
            assert r.stats.get("total_found", 0) >= 1

class TestSessionCounters:
    """Счётчики уникальны в рамках сессии."""

    def test_different_persons_get_different_tokens(self):
        from services.session_store import Session

        service = MaskingService(use_ner=True)
        session = Session(session_id="test")

        r1 = service.mask("Я Иванов Пётр, тел +7 999 111-22-33", session=session)
        r2 = service.mask("Я Козлова Мария, тел +7 916 444-55-66", session=session)

        # Токены не должны пересекаться
        tokens_1 = set(r1.mapping.keys())
        tokens_2 = set(r2.mapping.keys())
        assert tokens_1.isdisjoint(tokens_2), (
            f"Токены пересекаются!\n"
            f"Msg 1: {tokens_1}\n"
            f"Msg 2: {tokens_2}"
        )

        # PERSON_1 = Иванов, PERSON_2 = Козлова (не наоборот)
        all_mapping = {**r1.mapping, **r2.mapping}
        person_tokens = {k: v for k, v in all_mapping.items() if "PERSON" in k}
        assert len(person_tokens) >= 2, "Должно быть минимум 2 разных PERSON токена"

    def test_session_mapping_no_overwrite(self):
        from services.session_store import Session

        service = MaskingService(use_ner=False)
        session = Session(session_id="test")

        r1 = service.mask("Тел +7 999 111-22-33", session=session)
        r2 = service.mask("Тел +7 916 444-55-66", session=session)

        # Мерж маппингов
        session.merge_mapping(r1.mapping)
        session.merge_mapping(r2.mapping)

        # Оба телефона сохранены
        values = list(session.mapping.values())
        assert "+7 999 111-22-33" in values
        assert "+7 916 444-55-66" in values

    def test_counters_increment(self):
        from services.session_store import Session

        session = Session(session_id="test")
        t1 = session.next_token("PHONE")
        t2 = session.next_token("PHONE")
        t3 = session.next_token("PERSON")

        assert t1 == "[PHONE_1]"
        assert t2 == "[PHONE_2]"
        assert t3 == "[PERSON_1]"

    def test_without_session_counters_reset(self):
        """Без сессии — счётчики сбрасываются (обратная совместимость)."""
        service = MaskingService(use_ner=False)

        r1 = service.mask("Тел +7 999 111-22-33")
        r2 = service.mask("Тел +7 916 444-55-66")

        assert "[PHONE_1]" in r1.masked_text
        assert "[PHONE_1]" in r2.masked_text  # оба _1, т.к. без сессии