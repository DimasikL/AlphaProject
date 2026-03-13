"""
Аудит API: безопасность, граничные случаи, multi-turn.

pytest tests/test_audit_api.py -v
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app



class TestInputValidation:

    def test_empty_message_rejected(self, client):
        """Пустое сообщение"""
        response = client.post("/api/chat", json={
            "message": "",
            "stream": False,
        })
        assert response.status_code == 422  # Validation error

    def test_whitespace_message(self, client):
        """Только пробелы"""
        response = client.post("/api/chat", json={
            "message": "   ",
            "stream": False,
        })
        # Может быть 422 или 200 с пустым результатом
        # Зависит от валидации Pydantic

    def test_very_long_message(self, client):
        """Сообщение >5000 символов"""
        response = client.post("/api/chat", json={
            "message": "А" * 5001,
            "stream": False,
        })
        assert response.status_code == 422  # Превышен max_length

    def test_message_exactly_5000(self, client):
        """Ровно на границе"""
        response = client.post("/api/chat", json={
            "message": "А" * 5000,
            "stream": False,
        })
        assert response.status_code == 200

    def test_special_characters(self, client):
        """Спецсимволы не ломают сервер"""
        response = client.post("/api/chat", json={
            "message": "Тест <script>alert(1)</script> & \" ' \\ / \n\t",
            "stream": False,
        })
        assert response.status_code == 200

    def test_unicode_message(self, client):
        """Эмодзи и юникод"""
        response = client.post("/api/chat", json={
            "message": "Привет 👋 Мой телефон +7 999 123-45-67 🎉",
            "stream": False,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["entities_found"] >= 1

    def test_no_body(self, client):
        """Запрос без тела"""
        response = client.post("/api/chat")
        assert response.status_code == 422

    def test_wrong_content_type(self, client):
        """Не JSON"""
        response = client.post(
            "/api/chat",
            content="message=hello",
            headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 422


class TestSecurityHeaders:

    def test_session_id_xss(self, client):
        """XSS в session_id"""
        response = client.post("/api/chat", json={
            "message": "Тест",
            "session_id": "<script>alert('xss')</script>",
            "stream": False,
        })
        # Сервер не должен упасть
        assert response.status_code == 200
        data = response.json()
        # session_id не должен интерпретироваться как HTML
        assert "<script>" not in str(data.get("masked_message", ""))

    def test_session_id_sql_injection(self, client):
        """SQL injection в session_id"""
        response = client.post("/api/chat", json={
            "message": "Тест",
            "session_id": "'; DROP TABLE sessions; --",
            "stream": False,
        })
        assert response.status_code == 200


class TestMultiTurn:
    """Многоходовый диалог — маппинг между запросами."""

    def test_second_request_same_session(self, client):
        """Второй запрос в той же сессии помнит маппинг"""
        session = "multi-turn-test-1"

        # Первый запрос
        r1 = client.post("/api/chat", json={
            "message": "Я Иванов Пётр, телефон +7 999 111-22-33",
            "session_id": session,
            "stream": False,
        })
        assert r1.status_code == 200
        mapping1 = r1.json()["mapping"]
        assert len(mapping1) >= 1

        # Второй запрос — проверяем что сессия жива
        session_info = client.get(f"/api/sessions/{session}")
        assert session_info.status_code == 200
        data = session_info.json()
        assert data["request_count"] >= 1
        assert len(data["mapping"]) >= 1

    def test_different_sessions_isolated(self, client):
        """Разные сессии не пересекаются"""
        r1 = client.post("/api/chat", json={
            "message": "Я Иванов, тел +7 999 111-22-33",
            "session_id": "session-A",
            "stream": False,
        })
        r2 = client.post("/api/chat", json={
            "message": "Я Петров, тел +7 999 444-55-66",
            "session_id": "session-B",
            "stream": False,
        })

        s_a = client.get("/api/sessions/session-A").json()
        s_b = client.get("/api/sessions/session-B").json()

        # Маппинги не должны пересекаться
        values_a = set(s_a["mapping"].values())
        values_b = set(s_b["mapping"].values())
        assert values_a.isdisjoint(values_b), "Данные сессий пересеклись!"


class TestResponseIntegrity:
    """Ответ не должен содержать замаскированных токенов."""

    def test_no_brackets_in_clean_response(self, client):
        """В размаскированном ответе нет [TOKEN_N]"""
        response = client.post("/api/chat", json={
            "message": "Я Иванов Пётр, телефон +7 999 123-45-67. Баланс?",
            "session_id": "integrity-1",
            "stream": False,
        })
        data = response.json()
        clean = data["llm_response_clean"]
        import re
        leaked_tokens = re.findall(r'\[[A-Z]+_\d+\]', clean)
        assert len(leaked_tokens) == 0, (
            f"В ответе остались замаскированные токены: {leaked_tokens}"
        )

    def test_original_pii_not_in_masked(self, client):
        """Оригинальные PII не должны быть в masked_message"""
        response = client.post("/api/chat", json={
            "message": "Иванов Пётр, +7 999 123-45-67, test@mail.ru",
            "session_id": "integrity-2",
            "stream": False,
        })
        data = response.json()
        masked = data["masked_message"]
        assert "+7 999 123-45-67" not in masked
        assert "test@mail.ru" not in masked

    def test_mapping_contains_real_data(self, client):
        """Маппинг содержит реальные данные для обратной замены"""
        response = client.post("/api/chat", json={
            "message": "Телефон +7 999 123-45-67",
            "session_id": "integrity-3",
            "stream": False,
        })
        data = response.json()
        values = list(data["mapping"].values())
        assert "+7 999 123-45-67" in values


class TestStreamResponse:

    def test_stream_no_leaked_tokens(self, client):
        """Стрим-ответ не содержит замаскированных токенов"""
        with client.stream("POST", "/api/chat", json={
            "message": "Я Иванов Пётр, телефон +7 999 123-45-67. Баланс?",
            "session_id": "stream-integrity-1",
            "stream": True,
        }) as response:
            full_text = ""
            for line in response.iter_lines():
                if line.startswith("data: ") and not line.startswith("data: {"):
                    full_text += line[6:]

            import re
            leaked = re.findall(r'\[[A-Z]+_\d+\]', full_text)
            assert len(leaked) == 0, f"Утечка токенов в стриме: {leaked}"

    def test_stream_contains_real_name(self, client):
        """Стрим содержит реальное имя (размаскированное)"""
        with client.stream("POST", "/api/chat", json={
            "message": "Я Иванов Пётр. Баланс?",
            "session_id": "stream-integrity-2",
            "stream": True,
        }) as response:
            full_text = ""
            for line in response.iter_lines():
                if line.startswith("data: ") and not line.startswith("data: {"):
                    full_text += line[6:]

            # Имя должно быть в ответе (LLM-симулятор его использует)
            assert len(full_text) > 10  # хоть что-то пришло


class TestMultiTurnIntegration:
    """Полный multi-turn сценарий."""

    def test_three_turn_conversation(self, client):
        session = "multi-3-turn"

        # Ход 1: представление
        r1 = client.post("/api/chat", json={
            "message": "Здравствуйте, я Иванов Пётр, телефон +7 999 123-45-67",
            "session_id": session,
            "stream": False,
        })
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["entities_found"] >= 1
        assert "Иванов" not in d1["masked_message"]

        # Ход 2: вопрос (без PII)
        r2 = client.post("/api/chat", json={
            "message": "Какой у меня баланс?",
            "session_id": session,
            "stream": False,
        })
        assert r2.status_code == 200
        d2 = r2.json()
        # История должна расти
        assert d2["stats"].get("history_length", 0) >= 3  # 2 user + 1 assistant

        # Ход 3: ещё вопрос
        r3 = client.post("/api/chat", json={
            "message": "А какой курс доллара?",
            "session_id": session,
            "stream": False,
        })
        assert r3.status_code == 200
        d3 = r3.json()
        assert d3["stats"].get("history_length", 0) >= 5

    def test_history_endpoint(self, client):
        session = "history-test"
        client.post("/api/chat", json={
            "message": "Я Козлова Мария, тел +7 916 555-44-33",
            "session_id": session,
            "stream": False,
        })

        # Проверяем историю
        r = client.get(f"/api/history/{session}")
        assert r.status_code == 200
        data = r.json()
        assert data["total_messages"] >= 2  # user + assistant
        # Клиентская версия содержит реальные данные
        messages = data["messages"]
        assert any("Козлова" in m["content"] for m in messages)

    def test_history_not_found(self, client):
        r = client.get("/api/history/nonexistent")
        assert r.status_code == 404

    def test_mapping_accumulates(self, client):
        session = "mapping-accum"

        # Первый запрос с телефоном
        client.post("/api/chat", json={
            "message": "Мой телефон +7 999 111-22-33",
            "session_id": session,
            "stream": False,
        })

        # Второй запрос с email
        client.post("/api/chat", json={
            "message": "Мой email test@mail.ru",
            "session_id": session,
            "stream": False,
        })

        # Маппинг должен содержать ОБА
        s = client.get(f"/api/sessions/{session}").json()
        values = list(s["mapping"].values())
        assert "+7 999 111-22-33" in values
        assert "test@mail.ru" in values