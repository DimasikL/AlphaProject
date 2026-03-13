"""
Объединяет все детекторы в единый конвейер.
Regex → Natasha NER → дедупликация → сортировка.
"""

from detectors.regex_detector import RegexDetector, PIIEntity
from detectors.ner_detector import NatashaDetector


class DetectorPipeline:

    def __init__(self, use_ner: bool = True):
        self.regex_detector = RegexDetector()
        self.ner_detector = NatashaDetector() if use_ner else None

    def detect_all(self, text: str) -> list[PIIEntity]:
        entities = []

        # 1. Regex (включая контекстное ФИО)
        regex_entities = self.regex_detector.detect(text)
        entities.extend(regex_entities)

        # 2. NER (если включён)
        if self.ner_detector:
            ner_entities = self.ner_detector.detect(text)
            entities.extend(ner_entities)

        # 3. Разрешаем пересечения
        entities = self._resolve_all_overlaps(entities)
        entities.sort(key=lambda e: e.start)

        return entities

    @staticmethod
    def _resolve_all_overlaps(entities: list[PIIEntity]) -> list[PIIEntity]:
        if not entities:
            return []

        entities.sort(key=lambda e: (
            e.start,
            -int(e.validated),
            -e.confidence,
            -(e.end - e.start),
        ))

        result = [entities[0]]
        for entity in entities[1:]:
            last = result[-1]
            if entity.start < last.end:
                # Пересечение — оставляем с бОльшим confidence
                if entity.confidence > last.confidence:
                    result[-1] = entity
                continue
            result.append(entity)

        return result

    @staticmethod
    def _resolve_all_overlaps(entities: list[PIIEntity]) -> list[PIIEntity]:
        """
        Разрешает пересечения между regex и NER.
        Приоритет: validated > не validated, потом длина.
        """
        if not entities:
            return []

        # Приоритет: validated первыми, потом длинные
        entities.sort(key=lambda e: (
            e.start,
            -int(e.validated),
            -(e.end - e.start),
        ))

        result = [entities[0]]
        for entity in entities[1:]:
            last = result[-1]
            if entity.start < last.end:
                # Пересечение — оставляем уже добавленный (он приоритетнее)
                continue
            result.append(entity)

        return result