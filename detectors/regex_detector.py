"""
Regex-детекторы для PII в русскоязычных текстах.
Каждый детектор возвращает список найденных сущностей с позициями.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from detectors.checksum_validator import (
    is_valid_card_luhn,
    is_valid_inn,
    is_valid_snils,
    is_valid_passport_series,
    is_valid_account_number,
)


@dataclass
class PIIEntity:
    """Найденная PII-сущность."""
    entity_type: str
    value: str
    start: int
    end: int
    confidence: float = 1.0
    validated: bool = False

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)


class RegexDetector:

    # ── Приоритет типов при пересечениях ───────────────────
    # Чем выше число, тем выше приоритет.
    # ИНН с контрольной суммой надёжнее паспорта без контекста.
    TYPE_PRIORITY = {
        "INN": 10,       # контрольная сумма → максимальная надёжность
        "SNILS": 10,     # контрольная сумма
        "CARD": 9,       # алгоритм Луна
        "ACCOUNT": 8,    # проверка префикса
        "PHONE": 7,      # специфичный формат (+7/8)
        "EMAIL": 7,      # специфичный формат (@)
        "PASSPORT": 5,   # просто паттерн цифр, нет чексуммы
        "DATE": 4,       # распространённый формат, много false positives
    }

    # ── Паттерны ───────────────────────────────────────────

    PHONE_PATTERNS = [
        re.compile(
            r'(?<!\d)'
            r'(\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
            r'(?!\d)'
        ),
    ]

    EMAIL_PATTERN = re.compile(
        r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
        re.IGNORECASE
    )

    PASSPORT_PATTERNS = [
        # С разделителем между серией и номером: 45 15 123456
        re.compile(
            r'(?<!\d)'
            r'(\d{2}[\s\-]\d{2})[\s\-]?(?:№\s?)?(\d{6})'
            r'(?!\d)'
        ),
        # Серия слитно + пробел/дефис + номер: 4515 123456
        re.compile(
            r'(?<!\d)'
            r'(\d{4})[\s\-](?:№\s?)?(\d{6})'
            r'(?!\d)'
        ),
    ]

    SNILS_PATTERNS = [
        re.compile(
            r'(?<!\d)'
            r'\d{3}[\s\-]\d{3}[\s\-]\d{3}[\s\-]?\d{2}'
            r'(?!\d)'
        ),
    ]

    INN_PATTERNS = [
        re.compile(r'(?<!\d)(\d{12})(?!\d)'),
        re.compile(r'(?<!\d)(\d{10})(?!\d)'),
    ]

    CARD_PATTERNS = [
        re.compile(
            r'(?<!\d)'
            r'\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}'
            r'(?!\d)'
        ),
    ]

    ACCOUNT_PATTERNS = [
        re.compile(
            r'(?<!\d)'
            r'\d{20}'
            r'(?!\d)'
        ),
    ]

    DATE_PATTERNS = [
        re.compile(
            r'(?<!\d)'
            r'(0[1-9]|[12]\d|3[01])[\.\/\-](0[1-9]|1[0-2])[\.\/\-](19\d{2}|20[0-2]\d)'
            r'(?!\d)'
        ),
        re.compile(
            r'(\d{1,2})\s+'
            r'(января|февраля|марта|апреля|мая|июня|'
            r'июля|августа|сентября|октября|ноября|декабря)\s+'
            r'(\d{4})\s*(?:г\.?|года)?',
            re.IGNORECASE
        ),
    ]

    FIO_CONTEXT_PATTERNS = [
        # "Я Фамилия Имя Отчество" / "я Фамилия Имя"
        re.compile(
            r'(?:^|[\.!?]\s+|,\s*)[Яя]\s+'
            r'([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})',
        ),
        # "Меня зовут Фамилия Имя Отчество"
        re.compile(
            r'(?:меня\s+зовут|мое\s+имя|моё\s+имя)\s+'
            r'([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})',
            re.IGNORECASE,
        ),
        # "Клиент: Фамилия Имя Отчество" / "ФИО: ..."
        re.compile(
            r'(?:клиент|фио|отправитель|получатель|владелец|заявитель)[:\s]+'
            r'([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})',
            re.IGNORECASE,
        ),
    ]
    FIO_TRANSLIT_PATTERNS = [
        # Ivanov Petr, IVANOV PETR SERGEEVICH
        re.compile(
            r'(?:^|[\s,.])'
            r'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
            r'(?=[\s,.\!?]|$)'
        ),
    ]

    def detect(self, text: str) -> list[PIIEntity]:
        entities = []
        entities.extend(self._detect_phones(text))
        entities.extend(self._detect_emails(text))
        entities.extend(self._detect_passports(text))
        entities.extend(self._detect_snils(text))
        entities.extend(self._detect_inn(text))
        entities.extend(self._detect_cards(text))
        entities.extend(self._detect_accounts(text))
        entities.extend(self._detect_dates(text))
        entities.extend(self._detect_fio_context(text))
        entities.extend(self._detect_fio_translit(text))
        entities = self._resolve_overlaps(entities)
        return entities

    # ── Детекторы по типам ─────────────────────────────────
    def _detect_fio_translit(self, text: str) -> list[PIIEntity]:
        """Ловит транслитерированные ФИО: Ivanov Petr Sergeevich"""
        results = []

        # Стоп-слова (английские слова, не имена)
        STOP_WORDS = {
            "the", "and", "for", "from", "with", "that", "this", "have", "will",
            "your", "our", "not", "are", "was", "been", "being", "has", "had",
            "does", "did", "but", "can", "could", "would", "should", "may",
            "Premium", "Gold", "Silver", "Platinum", "Business", "Classic",
        }

        for pattern in self.FIO_TRANSLIT_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group(1).strip()
                words = name.split()

                # Фильтр: минимум 2 слова
                if len(words) < 2:
                    continue

                # Фильтр: не стоп-слова
                if any(w in STOP_WORDS for w in words):
                    continue

                # Фильтр: все слова с заглавной, длина >= 3
                if not all(len(w) >= 3 and w[0].isupper() for w in words):
                    continue

                results.append(PIIEntity(
                    entity_type="PERSON",
                    value=name,
                    start=match.start(1),
                    end=match.end(1),
                    confidence=0.6,  # ниже чем NER/контекстный
                    validated=True,
                ))
        return results
    def _detect_fio_context(self, text: str) -> list[PIIEntity]:
        """Ловит ФИО по контексту (я ..., клиент: ..., и т.д.)"""
        results = []
        for pattern in self.FIO_CONTEXT_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group(1).strip()
                # Фильтруем: минимум 2 слова, каждое с заглавной
                words = name.split()
                if len(words) < 2:
                    continue
                if not all(w[0].isupper() for w in words):
                    continue
                # Фильтруем слишком короткие слова (предлоги)
                if any(len(w) < 2 for w in words):
                    continue

                # Находим позицию группы в тексте
                group_start = match.start(1)
                group_end = match.end(1)

                results.append(PIIEntity(
                    entity_type="PERSON",
                    value=name,
                    start=group_start,
                    end=group_end,
                    confidence=0.75,  # ниже чем NER, но лучше чем ничего
                    validated=True,
                ))
        return results
    def _detect_phones(self, text: str) -> list[PIIEntity]:
        results = []
        for pattern in self.PHONE_PATTERNS:
            for match in pattern.finditer(text):
                results.append(PIIEntity(
                    entity_type="PHONE",
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                    validated=True,
                ))
        return results

    def _detect_emails(self, text: str) -> list[PIIEntity]:
        results = []
        for match in self.EMAIL_PATTERN.finditer(text):
            results.append(PIIEntity(
                entity_type="EMAIL",
                value=match.group(),
                start=match.start(),
                end=match.end(),
                validated=True,
            ))
        return results

    def _detect_passports(self, text: str) -> list[PIIEntity]:
        results = []
        for pattern in self.PASSPORT_PATTERNS:
            for match in pattern.finditer(text):
                full_match = match.group()
                series = match.group(1) if match.lastindex and match.lastindex >= 1 else ""
                validated = is_valid_passport_series(series)
                results.append(PIIEntity(
                    entity_type="PASSPORT",
                    value=full_match,
                    start=match.start(),
                    end=match.end(),
                    validated=validated,
                    confidence=0.8,  # нет контрольной суммы → ниже уверенность
                ))
        return results

    def _detect_snils(self, text: str) -> list[PIIEntity]:
        results = []
        for pattern in self.SNILS_PATTERNS:
            for match in pattern.finditer(text):
                validated = is_valid_snils(match.group())
                results.append(PIIEntity(
                    entity_type="SNILS",
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                    validated=validated,
                    confidence=1.0 if validated else 0.5,
                ))
        return results

    def _detect_inn(self, text: str) -> list[PIIEntity]:
        results = []
        for pattern in self.INN_PATTERNS:
            for match in pattern.finditer(text):
                validated = is_valid_inn(match.group())
                if validated:
                    results.append(PIIEntity(
                        entity_type="INN",
                        value=match.group(),
                        start=match.start(),
                        end=match.end(),
                        validated=True,
                        confidence=1.0,  # контрольная сумма → максимум
                    ))
        return results

    def _detect_cards(self, text: str) -> list[PIIEntity]:
        results = []
        for pattern in self.CARD_PATTERNS:
            for match in pattern.finditer(text):
                validated = is_valid_card_luhn(match.group())
                results.append(PIIEntity(
                    entity_type="CARD",
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                    validated=validated,
                    confidence=1.0 if validated else 0.5,
                ))
        return results

    def _detect_accounts(self, text: str) -> list[PIIEntity]:
        results = []
        for pattern in self.ACCOUNT_PATTERNS:
            for match in pattern.finditer(text):
                validated = is_valid_account_number(match.group())
                if validated:
                    results.append(PIIEntity(
                        entity_type="ACCOUNT",
                        value=match.group(),
                        start=match.start(),
                        end=match.end(),
                        validated=True,
                    ))
        return results

    def _detect_dates(self, text: str) -> list[PIIEntity]:
        results = []
        for pattern in self.DATE_PATTERNS:
            for match in pattern.finditer(text):
                results.append(PIIEntity(
                    entity_type="DATE",
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                    validated=True,
                ))
        return results

    # ── Разрешение пересечений ─────────────────────────────

    def _resolve_overlaps(self, entities: list[PIIEntity]) -> list[PIIEntity]:
        """
        Если два обнаружения пересекаются — выбираем по приоритету:
        1. Тип с более высоким приоритетом (ИНН > паспорт)
        2. Валидированный > невалидированный
        3. Более длинный спан
        """
        if not entities:
            return []

        entities.sort(key=lambda e: (
            e.start,
            -self.TYPE_PRIORITY.get(e.entity_type, 0),  # высокий приоритет первым
            -int(e.validated),                            # validated первыми
            -e.confidence,                                # выше confidence первыми
            -(e.end - e.start),                           # длинные первыми
        ))

        result = [entities[0]]
        for entity in entities[1:]:
            last = result[-1]
            if entity.start < last.end:
                continue
            result.append(entity)

        return result