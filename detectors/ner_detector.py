import threading
from natasha import (
    Segmenter,
    MorphVocab,
    NewsEmbedding,
    NewsNERTagger,
    NamesExtractor,
    AddrExtractor,
    Doc,
)

from detectors.regex_detector import PIIEntity


class NatashaDetector:

    FALSE_POSITIVE_WORDS = {
        "подключите", "переведите", "отправьте", "покажите", "проверьте",
        "заблокируйте", "разблокируйте", "оформите", "закройте", "откройте",
        "помогите", "подскажите", "расскажите", "уточните", "сообщите",
        "альфа", "premium", "gold", "platinum", "business",
        "здравствуйте", "добрый", "уважаемый", "уважаемая",
        "господин", "госпожа", "клиент",
    }

    MIN_SINGLE_WORD_LENGTH = 3

    def __init__(self):
        self.segmenter = Segmenter()
        self.morph_vocab = MorphVocab()
        self.emb = NewsEmbedding()
        self.ner_tagger = NewsNERTagger(self.emb)
        self.names_extractor = NamesExtractor(self.morph_vocab)
        self.addr_extractor = AddrExtractor(self.morph_vocab)
        self._lock = threading.Lock()  # ← THREAD SAFETY

    def detect(self, text: str) -> list[PIIEntity]:
        with self._lock:  # ← ЗАЩИТА
            return self._detect_unsafe(text)

    def _detect_unsafe(self, text: str) -> list[PIIEntity]:
        doc = Doc(text)
        doc.segment(self.segmenter)
        doc.tag_ner(self.ner_tagger)

        entities = []
        for span in doc.spans:
            entity_type = self._map_type(span.type)
            if entity_type is None:
                continue
            if not self._is_valid_entity(span, entity_type):
                continue

            entities.append(PIIEntity(
                entity_type=entity_type,
                value=span.text,
                start=span.start,
                end=span.stop,
                confidence=0.85,
                validated=True,
            ))

        return entities

    def _is_valid_entity(self, span, entity_type: str) -> bool:
        text_lower = span.text.lower().strip()
        words = text_lower.split()

        for word in words:
            if word in self.FALSE_POSITIVE_WORDS:
                return False

        if entity_type == "PERSON" and len(words) == 1:
            word = words[0]
            if len(word) < self.MIN_SINGLE_WORD_LENGTH:
                return False
            if not span.text[0].isupper():
                return False
            if any(c.isdigit() for c in word):
                return False

        if entity_type == "PERSON":
            original_words = span.text.split()
            has_capitalized = any(w[0].isupper() for w in original_words if w)
            if not has_capitalized:
                return False

        return True

    def extract_normalized_name(self, text: str) -> list[dict]:
        with self._lock:  # ← ЗАЩИТА
            return self._extract_normalized_name_unsafe(text)

    def _extract_normalized_name_unsafe(self, text: str) -> list[dict]:
        doc = Doc(text)
        doc.segment(self.segmenter)
        doc.tag_ner(self.ner_tagger)

        results = []
        for span in doc.spans:
            if span.type == "PER":
                if not self._is_valid_entity(span, "PERSON"):
                    continue
                span.normalize(self.morph_vocab)
                span.extract(self.names_extractor)
                name_info = {}
                if hasattr(span, "fact") and span.fact:
                    fact = span.fact
                    if fact.first:
                        name_info["first"] = fact.first
                    if fact.last:
                        name_info["last"] = fact.last
                    if fact.middle:
                        name_info["middle"] = fact.middle
                    name_info["normal"] = span.normal
                    name_info["original"] = span.text
                    name_info["start"] = span.start
                    name_info["stop"] = span.stop
                    results.append(name_info)

        return results

    @staticmethod
    def _map_type(natasha_type: str) -> str | None:
        mapping = {
            "PER": "PERSON",
            "LOC": "ADDRESS",
        }
        return mapping.get(natasha_type)