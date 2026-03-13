"""
Генератор синтетических данных для тестирования.
Создаёт реалистичные банковские запросы с PII.
"""

import random
from faker import Faker

fake = Faker("ru_RU")


# ── Шаблоны запросов ───────────────────────────────────────

TEMPLATES = [
    "Здравствуйте, я {name}, мой телефон {phone}. Какой у меня баланс?",
    "Добрый день! Меня зовут {name}, паспорт {passport}. Хочу открыть вклад.",
    "Переведите {amount} рублей на карту {card}. Отправитель: {name}.",
    "Я {name}, дата рождения {dob}. Хочу заказать кредитную карту.",
    "Прошу заблокировать карту {card}. Владелец: {name}, телефон {phone}.",
    "{name}, паспорт {passport}, СНИЛС {snils}. Подаю заявку на кредит.",
    "Мой email: {email}, телефон {phone}. Подключите мне интернет-банк. С уважением, {name}.",
    "Добрый день, это {name}. Номер счёта {account}. Какой остаток?",
    "Хочу перевести {amount} руб. с карты {card} на счёт {account}. Я {name}.",
    "Запрос на выписку. ФИО: {name}, дата рождения {dob}, паспорт {passport}.",
]


def generate_passport() -> str:
    """Генерирует случайный номер паспорта РФ."""
    region = random.randint(1, 99)
    year = random.randint(0, 24)
    number = random.randint(100000, 999999)
    return f"{region:02d} {year:02d} {number}"


def generate_snils() -> str:
    """Генерирует случайный СНИЛС (формат, без валидации контрольного числа)."""
    d = [random.randint(0, 9) for _ in range(9)]
    control = sum(d[i] * (9 - i) for i in range(9))
    if control < 100:
        check = control
    elif control in (100, 101):
        check = 0
    else:
        check = control % 101
        if check in (100, 101):
            check = 0
    return f"{''.join(map(str, d[:3]))}-{''.join(map(str, d[3:6]))}-{''.join(map(str, d[6:9]))} {check:02d}"


def generate_card() -> str:
    """Генерирует номер карты, валидный по алгоритму Луна."""
    # Префиксы Visa/MasterCard
    prefix = random.choice(["4276", "4532", "5425", "5321"])
    digits = [int(c) for c in prefix]

    # Генерируем 11 случайных цифр
    for _ in range(11):
        digits.append(random.randint(0, 9))

    # Вычисляем контрольную цифру по Луну
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:  # нечётные позиции с конца (0-indexed = чётные)
            n = d * 2
            total += n - 9 if n > 9 else n
        else:
            total += d
    check_digit = (10 - (total % 10)) % 10
    digits.append(check_digit)

    card = "".join(map(str, digits))
    return f"{card[:4]} {card[4:8]} {card[8:12]} {card[12:16]}"


def generate_account() -> str:
    """Генерирует номер расчётного счёта."""
    prefix = random.choice(["40817", "40820", "42301", "42601"])
    currency = random.choice(["810", "840", "978"])
    rest = "".join([str(random.randint(0, 9)) for _ in range(20 - len(prefix) - len(currency))])
    return prefix + currency + rest


def generate_phone() -> str:
    """Генерирует телефон в формате, который наш regex точно поймает."""
    code = random.choice(["999", "916", "495", "926", "903", "905", "915"])
    n1 = random.randint(100, 999)
    n2 = random.randint(10, 99)
    n3 = random.randint(10, 99)
    fmt = random.choice([
        f"+7 {code} {n1}-{n2}-{n3}",
        f"+7({code}){n1}-{n2}-{n3}",
        f"8{code}{n1}{n2}{n3}",
        f"+7-{code}-{n1}-{n2}-{n3}",
    ])
    return fmt


def generate_request() -> dict:
    """Генерирует один банковский запрос с PII."""
    template = random.choice(TEMPLATES)

    phone = generate_phone()  # ← наш формат вместо Faker

    data = {
        "name": fake.name(),
        "phone": phone,
        "email": fake.email(),
        "passport": generate_passport(),
        "snils": generate_snils(),
        "card": generate_card(),
        "account": generate_account(),
        "dob": fake.date_of_birth(minimum_age=18, maximum_age=80).strftime("%d.%m.%Y"),
        "amount": random.choice([500, 1000, 5000, 10000, 25000, 50000]),
    }

    text = template.format(**data)

    NON_PII_FIELDS = {"amount"}

    pii_present = {}
    for key, value in data.items():
        if key in NON_PII_FIELDS:
            continue
        if str(value) in text:
            pii_present[key] = str(value)

    return {
        "text": text,
        "pii_ground_truth": pii_present,
        "template_used": template,
    }

def generate_dataset(n: int = 1000) -> list[dict]:
    """Генерирует датасет из n банковских запросов."""
    return [generate_request() for _ in range(n)]


# ── CLI ────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    print("=== Генерация 10 примеров ===\n")
    for i, req in enumerate(generate_dataset(10), 1):
        print(f"[{i}] {req['text']}")
        print(f"    PII: {req['pii_ground_truth']}\n")

    # Сохраняем полный датасет
    dataset = generate_dataset(1000)
    with open("test_dataset.json", "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    print(f"\nСохранено {len(dataset)} записей в test_dataset.json")