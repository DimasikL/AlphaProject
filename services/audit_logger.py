"""
Аудит-логирование для compliance.
Банк требует: кто, когда, какие PII были обработаны.
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class AuditRecord:
    """Одна запись аудита."""
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    action: str = ""           # "mask", "unmask", "leak_detected", "request", "response"
    pii_types_found: list[str] = field(default_factory=list)
    pii_count: int = 0
    masked_text_preview: str = ""   # первые 100 символов (без PII!)
    latency_ms: float = 0
    leaked_pii_count: int = 0
    success: bool = True
    error: str = ""


class AuditLogger:
    """
    Логирует все операции с PII для compliance.
    В проде — отправка в SIEM / ELK.
    На хакатоне — файл + stdout.
    """

    def __init__(self, log_file: str = "audit.log"):
        self.log_file = Path(log_file)
        self.logger = logging.getLogger("audit")

        # Файловый handler
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

        self._records: list[AuditRecord] = []

    def log_masking(
            self,
            session_id: str,
            pii_types: list[str],
            pii_count: int,
            masked_preview: str,
            latency_ms: float,
    ):
        record = AuditRecord(
            session_id=session_id,
            action="mask",
            pii_types_found=pii_types,
            pii_count=pii_count,
            masked_text_preview=masked_preview[:100],
            latency_ms=latency_ms,
        )
        self._emit(record)

    def log_leak_detected(
            self,
            session_id: str,
            leaked_count: int,
            leaked_types: list[str],
    ):
        record = AuditRecord(
            session_id=session_id,
            action="leak_detected",
            pii_types_found=leaked_types,
            leaked_pii_count=leaked_count,
        )
        self._emit(record)

    def log_error(self, session_id: str, error: str):
        record = AuditRecord(
            session_id=session_id,
            action="error",
            success=False,
            error=error,
        )
        self._emit(record)

    def get_stats(self) -> dict:
        """Статистика для дашборда."""
        total = len(self._records)
        masks = [r for r in self._records if r.action == "mask"]
        leaks = [r for r in self._records if r.action == "leak_detected"]
        errors = [r for r in self._records if not r.success]

        total_pii = sum(r.pii_count for r in masks)
        avg_latency = (
            sum(r.latency_ms for r in masks) / len(masks)
            if masks else 0
        )

        return {
            "total_requests": total,
            "total_pii_masked": total_pii,
            "total_leaks_detected": len(leaks),
            "total_errors": len(errors),
            "avg_latency_ms": round(avg_latency, 2),
        }

    def _emit(self, record: AuditRecord):
        self._records.append(record)
        self.logger.info(json.dumps(asdict(record), ensure_ascii=False))