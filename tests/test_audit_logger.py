"""pytest tests/test_audit_logger.py -v"""

import os
import pytest
from services.audit_logger import AuditLogger


@pytest.fixture
def audit(tmp_path):
    log_file = str(tmp_path / "test_audit.log")
    return AuditLogger(log_file=log_file)


class TestAuditLogging:

    def test_log_masking(self, audit):
        audit.log_masking(
            session_id="test-1",
            pii_types=["PHONE", "PERSON"],
            pii_count=2,
            masked_preview="Здравствуйте, [PERSON_1]...",
            latency_ms=5.2,
        )
        stats = audit.get_stats()
        assert stats["total_requests"] == 1
        assert stats["total_pii_masked"] == 2

    def test_log_leak(self, audit):
        audit.log_leak_detected(
            session_id="test-1",
            leaked_count=1,
            leaked_types=["PHONE"],
        )
        stats = audit.get_stats()
        assert stats["total_leaks_detected"] == 1

    def test_log_error(self, audit):
        audit.log_error("test-1", "NER crashed")
        stats = audit.get_stats()
        assert stats["total_errors"] == 1

    def test_avg_latency(self, audit):
        audit.log_masking("s1", ["PHONE"], 1, "...", 10.0)
        audit.log_masking("s2", ["EMAIL"], 1, "...", 20.0)
        stats = audit.get_stats()
        assert stats["avg_latency_ms"] == 15.0

    def test_log_file_created(self, audit):
        audit.log_masking("s1", [], 0, "test", 1.0)
        assert os.path.exists(audit.log_file)

    def test_multiple_operations(self, audit):
        for i in range(10):
            audit.log_masking(f"s-{i}", ["PHONE"], 1, "...", 5.0)
        stats = audit.get_stats()
        assert stats["total_requests"] == 10
        assert stats["total_pii_masked"] == 10