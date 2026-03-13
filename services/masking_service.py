from dataclasses import dataclass, field
from detectors.detector_pipeline import DetectorPipeline
from detectors.regex_detector import PIIEntity


@dataclass
class MaskingResult:
    masked_text: str
    mapping: dict[str, str]
    entities_found: list[PIIEntity]
    stats: dict = field(default_factory=dict)


class MaskingService:

    def __init__(self, use_ner: bool = True):
        self.pipeline = DetectorPipeline(use_ner=use_ner)

    def mask(
            self,
            text: str,
            session=None,
    ) -> MaskingResult:
        """
        Маскирует PII в тексте.

        Args:
            text: исходный текст
            session: объект Session для уникальных токенов в рамках сессии.
                     Если None — счётчики локальные (для одиночных вызовов).
        """
        entities = self.pipeline.detect_all(text)

        if not entities:
            return MaskingResult(
                masked_text=text,
                mapping={},
                entities_found=[],
                stats={"total_found": 0},
            )

        # Локальные счётчики (для вызовов без сессии)
        local_counters: dict[str, int] = {}

        mapping = {}
        masked_text = text

        for entity in sorted(entities, key=lambda e: e.start, reverse=True):
            # Генерируем токен
            if session is not None:
                token = session.next_token(entity.entity_type)
            else:
                count = local_counters.get(entity.entity_type, 0) + 1
                local_counters[entity.entity_type] = count
                token = f"[{entity.entity_type}_{count}]"

            mapping[token] = entity.value
            masked_text = (
                    masked_text[:entity.start]
                    + token
                    + masked_text[entity.end:]
            )

        stats = {
            "total_found": len(entities),
            "by_type": {},
        }
        for entity in entities:
            t = entity.entity_type
            stats["by_type"][t] = stats["by_type"].get(t, 0) + 1

        return MaskingResult(
            masked_text=masked_text,
            mapping=mapping,
            entities_found=entities,
            stats=stats,
        )