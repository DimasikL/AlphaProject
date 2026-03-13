"""
Эндпоинты API — финальная версия.
Multi-turn с историей, fallback, audit, output scan.
"""

import json
import re
import time
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from api.schemas import ChatRequest, ChatResponseSync, HealthResponse, SessionInfo
from services.masking_service import MaskingService
from services.unmasking_stream import StreamInterceptor, TokenFormat
from services.session_store import SessionStore
from services.output_scanner import OutputScanner
from services.audit_logger import AuditLogger
from config import config

logger = logging.getLogger(__name__)

# ── Инициализация ──────────────────────────────────────────
router = APIRouter()

try:
    masking_service = MaskingService(use_ner=config.USE_NER)
    logger.info("MaskingService инициализирован с NER=%s", config.USE_NER)
except Exception as e:
    logger.warning(f"NER fallback на regex: {e}")
    masking_service = MaskingService(use_ner=False)

session_store = SessionStore(ttl_seconds=config.SESSION_TTL_SECONDS)
output_scanner = OutputScanner(use_ner=False)
audit = AuditLogger(log_file=config.AUDIT_LOG_FILE)

# LLM
if config.USE_MOCK_LLM or not config.LLM_API_KEY:
    from mocks.llm_simulator import async_llm_stream, generate_llm_response
    llm_client = None
    if not config.LLM_API_KEY and not config.USE_MOCK_LLM:
        logger.warning("LLM_API_KEY не задан — используется Mock LLM")
    else:
        logger.info("Mock LLM")
else:
    from services.llm_client import LLMClient, LLMConfig, SYSTEM_PROMPT_MASKED
    llm_client = LLMClient(LLMConfig(
        api_url=config.LLM_API_URL,
        api_key=config.LLM_API_KEY,
        model=config.LLM_MODEL,
    ))
    logger.info(f"Real LLM: {config.LLM_MODEL}")


# ── /health ────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health():
    sessions = session_store.list_sessions()
    return HealthResponse(
        status="ok",
        version="0.1.0",
        active_sessions=len(sessions),
    )


# ── /chat ──────────────────────────────────────────────────

@router.post("/chat")
async def chat(request: ChatRequest):
    start_time = time.time()

    # 1. Маскирование текущего сообщения
    try:
        session = session_store.get_or_create(request.session_id)
        masking_result = masking_service.mask(request.message, session=session)
    except Exception as e:
        logger.error(f"Masking error: {e}")
        audit.log_error(request.session_id, str(e))
        raise HTTPException(status_code=500, detail="Ошибка маскирования PII")

    latency_ms = (time.time() - start_time) * 1000

    # 2. Сохраняем маппинг в сессию
    session_store.save_mapping(request.session_id, masking_result.mapping)
    full_mapping = session_store.get_mapping(request.session_id)

    # 3. Добавляем сообщение в историю чата
    history = session_store.get_history(request.session_id)
    history.add_user_message(
        original=request.message,
        masked=masking_result.masked_text,
    )

    # 4. Аудит
    if config.AUDIT_ENABLED:
        audit.log_masking(
            session_id=request.session_id,
            pii_types=list(masking_result.stats.get("by_type", {}).keys()),
            pii_count=masking_result.stats.get("total_found", 0),
            masked_preview=masking_result.masked_text[:100],
            latency_ms=latency_ms,
        )

    logger.info(
        f"[{request.session_id}] "
        f"PII: {masking_result.stats.get('total_found', 0)} | "
        f"{latency_ms:.1f}ms | "
        f"History: {len(history)} msgs"
    )

    if not request.stream:
        return await _sync_response(request, masking_result, full_mapping, history, start_time)

    return StreamingResponse(
        _sse_generator(masking_result, full_mapping, history, request.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-Id": request.session_id,
            "X-PII-Found": str(masking_result.stats.get("total_found", 0)),
        },
    )


async def _sse_generator(masking_result, mapping, history, session_id):
    interceptor = StreamInterceptor(mapping, fmt=TokenFormat.BRACKET)

    meta = json.dumps({
        "type": "meta",
        "session_id": session_id,
        "masked_query": masking_result.masked_text,
        "mapping": masking_result.mapping,
        "history_length": len(history),
    }, ensure_ascii=False)
    yield f"event: meta\ndata: {meta}\n\n"

    full_response_masked = ""
    full_response_clean = ""

    # Выбираем источник LLM
    if llm_client is None:
        stream = async_llm_stream(masking_result.masked_text)
    else:
        # Multi-turn: отправляем ВСЮ историю
        messages = history.get_messages_for_llm()
        stream = llm_client.chat_stream(messages, system_prompt=SYSTEM_PROMPT_MASKED)

    async for chunk in stream:
        full_response_masked += chunk
        clean_chunk = interceptor.feed(chunk)
        if clean_chunk:
            safe_chunk = clean_chunk.replace("\n", "\u2028")  # Unicode line separator, не ломает SSE
            yield f"data: {safe_chunk}\n\n"
            full_response_clean += clean_chunk

    remaining = interceptor.flush()
    if remaining:
        yield f"data: {remaining}\n\n"
        full_response_clean += remaining

    # Сохраняем ответ ассистента в историю
    history.add_assistant_message(
        masked_response=full_response_masked,
        clean_response=full_response_clean,
    )

    # Сканирование на утечки
    leaked_count = 0
    if config.SCAN_LLM_OUTPUT:
        leaked = output_scanner.scan(full_response_clean, mapping)
        leaked_count = len(leaked)
        if leaked:
            audit.log_leak_detected(
                session_id=session_id,
                leaked_count=len(leaked),
                leaked_types=[e.entity_type for e in leaked],
            )

    done_data = json.dumps({
        "type": "done",
        "stats": {
            **interceptor.stats,
            "leaked_pii_in_response": leaked_count,
            "history_length": len(history),
        },
    }, ensure_ascii=False)
    yield f"event: done\ndata: {done_data}\n\n"


