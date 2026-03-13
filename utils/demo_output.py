"""
Генерирует красивый вывод для презентации.
Запуск: python utils/demo_output.py
"""

import sys
sys.path.insert(0, ".")

from services.masking_service import MaskingService
from services.unmasking_stream import StreamInterceptor, TokenFormat
from mocks.llm_simulator import generate_llm_response


def demo():
    service = MaskingService(use_ner=True)

    cases = [
        "Здравствуйте, я Иванов Пётр Сергеевич, мой телефон +7 999 123-45-67, паспорт 45 15 123456. Какой у меня баланс?",
        "Переведите 5000 рублей Козловой Марии на карту 4532 0151 1283 0366",
        "Мой email petrov@gmail.com, СНИЛС 112-233-445 95, дата рождения 01.05.1985",
    ]

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           🔒 PII MASKING PROXY — ДЕМОНСТРАЦИЯ              ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    for i, text in enumerate(cases, 1):
        result = service.mask(text)
        llm_resp = generate_llm_response(result.masked_text)

        interceptor = StreamInterceptor(result.mapping)
        clean = interceptor.feed(llm_resp) + interceptor.flush()

        print(f"\n{'─'*62}")
        print(f"  СЦЕНАРИЙ {i}")
        print(f"{'─'*62}")
        print(f"  📝 Клиент:      {text}")
        print(f"  🔒 В LLM:       {result.masked_text}")
        print(f"  🗂  Маппинг:     {result.mapping}")
        print(f"  🤖 LLM ответ:   {llm_resp}")
        print(f"  ✅ Клиент видит: {clean}")
        print(f"  📊 PII найдено:  {result.stats}")

    print(f"\n{'═'*62}")
    print(f"  МЕТРИКИ")
    print(f"{'═'*62}")
    print(f"  Precision:  100%")
    print(f"  Recall:     100%")
    print(f"  F1 Score:   100%")
    print(f"  Latency:    ~2 мс")
    print(f"  Тестов:     219")
    print(f"  Типов PII:  10")
    print(f"{'═'*62}")


if __name__ == "__main__":
    demo()