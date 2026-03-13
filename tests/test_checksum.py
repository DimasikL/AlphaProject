"""pytest tests/test_checksum.py -v"""

import pytest
from detectors.checksum_validator import (
    is_valid_inn_personal,
    is_valid_inn_company,
    is_valid_inn,
    is_valid_snils,
    is_valid_card_luhn,
    is_valid_passport_series,
    is_valid_account_number,
)


class TestINN:
    def test_valid_inn_12(self):
        # ИНН физлица: 500100732259 (реальный формат, тестовое значение)
        assert is_valid_inn("500100732259") is True

    def test_valid_inn_10(self):
        # ИНН юрлица: 7707083893 (Сбербанк)
        assert is_valid_inn("7707083893") is True

    def test_invalid_inn_wrong_checksum(self):
        assert is_valid_inn("500100732250") is False

    def test_invalid_inn_short(self):
        assert is_valid_inn("12345") is False

    def test_invalid_inn_letters(self):
        assert is_valid_inn("50010073225a") is False


class TestSNILS:
    def test_valid_snils(self):
        assert is_valid_snils("112-233-445 95") is True

    def test_invalid_snils(self):
        assert is_valid_snils("112-233-445 00") is False

    def test_snils_short(self):
        assert is_valid_snils("123-456") is False


class TestCard:
    def test_valid_visa(self):
        assert is_valid_card_luhn("4276123456789012") is False  # случайный — скорее невалидный
        assert is_valid_card_luhn("4532015112830366") is True   # тестовый номер Луна

    def test_valid_mastercard(self):
        assert is_valid_card_luhn("5425233430109903") is True   # тестовый

    def test_invalid_card(self):
        assert is_valid_card_luhn("1234567890123456") is False

    def test_short_number(self):
        assert is_valid_card_luhn("1234") is False


class TestPassport:
    def test_valid_series(self):
        assert is_valid_passport_series("4515") is True
        assert is_valid_passport_series("01 20") is True

    def test_invalid_series(self):
        assert is_valid_passport_series("0015") is False  # регион 00 — невалидный
        # но наша проверка проста: 01-99

    def test_short(self):
        assert is_valid_passport_series("45") is False


class TestAccount:
    def test_valid_account(self):
        assert is_valid_account_number("40817810099910004312") is True

    def test_invalid_prefix(self):
        assert is_valid_account_number("12345678901234567890") is False

    def test_short(self):
        assert is_valid_account_number("4081781009991") is False