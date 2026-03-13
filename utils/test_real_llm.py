"""
Тест полного pipeline с реальным Mistral API.
Запуск: python utils/test_real_llm.py
"""

import asyncio
import sys
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

from config import config


async def test_real_llm():
    if not config.LLM_API_KEY:
        print("❌ LLM_API_KEY не задан в .env")
        return

    from services.llm_client import LLMClient, LLMConfig, SYSTEM_PROMPT_MASKED
    from services.masking_service import MaskingService
    from services.unmasking_stream import StreamInterceptor, TokenFormat

    print("=" * 60)
    print("ТЕСТ РЕАЛЬНОГО LLM (Mistral)")
    print("=" * 60)

    # 1. Маскирование
    service = MaskingService(use_ner=True)
    user_msg = "Здравствуйте, я Иванов Пётр, телефон +7 999 123-45-67. Какой у меня баланс?"

    result = service.mask(user_msg)
    print(f"\n📝 Оригинал:    {user_msg}")
    print(f"🔒 Маскировано: {result.masked_text}")
    print(f"🗂  Маппинг:     {result.mapping}")

    # 2. Отправка в LLM
    client = LLMClient(LLMConfig(
        api_url=config.LLM_API_URL,
        api_key=config.LLM_API_KEY,
        model=config.LLM_MODEL,
    ))

    messages = [{"role": "user", "content": result.masked_text}]

    print(f"\n🤖 Стрим от {config.LLM_MODEL}:")
    print("   ", end="", flush=True)

    interceptor = StreamInterceptor(result.mapping, fmt=TokenFormat.BRACKET)
    full_masked = ""
    full_clean = ""

    async for chunk in client.chat_stream(messages, system_prompt=SYSTEM_PROMPT_MASKED):
        full_masked += chunk
        clean = interceptor.feed(chunk)
        if clean:
            print(clean, end="", flush=True)
            full_clean += clean

    remaining = interceptor.flush()
    if remaining:
        print(remaining, end="", flush=True)
        full_clean += remaining

    print("\n")

    # 3. Проверки
    import re
    leaked_tokens = re.findall(r'\[[A-Z]+_\d+\]', full_clean)

    print("=" * 60)
    print("РЕЗУЛЬТАТ")
    print("=" * 60)
    print(f"  Замаскированный ответ LLM: {full_masked[:100]}...")
    print(f"  Чистый ответ клиенту:      {full_clean[:100]}...")
    print(f"  Утечки токенов:            {'❌ ' + str(leaked_tokens) if leaked_tokens else '✅ нет'}")
    print(f"  Interceptor stats:         {interceptor.stats}")

    await client.close()

    if leaked_tokens:
        print("\n⚠️  ВНИМАНИЕ: LLM изменила формат токенов!")
        print("    Возможные решения:")
        print("    1. Улучшить system prompt")
        print("    2. Использовать XML-формат токенов")
        print("    3. Добавить fuzzy matching в StreamInterceptor")
    else:
        print("\n✅ Полный pipeline работает корректно!")


if __name__ == "__main__":
    asyncio.run(test_real_llm())