async def _sync_response(request, masking_result, full_mapping, history, start_time):
    if llm_client is None:
        llm_response_masked = generate_llm_response(masking_result.masked_text)
    else:
        messages = history.get_messages_for_llm()
        llm_response_masked = await llm_client.chat_sync(
            messages, system_prompt=SYSTEM_PROMPT_MASKED
        )

    interceptor = StreamInterceptor(full_mapping, fmt=TokenFormat.BRACKET)
    llm_response_clean = interceptor.feed(llm_response_masked)
    llm_response_clean += interceptor.flush()

    # Сохраняем в историю
    history.add_assistant_message(
        masked_response=llm_response_masked,
        clean_response=llm_response_clean,
    )

    # Сканирование на утечки
    leaked = []
    if config.SCAN_LLM_OUTPUT:
        leaked = output_scanner.scan(llm_response_clean, full_mapping)
        if leaked:
            llm_response_clean = output_scanner.mask_leaked(llm_response_clean, leaked)
            audit.log_leak_detected(
                session_id=request.session_id,
                leaked_count=len(leaked),
                leaked_types=[e.entity_type for e in leaked],
            )

    elapsed = round((time.time() - start_time) * 1000, 1)

    return ChatResponseSync(
        original_message=request.message,
        masked_message=masking_result.masked_text,
        llm_response_masked=llm_response_masked,
        llm_response_clean=llm_response_clean,
        mapping=masking_result.mapping,
        entities_found=masking_result.stats.get("total_found", 0),
        stats={
            **masking_result.stats,
            "latency_ms": elapsed,
            "interceptor": interceptor.stats,
            "leaked_pii_in_response": len(leaked),
            "history_length": len(history),
        },
    )



@router.post("/analyze")
async def analyze_pii(request: ChatRequest):
    """Анализирует текст и возвращает найденные PII с подсветкой."""
    masking_result = masking_service.mask(request.message)

    pipeline = masking_service.pipeline
    entities = pipeline.detect_all(request.message)

    highlighted_html = _build_highlighted_html(request.message, entities)

    return {
        "original": request.message,
        "masked": masking_result.masked_text,
        "mapping": masking_result.mapping,
        "highlighted_html": highlighted_html,
        "entities": [
            {
                "type": e.entity_type,
                "value": e.value,
                "start": e.start,
                "end": e.end,
                "confidence": e.confidence,
                "validated": e.validated,
            }
            for e in entities
        ],
        "stats": masking_result.stats,
    }


def _build_highlighted_html(text: str, entities: list) -> str:
    if not entities:
        return text

    COLORS = {
        "PERSON": "#ff6b6b", "PHONE": "#ffa94d", "EMAIL": "#69db7c",
        "PASSPORT": "#748ffc", "SNILS": "#da77f2", "INN": "#f06595",
        "CARD": "#4ecdc4", "ACCOUNT": "#45b7d1", "DATE": "#ffd93d",
        "ADDRESS": "#95e1d3",
    }

    sorted_entities = sorted(entities, key=lambda e: e.start)
    result = []
    last_end = 0

    for entity in sorted_entities:
        if entity.start > last_end:
            result.append(_escape_html(text[last_end:entity.start]))

        color = COLORS.get(entity.entity_type, "#ff6b6b")
        escaped_value = _escape_html(text[entity.start:entity.end])
        result.append(
            f'<span style="background:{color}33;'
            f'border-bottom:2px solid {color};padding:1px 3px;border-radius:3px"'
            f' title="{entity.entity_type} ({entity.confidence})">'
            f'{escaped_value}</span>'
        )
        last_end = entity.end

    if last_end < len(text):
        result.append(_escape_html(text[last_end:]))

    return "".join(result)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
@router.post("/table")
async def mask_table(file: UploadFile = File(...)):
    from services.tabular_masker import TabularMasker

    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        csv_text = content.decode("cp1251")  # Windows кириллица

    masker = TabularMasker(use_ner=config.USE_NER)
    masked_csv, mapping = masker.mask_csv(csv_text)

    return {
        "masked_csv": masked_csv,
        "mapping": mapping,
        "filename": file.filename,
        "stats": {
            "total_replacements": len(mapping),
        },
    }


# ── /audit ─────────────────────────────────────────────────

@router.get("/audit/stats")
async def audit_stats():
    return audit.get_stats()


@router.get("/sessions")
async def list_sessions():
    return session_store.list_sessions()


@router.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionInfo(
        session_id=session.session_id,
        mapping=session.mapping,
        request_count=session.request_count,
        age_seconds=round(session.age_seconds, 1),
    )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    session_store.delete(session_id)
    return {"status": "deleted", "session_id": session_id}


# ── /history ───────────────────────────────────────────────

@router.get("/history/{session_id}")
async def get_history(session_id: str):
    """Возвращает историю чата (оригинальные сообщения)."""
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "messages": session.history.get_messages_for_client(),
        "total_messages": len(session.history),
    }

