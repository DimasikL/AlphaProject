"""
Аудит SessionStore: TTL, конкурентность, edge cases.

pytest tests/test_audit_session_store.py -v
"""

import time
import threading
import pytest
from services.session_store import SessionStore


class TestSessionTTL:

    def test_session_expires(self):
        """Сессия удаляется после TTL"""
        store = SessionStore(ttl_seconds=1)
        store.get_or_create("exp-1")
        store.save_mapping("exp-1", {"[PER_1]": "Тест"})

        assert store.get("exp-1") is not None

        time.sleep(1.5)  # ждём больше TTL

        # Следующий вызов должен очистить
        store.get_or_create("trigger-cleanup")
        assert store.get("exp-1") is None

    def test_session_refreshed_on_update(self):
        """Обновление сессии продлевает TTL"""
        store = SessionStore(ttl_seconds=2)
        store.get_or_create("refresh-1")

        time.sleep(1)
        store.save_mapping("refresh-1", {"[PER_1]": "Тест"})

        time.sleep(1.5)
        # Прошло 2.5 сек с создания, но 1.5 с обновления — TTL=2
        store.get_or_create("trigger")
        assert store.get("refresh-1") is not None


class TestSessionConcurrency:

    def test_concurrent_access(self):
        """Несколько потоков пишут в разные сессии"""
        store = SessionStore()
        errors = []

        def worker(session_id):
            try:
                for i in range(100):
                    store.save_mapping(session_id, {f"[T_{i}]": f"v_{i}"})
                    store.get_mapping(session_id)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(f"thread-{i}",))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Ошибки при конкурентном доступе: {errors}"

    def test_concurrent_same_session(self):
        """Несколько потоков пишут в ОДНУ сессию"""
        store = SessionStore()
        session_id = "shared-session"

        def worker(prefix):
            for i in range(50):
                store.save_mapping(session_id, {f"[{prefix}_{i}]": f"val_{i}"})

        threads = [
            threading.Thread(target=worker, args=(f"W{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        mapping = store.get_mapping(session_id)
        # Все 250 записей должны быть сохранены
        assert len(mapping) == 250


class TestSessionEdgeCases:

    def test_empty_session_id(self):
        store = SessionStore()
        session = store.get_or_create("")
        assert session.session_id == ""

    def test_very_long_session_id(self):
        store = SessionStore()
        long_id = "x" * 10000
        session = store.get_or_create(long_id)
        assert session.session_id == long_id

    def test_merge_mapping_preserves_old(self):
        """Новый маппинг не затирает старый"""
        store = SessionStore()
        store.save_mapping("merge-test", {"[A]": "1", "[B]": "2"})
        store.save_mapping("merge-test", {"[C]": "3"})

        mapping = store.get_mapping("merge-test")
        assert mapping == {"[A]": "1", "[B]": "2", "[C]": "3"}

    def test_delete_nonexistent(self):
        """Удаление несуществующей сессии не падает"""
        store = SessionStore()
        store.delete("ghost")  # не должно быть исключения

    def test_list_sessions_format(self):
        store = SessionStore()
        store.get_or_create("list-1")
        store.get_or_create("list-2")
        sessions = store.list_sessions()
        assert len(sessions) >= 2
        for s in sessions:
            assert "session_id" in s
            assert "request_count" in s
            assert "age_seconds" in s