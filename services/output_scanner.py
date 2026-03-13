"""
Сканирование ответа LLM на наличие НОВЫХ PII.
LLM может сгенерировать чужой телефон, имя, адрес — это утечка в обратную сторону.
"""

import logging
from detectors.detector_pipeline import DetectorPipeline
from detectors.regex_detector import PIIEntity

logger = logging.getLogger(__name__)


class OutputScanner:
    """
    Проверяет ответ LLM на наличие PII, которых НЕ было в исходном запросе.
    """

    def __init__(self, use_ner: bool = False):
        # Для выхода используем только regex (быстрее)
        # NER может давать false positives на сгенерированном тексте
        self.pipeline = DetectorPipeline(use_ner=use_ner)

    def scan(
            self,
            response_text: str,
            known_mapping: dict[str, str],
    ) -> list[PIIEntity]:
        """
        Находит PII в ответе LLM, исключая те, что уже есть в mapping.

        Args:
            response_text: размаскированный ответ LLM
            known_mapping: маппинг из MaskingService (известные PII клиента)

        Returns:
            Список НОВЫХ (неизвестных) PII — потенциальная утечка
        """
        known_values = set(known_mapping.values())

        all_entities = self.pipeline.detect_all(response_text)

        # Фильтруем: оставляем только те, что НЕ были в запросе клиента
        leaked = []
        for entity in all_entities:
            if entity.value not in known_values:
                leaked.append(entity)
                logger.warning(
                    f"LEAKED PII in LLM response: type={entity.entity_type}, "
                    f"value={entity.value[:20]}..."
                )

        return leaked

    def mask_leaked(
            self,
            response_text: str,
            leaked_entities: list[PIIEntity],
    ) -> str:
        """
        Маскирует обнаруженные утечки в ответе.
        Заменяет на [REDACTED].
        """
        if not leaked_entities:
            return response_text

        # Заменяем с конца, чтобы не сбить индексы
        result = response_text
        for entity in sorted(leaked_entities, key=lambda e: e.start, reverse=True):
            result = (
                    result[:entity.start]
                    + "[ДАННЫЕ СКРЫТЫ]"
                    + result[entity.end:]
            )

        return result