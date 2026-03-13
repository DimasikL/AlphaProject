"""
Асинхронный симулятор LLM.
Имитирует потоковую генерацию текста.
Использует ТОЛЬКО токены из ТЕКУЩЕГО запроса.
"""

import asyncio
import random
import re
from typing import AsyncGenerator


def generate_llm_response(masked_text: str) -> str:
    """
    Генерирует ответ на основе замаскированного текста.
    ВАЖНО: использует только токены, которые есть в masked_text.
    Никогда не придумывает токены, которых нет.
    """
    text_lower = masked_text.lower()

    # Извлекаем ТОЛЬКО токены из текущего запроса
    tokens = re.findall(r'\[[A-Z]+_\d+\]', masked_text)
    token_by_type: dict[str, str] = {}
    for t in tokens:
        match = re.match(r'\[([A-Z]+)_\d+\]', t)
        if match:
            entity_type = match.group(1)
            # Сохраняем только первый токен каждого типа
            if entity_type not in token_by_type:
                token_by_type[entity_type] = t

    person = token_by_type.get("PERSON", "клиент")
    has_phone = "PHONE" in token_by_type
    has_card = "CARD" in token_by_type
    has_passport = "PASSPORT" in token_by_type
    has_snils = "SNILS" in token_by_type
    has_inn = "INN" in token_by_type
    has_email = "EMAIL" in token_by_type
    has_account = "ACCOUNT" in token_by_type
    has_date = "DATE" in token_by_type

    # ── Определяем тему запроса ────────────────────────────

    if any(w in text_lower for w in ["баланс", "остаток", "сколько на"]):
        if has_card:
            card = token_by_type["CARD"]
            response = (
                f"Здравствуйте, {person}! Баланс вашей карты {card}: "
                f"45 230,50 руб. Последняя операция: списание 1 500 руб. "
                f"в магазине «Пятёрочка» 12.03.2026."
            )
        elif has_account:
            account = token_by_type["ACCOUNT"]
            response = (
                f"Здравствуйте, {person}! Баланс счёта {account}: "
                f"128 450,00 руб. Доступно для снятия: 125 000,00 руб."
            )
        else:
            response = (
                f"Здравствуйте, {person}! Баланс вашего основного счёта: "
                f"45 230,50 руб. Для детализации по конкретной карте "
                f"укажите, пожалуйста, номер карты."
            )

    elif any(w in text_lower for w in ["перевод", "переведи", "отправь", "перечисл"]):
        amount = random.randint(100, 50000)
        op_id = random.randint(100000, 999999)
        if has_card:
            target = f"карту {token_by_type['CARD']}"
        elif has_account:
            target = f"счёт {token_by_type['ACCOUNT']}"
        else:
            target = "указанный счёт"

        response = (
            f"Перевод для {person} на {target} успешно выполнен. "
            f"Номер операции: {op_id}. "
            f"Средства поступят в течение нескольких минут."
        )

    elif any(w in text_lower for w in ["заблокир", "блокир", "украли", "потерял"]):
        if has_card:
            card = token_by_type["CARD"]
            response = (
                f"{person}, карта {card} немедленно заблокирована. "
                f"Номер обращения: BLK-{random.randint(10000, 99999)}. "
                f"Для перевыпуска карты обратитесь в ближайшее отделение "
                f"с паспортом."
            )
        else:
            response = (
                f"{person}, для блокировки карты назовите, пожалуйста, "
                f"последние 4 цифры карты. Мы немедленно её заблокируем."
            )

    elif any(w in text_lower for w in ["кредит", "ипотек", "заявк", "оформ"]):
        response = (
            f"{person}, спасибо за обращение! "
            f"Для оформления заявки нам потребуются ваши документы. "
        )
        if has_passport:
            response += f"Паспортные данные получены. "
        else:
            response += f"Пожалуйста, предоставьте паспортные данные. "

        if has_inn:
            response += f"ИНН подтверждён. "

        response += (
            f"Предварительное решение будет готово в течение 15 минут. "
            f"Номер заявки: CR-{random.randint(10000, 99999)}."
        )

    elif any(w in text_lower for w in ["брокер", "инвестиц", "акци", "облигац"]):
        response = (
            f"{person}, для открытия брокерского счёта необходимо: "
            f"1) Подписать договор на обслуживание. "
            f"2) Пополнить счёт от 1 000 руб. "
        )
        if has_inn:
            response += f"Ваш ИНН подтверждён, налоговая отчётность будет автоматической. "
        response += (
            f"После открытия вам будет доступна торговля на Московской бирже. "
            f"Комиссия: 0,05% от суммы сделки."
        )

    elif any(w in text_lower for w in ["карт", "card", "информац"]):
        if has_card:
            card = token_by_type["CARD"]
            response = (
                f"{person}, информация по карте {card}: "
                f"тип — дебетовая, статус — активна, срок действия — 12/26. "
                f"Кэшбэк за текущий месяц: 1 230 руб."
            )
        else:
            response = (
                f"{person}, у вас 2 активные карты. "
                f"Для уточнения укажите номер или последние 4 цифры."
            )

    elif any(w in text_lower for w in ["выписк", "история операц"]):
        response = (
            f"{person}, выписка за последний месяц сформирована. "
        )
        if has_email:
            email = token_by_type["EMAIL"]
            response += f"Отправлена на {email}. "
        else:
            response += f"Для отправки по email укажите адрес электронной почты. "
        response += f"Номер документа: STM-{random.randint(10000, 99999)}."

    elif any(w in text_lower for w in ["смен", "изменить", "обновить", "новый номер"]):
        response = f"{person}, для смены контактных данных "
        if has_phone:
            phone = token_by_type["PHONE"]
            response += (
                f"подтвердите, пожалуйста, старый номер. "
                f"SMS-код отправлен на текущий номер. "
                f"После подтверждения новый номер будет привязан к вашему аккаунту."
            )
        else:
            response += f"обратитесь в отделение с паспортом."

    elif any(w in text_lower for w in ["страхов", "путешеств", "поездк", "турци", "отпуск"]):
        response = (
            f"{person}, рекомендуем полис «Альфа-Путешественник»: "
            f"покрытие до 100 000 €, экстренная медпомощь, "
            f"эвакуация, потеря багажа. "
            f"Стоимость: от 1 200 руб. за 14 дней. "
        )
        if has_passport:
            response += f"Паспортные данные получены, полис можно оформить онлайн."
        else:
            response += f"Для оформления потребуется загранпаспорт."

    elif any(w in text_lower for w in ["курс", "доллар", "евро", "валют"]):
        response = (
            f"Текущие курсы валют: "
            f"USD/RUB: 92.45 (покупка) / 93.10 (продажа). "
            f"EUR/RUB: 100.20 (покупка) / 101.05 (продажа). "
            f"Курсы обновлены на 13.03.2026 12:00 МСК."
        )

    elif any(w in text_lower for w in ["кэшбэк", "cashback", "бонус", "привилег"]):
        response = (
            f"{person}, ваш текущий кэшбэк: "
            f"1 230 руб. за март 2026. Категории с повышенным кэшбэком: "
            f"рестораны — 5%, АЗС — 3%, онлайн-покупки — 2%."
        )

    else:
        ticket_id = f"ALF-{random.randint(10000, 99999)}"
        response = (
            f"Здравствуйте, {person}! Спасибо за обращение. "
            f"Ваш запрос принят, номер обращения: {ticket_id}. "
        )
        if has_phone:
            phone = token_by_type["PHONE"]
            response += f"Мы свяжемся с вами по телефону {phone} в ближайшее время."
        elif has_email:
            email = token_by_type["EMAIL"]
            response += f"Ответ будет направлен на {email}."
        else:
            response += f"Мы свяжемся с вами в ближайшее время."

    return response


