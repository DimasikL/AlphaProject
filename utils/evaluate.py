"""
Оценка качества детекции PII.
Считает Precision, Recall, F1 на синтетических данных.

Запуск:
    python utils/evaluate.py
"""

import json
import time
import sys
sys.path.insert(0, ".")

from utils.generate_data import generate_dataset
from services.masking_service import MaskingService


def evaluate(n_samples: int = 200, use_ner: bool = True):
    """
    Генерирует N запросов с известными PII (ground truth),
    прогоняет через MaskingService, считает метрики.
    """
    print(f"Генерация {n_samples} тестовых запросов...")
    dataset = generate_dataset(n_samples)

    service = MaskingService(use_ner=use_ner)

    true_positives = 0   # PII найдено и оно реально есть
    false_positives = 0  # Найдено, но это не PII
    false_negatives = 0  # PII есть, но не найдено

    total_latency = 0
    errors = []

    for i, sample in enumerate(dataset):
        text = sample["text"]
        ground_truth = sample["pii_ground_truth"]  # {"phone": "+7...", "name": "Иванов..."}

        start = time.perf_counter()
        result = service.mask(text)
        elapsed = (time.perf_counter() - start) * 1000
        total_latency += elapsed

        # Проверяем: каждый PII из ground_truth должен быть замаскирован
        masked_values = set(result.mapping.values())

        for pii_type, pii_value in ground_truth.items():
            if pii_value in masked_values:
                true_positives += 1
            elif pii_value not in result.masked_text:
                # Замаскировано, но другим способом (частично)
                true_positives += 1
            else:
                false_negatives += 1
                errors.append({
                    "sample": i,
                    "type": pii_type,
                    "value": pii_value[:30],
                    "text_preview": text[:80],
                    "error": "NOT_DETECTED",
                })

    # Precision и Recall
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    avg_latency = total_latency / n_samples

    # ── Вывод ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТЫ ОЦЕНКИ КАЧЕСТВА")
    print("=" * 60)
    print(f"Выборка:          {n_samples} запросов")
    print(f"NER включён:      {use_ner}")
    print(f"")
    print(f"True Positives:   {true_positives}")
    print(f"False Positives:  {false_positives}")
    print(f"False Negatives:  {false_negatives}")
    print(f"")
    print(f"Precision:        {precision:.1%}")
    print(f"Recall:           {recall:.1%}")
    print(f"F1 Score:         {f1:.1%}")
    print(f"")
    print(f"Avg Latency:      {avg_latency:.1f} мс/запрос")
    print(f"Total Time:       {total_latency / 1000:.1f} сек")
    print("=" * 60)

    if errors:
        print(f"\nПримеры пропусков ({min(len(errors), 10)} из {len(errors)}):")
        for err in errors[:10]:
            print(f"  [{err['type']}] {err['value']} — {err['error']}")
            print(f"    Текст: {err['text_preview']}...")

    # Сохраняем результаты
    results = {
        "samples": n_samples,
        "use_ner": use_ner,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "avg_latency_ms": round(avg_latency, 2),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "errors": errors[:50],
    }
    with open("evaluation_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nРезультаты сохранены в evaluation_results.json")

    return results

def evaluate_manual():
    """Оценка на ручных тест-кейсах."""
    from utils.manual_test_cases import MANUAL_TEST_CASES

    service = MaskingService(use_ner=True)

    passed = 0
    failed = 0
    errors = []

    print("\n" + "=" * 60)
    print("РУЧНЫЕ ТЕСТ-КЕЙСЫ")
    print("=" * 60)

    for i, case in enumerate(MANUAL_TEST_CASES):
        text = case["text"]
        expected = case["expected_pii"]

        result = service.mask(text)
        masked_values = set(result.mapping.values())

        case_ok = True

        # Проверяем что ВСЕ ожидаемые PII замаскированы
        for pii_type, pii_value in expected.items():
            if pii_value in result.masked_text:
                case_ok = False
                errors.append({
                    "case": i,
                    "type": pii_type,
                    "value": pii_value[:30],
                    "text": text[:60],
                    "error": "NOT_MASKED",
                })

        # Проверяем false positives (для пустых expected)
        if not expected and result.stats.get("total_found", 0) > 0:
            case_ok = False
            found_types = list(result.stats.get("by_type", {}).keys())
            errors.append({
                "case": i,
                "type": str(found_types),
                "value": str(list(result.mapping.values())[:2]),
                "text": text[:60],
                "error": "FALSE_POSITIVE",
            })

        status = "✅" if case_ok else "❌"
        print(f"  {status} [{i+1:2d}] {text[:70]}...")

        if case_ok:
            passed += 1
        else:
            failed += 1

    print(f"\n  Результат: {passed}/{passed+failed} passed")
    if errors:
        print(f"\n  Ошибки:")
        for e in errors:
            print(f"    [{e['case']}] {e['error']}: {e['type']} = {e['value']}")

    return passed, failed, errors


if __name__ == "__main__":
    evaluate(n_samples=200, use_ner=True)
    evaluate_manual()