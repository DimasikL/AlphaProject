"""
Валидация PII по контрольным суммам.
Снижает false positives: не каждые 12 цифр — это ИНН.
"""


def is_valid_inn_personal(inn: str) -> bool:
    """ИНН физлица — 12 цифр с двумя контрольными разрядами."""
    digits = inn.replace(" ", "").replace("-", "")
    if len(digits) != 12 or not digits.isdigit():
        return False
    d = [int(c) for c in digits]
    weights_11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    weights_12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    check_11 = sum(d[i] * weights_11[i] for i in range(10)) % 11 % 10
    check_12 = sum(d[i] * weights_12[i] for i in range(11)) % 11 % 10
    return d[10] == check_11 and d[11] == check_12


def is_valid_inn_company(inn: str) -> bool:
    """ИНН юрлица — 10 цифр с одним контрольным разрядом."""
    digits = inn.replace(" ", "").replace("-", "")
    if len(digits) != 10 or not digits.isdigit():
        return False
    d = [int(c) for c in digits]
    weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    check = sum(d[i] * weights[i] for i in range(9)) % 11 % 10
    return d[9] == check


def is_valid_inn(inn: str) -> bool:
    """ИНН — 10 или 12 цифр."""
    clean = inn.replace(" ", "").replace("-", "")
    if len(clean) == 12:
        return is_valid_inn_personal(clean)
    elif len(clean) == 10:
        return is_valid_inn_company(clean)
    return False


def is_valid_snils(snils: str) -> bool:
    """
    СНИЛС — 11 цифр, формат XXX-XXX-XXX XX.
    Контрольное число — последние 2 цифры.
    """
    digits = "".join(c for c in snils if c.isdigit())
    if len(digits) != 11:
        return False

    d = [int(c) for c in digits]
    # Контрольная сумма по первым 9 цифрам
    control_sum = sum(d[i] * (9 - i) for i in range(9))

    if control_sum < 100:
        check = control_sum
    elif control_sum in (100, 101):
        check = 0
    else:
        check = control_sum % 101
        if check in (100, 101):
            check = 0

    actual_check = d[9] * 10 + d[10]
    return actual_check == check


def is_valid_card_luhn(number: str) -> bool:
    """Алгоритм Луна для банковских карт (13-19 цифр)."""
    digits = "".join(c for c in number if c.isdigit())
    if len(digits) < 13 or len(digits) > 19:
        return False

    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def is_valid_passport_series(series: str) -> bool:
    """
    Серия паспорта РФ — 4 цифры.
    Первые 2 — код региона (01-99), вторые 2 — год выдачи.
    """
    digits = "".join(c for c in series if c.isdigit())
    if len(digits) != 4:
        return False
    region = int(digits[:2])
    return 1 <= region <= 99


def is_valid_account_number(account: str) -> bool:
    """
    Расчётный счёт — 20 цифр.
    Базовая проверка: начинается с допустимых префиксов.
    """
    digits = "".join(c for c in account if c.isdigit())
    if len(digits) != 20:
        return False
    # Расчётные счета физлиц начинаются с 408, 423, 426
    # Юрлиц — 407, 405, 406
    valid_prefixes = ("405", "406", "407", "408", "423", "426", "302", "301")
    return digits.startswith(valid_prefixes)