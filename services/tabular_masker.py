"""
Маскирование PII в табличных данных (CSV, Excel).
"""

import csv
import io
import re
import logging
from dataclasses import dataclass, field

from services.masking_service import MaskingService

logger = logging.getLogger(__name__)


@dataclass
class TabularMaskingResult:
    """Результат маскирования таблицы."""
    masked_rows: list[dict]
    mapping: dict[str, str]
    stats: dict
    columns_with_pii: list[str]


class TabularMasker:
    """
    Маскирует PII в табличных данных.
    Поддерживает: CSV строки, list[dict], JSON.
    """

    PII_COLUMN_HINTS = {
        "name", "имя", "фио", "фамилия", "отчество",
        "phone", "телефон", "тел", "mobile",
        "email", "почта", "e-mail",
        "passport", "паспорт",
        "snils", "снилс",
        "inn", "инн",
        "card", "карта", "card_number",
        "account", "счёт", "счет",
        "address", "адрес",
        "dob", "дата_рождения", "birth_date", "birthdate",
    }

    # Паттерн для извлечения типа из токена
    TOKEN_PATTERN = re.compile(r'\[([A-Z]+)_\d+\]')

    def __init__(self, use_ner: bool = True):
        self.masking_service = MaskingService(use_ner=use_ner)

    def mask_rows(self, rows: list[dict]) -> TabularMaskingResult:
        global_mapping = {}
        masked_rows = []
        total_found = 0
        pii_by_column = {}
        counter = 0

        for row in rows:
            masked_row = {}
            for col_name, cell_value in row.items():
                if cell_value is None or str(cell_value).strip() == "":
                    masked_row[col_name] = cell_value
                    continue

                cell_str = str(cell_value)

                should_check = (
                        self._is_pii_column(col_name) or
                        len(cell_str) > 3
                )

                if should_check:
                    result = self.masking_service.mask(cell_str)
                    if result.mapping:
                        renamed_mapping = {}
                        for token, original in result.mapping.items():
                            counter += 1
                            match = self.TOKEN_PATTERN.match(token)
                            entity_type = match.group(1) if match else "PII"
                            new_token = f"[{entity_type}_{counter}]"
                            renamed_mapping[token] = new_token
                            global_mapping[new_token] = original

                        masked_cell = result.masked_text
                        for old_token, new_token in renamed_mapping.items():
                            masked_cell = masked_cell.replace(old_token, new_token)

                        masked_row[col_name] = masked_cell
                        total_found += result.stats.get("total_found", 0)
                        pii_by_column[col_name] = pii_by_column.get(col_name, 0) + len(result.mapping)
                    else:
                        masked_row[col_name] = cell_str
                else:
                    masked_row[col_name] = cell_str

            masked_rows.append(masked_row)

        return TabularMaskingResult(
            masked_rows=masked_rows,
            mapping=global_mapping,
            stats={
                "total_rows": len(rows),
                "total_pii_found": total_found,
                "pii_by_column": pii_by_column,
            },
            columns_with_pii=list(pii_by_column.keys()),
        )

    def mask_csv(self, csv_content: str) -> tuple[str, dict[str, str]]:
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)

        if not rows:
            return csv_content, {}

        result = self.mask_rows(rows)

        output = io.StringIO()
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(result.masked_rows)

        return output.getvalue(), result.mapping

    def _is_pii_column(self, column_name: str) -> bool:
        clean = column_name.lower().strip().replace(" ", "_")
        return clean in self.PII_COLUMN_HINTS