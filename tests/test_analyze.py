"""pytest tests/test_analyze.py -v"""

import pytest
from fastapi.testclient import TestClient
from api.main import app


class TestAnalyzeEndpoint:

    def test_analyze_basic(self, client):
        response = client.post("/api/analyze", json={
            "message": "Я Иванов Пётр, телефон +7 999 123-45-67",
            "stream": False,
        })
        assert response.status_code == 200
        data = response.json()
        assert "original" in data
        assert "masked" in data
        assert "entities" in data
        assert "highlighted_html" in data
        assert "mapping" in data

    def test_analyze_finds_entities(self, client):
        response = client.post("/api/analyze", json={
            "message": "Телефон +7 999 123-45-67, email test@mail.ru",
            "stream": False,
        })
        data = response.json()
        types = [e["type"] for e in data["entities"]]
        assert "PHONE" in types
        assert "EMAIL" in types

    def test_analyze_highlighted_html_contains_spans(self, client):
        response = client.post("/api/analyze", json={
            "message": "Телефон +7 999 123-45-67",
            "stream": False,
        })
        data = response.json()
        assert "<span" in data["highlighted_html"]
        assert "+7 999 123-45-67" in data["highlighted_html"]

    def test_analyze_no_pii(self, client):
        response = client.post("/api/analyze", json={
            "message": "Какой курс доллара?",
            "stream": False,
        })
        data = response.json()
        assert len(data["entities"]) == 0
        assert data["masked"] == "Какой курс доллара?"

    def test_analyze_complex(self, client):
        response = client.post("/api/analyze", json={
            "message": (
                "Петров Алексей, паспорт 45 15 123456, "
                "телефон +7 916 555-44-33, email petrov@gmail.com, "
                "дата рождения 01.05.1985"
            ),
            "stream": False,
        })
        data = response.json()
        assert len(data["entities"]) >= 4
        assert len(data["mapping"]) >= 4
        # PII не должны быть в masked
        assert "+7 916 555-44-33" not in data["masked"]
        assert "petrov@gmail.com" not in data["masked"]

    def test_analyze_entity_fields(self, client):
        response = client.post("/api/analyze", json={
            "message": "Телефон +7 999 123-45-67",
            "stream": False,
        })
        data = response.json()
        entity = data["entities"][0]
        assert "type" in entity
        assert "value" in entity
        assert "start" in entity
        assert "end" in entity
        assert "confidence" in entity
        assert "validated" in entity

    def test_analyze_html_escaping(self, client):
        """HTML-символы не должны ломать подсветку."""
        response = client.post("/api/analyze", json={
            "message": "Тест <script> и телефон +7 999 123-45-67",
            "stream": False,
        })
        data = response.json()
        assert "<script>" not in data["highlighted_html"]
        assert "&lt;script&gt;" in data["highlighted_html"]