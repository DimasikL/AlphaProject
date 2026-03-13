"""pytest tests/test_chat_history.py -v"""

import pytest
from services.chat_history import ChatHistory


class TestChatHistory:

    def test_add_user_message(self):
        history = ChatHistory()
        history.add_user_message(
            original="Я Иванов, тел +7 999 123-45-67",
            masked="Я [PERSON_1], тел [PHONE_1]",
        )
        assert len(history) == 1

    def test_add_assistant_message(self):
        history = ChatHistory()
        history.add_user_message("Привет", "Привет")
        history.add_assistant_message(
            masked_response="Здравствуйте, [PERSON_1]!",
            clean_response="Здравствуйте, Иванов!",
        )
        assert len(history) == 2

    def test_messages_for_llm_are_masked(self):
        history = ChatHistory()
        history.add_user_message(
            original="Я Иванов",
            masked="Я [PERSON_1]",
        )
        messages = history.get_messages_for_llm()
        assert messages[0]["content"] == "Я [PERSON_1]"
        assert messages[0]["role"] == "user"

    def test_messages_for_client_are_original(self):
        history = ChatHistory()
        history.add_user_message(
            original="Я Иванов",
            masked="Я [PERSON_1]",
        )
        messages = history.get_messages_for_client()
        assert messages[0]["content"] == "Я Иванов"

    def test_trim_at_max(self):
        history = ChatHistory(max_messages=3)
        for i in range(5):
            history.add_user_message(f"msg-{i}", f"masked-{i}")
        assert len(history) == 3
        # Должны остаться последние 3
        messages = history.get_messages_for_llm()
        assert messages[0]["content"] == "masked-2"

    def test_multi_turn_format(self):
        history = ChatHistory()
        history.add_user_message("Я Иванов", "[PERSON_1]")
        history.add_assistant_message("Здравствуйте, [PERSON_1]!", "Здравствуйте, Иванов!")
        history.add_user_message("Мой баланс?", "Мой баланс?")

        llm_messages = history.get_messages_for_llm()
        assert len(llm_messages) == 3
        assert llm_messages[0]["role"] == "user"
        assert llm_messages[1]["role"] == "assistant"
        assert llm_messages[2]["role"] == "user"
        # Все замаскированы
        assert "Иванов" not in str(llm_messages)

    def test_empty_history(self):
        history = ChatHistory()
        assert history.get_messages_for_llm() == []
        assert history.get_messages_for_client() == []