async def async_llm_stream(
        masked_text: str,
        min_chunk: int = 2,
        max_chunk: int = 6,
        delay_min: float = 0.02,
        delay_max: float = 0.08,
) -> AsyncGenerator[str, None]:
    """
    Асинхронный генератор, имитирующий стрим от LLM API.
    """
    response = generate_llm_response(masked_text)

    i = 0
    while i < len(response):
        chunk_size = random.randint(min_chunk, max_chunk)
        chunk = response[i: i + chunk_size]
        yield chunk
        i += chunk_size
        await asyncio.sleep(random.uniform(delay_min, delay_max))


async def async_llm_stream_adversarial(
        masked_text: str,
) -> AsyncGenerator[str, None]:
    """
    Злой симулятор — режет ответ посередине токенов.
    """
    response = generate_llm_response(masked_text)

    cut_points = set()
    for i, ch in enumerate(response):
        if ch in "[]":
            cut_points.add(i)
            cut_points.add(i + 1)

    for _ in range(len(response) // 4):
        cut_points.add(random.randint(0, len(response)))

    cut_points = sorted(cut_points | {0, len(response)})

    for start, end in zip(cut_points, cut_points[1:]):
        chunk = response[start:end]
        if chunk:
            yield chunk
            await asyncio.sleep(random.uniform(0.01, 0.05))