"""pytest tests/test_tabular_masker.py -v"""

import pytest
from services.tabular_masker import TabularMasker


@pytest.fixture
def masker():
    return TabularMasker(use_ner=False)


class TestTabularBasic:

    def test_mask_single_row(self, masker):
        rows = [{"name": "Иванов Пётр", "phone": "+7 999 123-45-67", "amount": "5000"}]
        result = masker.mask_rows(rows)
        assert "+7 999 123-45-67" not in str(result.masked_rows)
        assert len(result.mapping) >= 1

    def test_mask_multiple_rows(self, masker):
        rows = [
            {"name": "Иванов", "phone": "+7 999 111-22-33"},
            {"name": "Петров", "phone": "+7 999 444-55-66"},
        ]
        result = masker.mask_rows(rows)
        assert "+7 999 111-22-33" not in str(result.masked_rows)
        assert "+7 999 444-55-66" not in str(result.masked_rows)
        assert result.stats["total_rows"] == 2

    def test_mask_csv_string(self, masker):
        csv_content = "name,phone,amount\nИванов,+7 999 123-45-67,5000\n"
        masked_csv, mapping = masker.mask_csv(csv_content)
        assert "+7 999 123-45-67" not in masked_csv
        assert len(mapping) >= 1

    def test_empty_rows(self, masker):
        result = masker.mask_rows([])
        assert result.masked_rows == []
        assert result.mapping == {}

    def test_no_pii_in_table(self, masker):
        rows = [{"product": "Кредит", "rate": "12%"}]
        result = masker.mask_rows(rows)
        assert result.stats["total_pii_found"] == 0

    def test_none_values(self, masker):
        rows = [{"name": None, "phone": "+7 999 123-45-67"}]
        result = masker.mask_rows(rows)
        assert result.masked_rows[0]["name"] is None

    def test_pii_column_detection(self, masker):
        assert masker._is_pii_column("телефон") is True
        assert masker._is_pii_column("фио") is True
        assert masker._is_pii_column("amount") is False

    def test_columns_with_pii_tracked(self, masker):
        rows = [{"phone": "+7 999 123-45-67", "city": "Москва"}]
        result = masker.mask_rows(rows)
        assert "phone" in result.columns_with_pii

    def test_mapping_is_unique_across_rows(self, masker):
        rows = [
            {"phone": "+7 999 111-22-33"},
            {"phone": "+7 999 444-55-66"},
        ]
        result = masker.mask_rows(rows)
        tokens = list(result.mapping.keys())
        assert len(tokens) == len(set(tokens)), "Дубликаты токенов между строками"

    def test_reversibility(self, masker):
        rows = [{"phone": "+7 999 123-45-67", "email": "test@mail.ru"}]
        result = masker.mask_rows(rows)
        masked_str = str(result.masked_rows)
        restored = masked_str
        for token, original in result.mapping.items():
            restored = restored.replace(token, original)
        assert "+7 999 123-45-67" in restored
        assert "test@mail.ru" in restored