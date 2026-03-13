"""
Бенчмарк производительности.
Замеряет латенцию каждого компонента отдельно.

Запуск:
    python utils/benchmark.py
"""

import time
import statistics
import sys
sys.path.insert(0, ".")

from detectors.regex_detector import RegexDetector
from detectors.ner_detector import NatashaDetector
from services.masking_service import MaskingService
from services.unmasking_stream import StreamInterceptor, TokenFormat


SAMPLE_TEXTS = [
    "Я Иванов Пётр, телефон +7 999 123-45-67",
    "Паспорт 45 15 123456, СНИЛС 112-233-445 95, карта 4532 0151 1283 0366",
    "Здравствуйте, я Петров Алексей Сергеевич, паспорт 45 15 123456, телефон +7 916 555-44-33, email petrov@gmail.com, дата рождения 01.05.1985",
    "Какой курс доллара?",
    "Переведите 5000 рублей Сидорову на карту 5425 2334 3010 9903",
]


def benchmark_component(name: str, func, n_runs: int = 100):
    """Замеряет время выполнения функции."""
    # Прогрев
    for _ in range(5):
        func()

    times = []
    for _ in range(n_runs):
        start = time.perf_counter()
        func()
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)

    print(f"\n{name}:")
    print(f"  Среднее:   {statistics.mean(times):.2f} мс")
    print(f"  Медиана:   {statistics.median(times):.2f} мс")
    print(f"  P95:       {sorted(times)[int(len(times)*0.95)]:.2f} мс")
    print(f"  P99:       {sorted(times)[int(len(times)*0.99)]:.2f} мс")
    print(f"  Мин/Макс:  {min(times):.2f} / {max(times):.2f} мс")

    return statistics.mean(times)


def main():
    print("=" * 60)
    print("БЕНЧМАРК ПРОИЗВОДИТЕЛЬНОСТИ")
    print("=" * 60)

    # 1. Regex только
    regex = RegexDetector()
    benchmark_component(
        "Regex Detector (сложный текст)",
        lambda: regex.detect(SAMPLE_TEXTS[2]),
    )

    # 2. NER только
    ner = NatashaDetector()
    benchmark_component(
        "Natasha NER (сложный текст)",
        lambda: ner.detect(SAMPLE_TEXTS[2]),
    )

    # 3. MaskingService (regex + NER)
    service = MaskingService(use_ner=True)
    benchmark_component(
        "MaskingService с NER (сложный текст)",
        lambda: service.mask(SAMPLE_TEXTS[2]),
    )

    # 4. MaskingService (regex only)
    service_regex = MaskingService(use_ner=False)
    benchmark_component(
        "MaskingService без NER (сложный текст)",
        lambda: service_regex.mask(SAMPLE_TEXTS[2]),
    )

    # 5. StreamInterceptor
    mapping = {"[PER_1]": "Иванов", "[PHONE_1]": "+7 999 123-45-67"}
    text = "Здравствуйте, [PER_1]! Ваш номер [PHONE_1]."

    def stream_test():
        interceptor = StreamInterceptor(mapping)
        for i in range(0, len(text), 3):
            interceptor.feed(text[i:i+3])
        interceptor.flush()

    benchmark_component("StreamInterceptor (chunk=3)", stream_test)

    # 6. Полный pipeline
    def full_pipeline():
        result = service.mask(SAMPLE_TEXTS[2])
        interceptor = StreamInterceptor(result.mapping)
        response = f"Здравствуйте, {list(result.mapping.keys())[0]}!"
        for i in range(0, len(response), 2):
            interceptor.feed(response[i:i+2])
        interceptor.flush()

    benchmark_component("Полный pipeline (mask + unmask)", full_pipeline)

    # 7. Текст без PII
    benchmark_component(
        "Текст без PII (быстрый путь)",
        lambda: service.mask(SAMPLE_TEXTS[3]),
    )

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
