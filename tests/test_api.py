"""
pytest tests/test_api.py -v

Тесты API через TestClient (без реального сервера).
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app


class TestHealth:
    def test_health_endpoint(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestChatSync:
    def test_sync_basic(self, client):
        response = client.post("/api/chat", json={
            "message": "Привет, я Иванов Пётр, телефон +7 999 123-45-67",
            "session_id": "test-1",
            "stream": False,
        })
        assert response.status_code == 200
        data = response.json()

        # PII замаскированы
        assert "Иванов" not in data["masked_message"] or "PERSON" in data["masked_message"]
        assert "+7 999 123-45-67" not in data["masked_message"]

        # Ответ LLM размаскирован
        assert "[PHONE_" not in data["llm_response_clean"]
        assert data["entities_found"] >= 1

    def test_sync_no_pii(self, client):
        response = client.post("/api/chat", json={
            "message": "Какой курс доллара сегодня?",
            "session_id": "test-2",
            "stream": False,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["entities_found"] == 0
        assert data["masked_message"] == "Какой курс доллара сегодня?"

    def test_sync_full_bank_request(self, client):
        response = client.post("/api/chat", json={
            "message": (
                "Здравствуйте, я Петров Алексей, паспорт 45 15 123456, "
                "телефон +7 916 555-44-33, email petrov@gmail.com"
            ),
            "session_id": "test-3",
            "stream": False,
        })
        data = response.json()
        assert data["entities_found"] >= 3
        assert len(data["mapping"]) >= 3

    def test_sync_mapping_is_populated(self, client):
        response = client.post("/api/chat", json={
            "message": "Меня зовут Козлова Мария, телефон +7 999 111-22-33",
            "session_id": "test-4",
            "stream": False,
        })
        data = response.json()
        mapping = data["mapping"]
        # Маппинг содержит реальные данные
        values = list(mapping.values())
        assert any("+7 999 111-22-33" in v for v in values)


class TestChatStream:
    def test_stream_returns_sse(self, client):
        with client.stream("POST", "/api/chat", json={
            "message": "Я Иванов, телефон +7 999 123-45-67. Баланс?",
            "session_id": "test-stream-1",
            "stream": True,
        }) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            full_text = ""
            for line in response.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if not data.startswith("{"):
                        full_text += data

            # Ответ не должен содержать токены-заглушки
            assert "[PHONE_" not in full_text
            assert "[PERSON_" not in full_text
            assert len(full_text) > 10  # что-то пришло


class TestSessions:
    def test_session_created(self, client):
        client.post("/api/chat", json={
            "message": "Я Иванов, телефон +7 999 123-45-67",
            "session_id": "sess-test-1",
            "stream": False,
        })

        response = client.get("/api/sessions/sess-test-1")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "sess-test-1"
        assert data["request_count"] >= 1
        assert len(data["mapping"]) >= 1

    def test_session_not_found(self, client):
        response = client.get("/api/sessions/nonexistent")
        assert response.status_code == 404

    def test_session_delete(self, client):
        client.post("/api/chat", json={
            "message": "Тест",
            "session_id": "sess-to-delete",
            "stream": False,
        })
        response = client.delete("/api/sessions/sess-to-delete")
        assert response.status_code == 200

        response = client.get("/api/sessions/sess-to-delete")
        assert response.status_code == 404

    def test_list_sessions(self, client):
        response = client.get("/api/sessions")
        assert response.status_code == 200
        assert isinstance(response.json(), list)