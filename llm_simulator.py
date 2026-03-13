"""
Имитирует поведение LLM, которая отдаёт ответ чанками разной длины.
Используется для тестирования StreamInterceptor без реального API.
"""

import random
import time
from typing import Generator


def simulate_llm_stream(
        text: str,
        min_chunk: int = 1,
        max_chunk: int = 5,
        delay: float = 0.05,
) -> Generator[str, None, None]:
    """
    Разбивает text на случайные куски от min_chunk до max_chunk символов
    и отдаёт их с задержкой, имитируя поведение LLM API.
    """
    i = 0
    while i < len(text):
        chunk_size = random.randint(min_chunk, max_chunk)
        chunk = text[i : i + chunk_size]
        yield chunk
        i += chunk_size
        time.sleep(delay)


def simulate_llm_stream_adversarial(
        text: str,
) -> Generator[str, None, None]:
    """
    Злой симулятор: специально режет текст посередине токенов.
    Например, [PER_1] режется как: "[", "PER", "_1", "]"
    """
    # Находим позиции всех [ и ] и режем именно там
    cut_points = set()
    for i, ch in enumerate(text):
        if ch in "[]<>/":
            cut_points.add(i)
            cut_points.add(i + 1)

    # Добавляем случайные точки разреза
    for _ in range(len(text) // 3):
        cut_points.add(random.randint(0, len(text)))

    cut_points = sorted(cut_points | {0, len(text)})

    for start, end in zip(cut_points, cut_points[1:]):
        chunk = text[start:end]
        if chunk:
            yield chunk
            time.sleep(0.03)


# ── Быстрый тест ──────────────────────────────────────────
if __name__ == "__main__":
    test_text = "Привет, [PER_1]! Ваш номер [PHONE_1]. Баланс карты [CARD_1]: 15 000 руб."

    print("=== Обычный стрим ===")
    for chunk in simulate_llm_stream(test_text, min_chunk=1, max_chunk=4):
        print(repr(chunk), end=" → ", flush=True)

    print("\n\n=== Злой стрим (режет токены) ===")
    for chunk in simulate_llm_stream_adversarial(test_text):
        print(repr(chunk), end=" → ", flush=True)