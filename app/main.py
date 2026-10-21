import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import (
    DistributedLock,
    EventDeduplicator,
    LockAcquisitionError,
    SessionCache,
    get_db,
    get_redis,
    init_db,
    redis_client,
)
from app.graph import build_copy_graph
from app.rag import format_rag_context, retrieve_relevant_knowledge
from app.repository import UserRepository
from app.schemas import AgentState, WebhookEvent, WebhookResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

# Default singleton graph (uses Gemini in production)
_compiled_graph = None


def get_compiled_graph():
    """Dependency provider for compiled LangGraph state machine."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_copy_graph()
    return _compiled_graph


def set_compiled_graph(graph):
    """Allows test harness to inject a graph with mock LLM."""
    global _compiled_graph
    _compiled_graph = graph


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager initializing connections and schemas."""
    logger.info("Initializing relational database tables...")
    await init_db()
    logger.info("Database and Redis clients ready.")
    yield
    # Shutdown logic
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        logger.info("Redis client closed.")


app = FastAPI(
    title="High-Conversion Copywriting Bot API",
    version="1.0.0",
    description="Deterministic LangGraph + Redis Concurrency + PostgreSQL Test Harness for WhatsApp/Telegram",
    lifespan=lifespan,
)


@app.get("/health", tags=["Monitoring"])
async def health_check():
    """Health check endpoint confirming API status."""
    return {"status": "healthy", "env": settings.APP_ENV}


@app.post(
    "/webhook/message",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    tags=["Messaging Webhook"],
)
async def process_webhook_message(
    event: WebhookEvent,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    graph=Depends(get_compiled_graph),
):
    """
    Process incoming messaging events with guaranteed idempotency and concurrency isolation:
    1. Deduplicates events by message_id in Redis (5-min TTL).
    2. Enforces Distributed Lock by sender_id.
    3. Runs LangGraph state machine over PostgreSQL relational state.
    4. Persists transitions and message history to PostgreSQL and warms session cache.
    5. Releases lock and outputs standardized response.
    """
    dedup = EventDeduplicator(redis, ttl_seconds=settings.REDIS_DEDUP_TTL_SECONDS)
    session_cache = SessionCache(redis, ttl_seconds=settings.REDIS_SESSION_CACHE_TTL_SECONDS)
    repo = UserRepository(db)

    # 1. Event Deduplication
    is_dup = await dedup.is_duplicate(event.message_id)
    if is_dup:
        logger.warning("Duplicate event detected: %s. Skipping with HTTP 200.", event.message_id)
        return WebhookResponse(
            status="ignored",
            reason="duplicate_event",
            response_text=None,
        )

    # 2. Acquire Distributed Lock based on sender phone number
    try:
        async with DistributedLock(
            redis=redis,
            phone_number=event.sender_id,
            timeout=settings.REDIS_LOCK_TIMEOUT_SECONDS,
            blocking_timeout=settings.REDIS_LOCK_BLOCKING_TIMEOUT_SECONDS,
        ):
            # 3. Retrieve or initialize user record
            user, is_new = await repo.get_or_create(
                phone_number=event.sender_id,
                current_time=event.timestamp,
            )

            # Check cache or sync current_step and format_type
            cached_step = await session_cache.get_cached_step(event.sender_id)
            effective_step = cached_step if cached_step else user.current_step

            cached_format = await session_cache.get_cached_format(event.sender_id)
            effective_format = cached_format if cached_format else user.format_type

            # Check if this interaction needs RAG context (Copy Brief submission, Refinement, or Smart Intent)
            rag_context = ""
            needs_rag = effective_step in ("AWAITING_COPY_BRIEF", "GENERATE_COPY", "COPY_REFINEMENT")
            if not needs_rag and effective_step in ("CHOOSE_FORMAT", "CHOOSE_SUB_INTENT"):
                if len(event.message_text.strip().split()) >= 4:
                    needs_rag = True

            if needs_rag:
                chunks = await retrieve_relevant_knowledge(
                    db=db,
                    query=event.message_text,
                    niche=user.niche,
                    format_type=effective_format,
                    top_k=3,
                )
                if chunks:
                    rag_context = format_rag_context(chunks)

            # Assemble AgentState for LangGraph
            state: AgentState = {
                "user_id": user.id,
                "phone_number": user.phone_number,
                "name": user.name,
                "profession": user.profession,
                "niche": user.niche,
                "brand_handle": user.brand_handle,
                "sub_intent": user.sub_intent,
                "current_step": effective_step,
                "format_type": effective_format,
                "last_interaction_at": user.last_interaction_at,
                "message_timestamp": event.timestamp,
                "input_text": event.message_text,
                "response_text": None,
                "messages": [HumanMessage(content=event.message_text)],
                "error": None,
                "daily_trigger_fired": False,
                "rag_context": rag_context,
            }

            # 4. Invoke LangGraph state machine
            output_state: AgentState = await graph.ainvoke(state)

            new_step = output_state.get("current_step", effective_step)
            response_text = output_state.get("response_text")
            new_format = output_state.get("format_type", effective_format)
            new_brand_handle = output_state.get("brand_handle", user.brand_handle)
            new_sub_intent = output_state.get("sub_intent", user.sub_intent)

            # 5. Persist updated user state and message logs to PostgreSQL
            await repo.update_user(
                user,
                name=output_state.get("name", user.name),
                profession=output_state.get("profession", user.profession),
                niche=output_state.get("niche", user.niche),
                brand_handle=new_brand_handle,
                sub_intent=new_sub_intent,
                format_type=new_format,
                current_step=new_step,
                last_interaction_at=event.timestamp,
            )

            # Record human message
            await repo.record_message(
                user_id=user.id,
                role="user",
                content=event.message_text,
                format_type=new_format,
                created_at=event.timestamp,
            )

            # Record assistant message
            if response_text:
                await repo.record_message(
                    user_id=user.id,
                    role="assistant",
                    content=response_text,
                    format_type=new_format,
                    created_at=event.timestamp,
                )

            await db.commit()

            # Warm ephemeral session cache in Redis
            await session_cache.set_cached_step(event.sender_id, new_step)
            await session_cache.set_cached_format(event.sender_id, new_format)

            return WebhookResponse(
                status="success",
                response_text=response_text,
                current_step=new_step,
                user_id=user.id,
                format_type=new_format,
                sub_intent=new_sub_intent,
            )

    except LockAcquisitionError as e:
        logger.warning("Lock contention for sender %s: %s", event.sender_id, e)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "status": "busy",
                "reason": "lock_contention",
                "message": "Outra mensagem sua já está em processamento. Aguarde alguns instantes.",
            },
        )


async def send_evolution_message(phone_number: str, text: str) -> bool:
    """Sends a text message back to WhatsApp via Evolution API."""
    url = f"{settings.EVOLUTION_API_URL}/message/sendText/{settings.EVOLUTION_INSTANCE_NAME}"
    headers = {
        "apikey": settings.EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }
    clean_number = "".join(filter(str.isdigit, phone_number))
    payload = {
        "number": clean_number,
        "text": text,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code not in (200, 201):
                logger.error("Evolution sendText error [%s]: %s", resp.status_code, resp.text)
                return False
            logger.info("Message sent to WhatsApp user %s via Evolution API", clean_number)
            return True
    except Exception as exc:
        logger.error("Failed to communicate with Evolution API: %s", exc)
        return False


@app.post(
    "/webhook/evolution",
    status_code=status.HTTP_200_OK,
    tags=["Evolution API Webhook"],
)
async def process_evolution_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    graph=Depends(get_compiled_graph),
):
    """
    Adapter endpoint for Evolution API webhooks (MESSAGES_UPSERT).
    Extracts sender, message text, and message_id, executes the LangGraph
    state machine and automatically sends the response back to WhatsApp.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "invalid_json"}

    event_type = payload.get("event")
    if event_type not in ("messages.upsert", "MESSAGES_UPSERT"):
        return {"status": "ignored", "reason": f"unhandled_event_{event_type}"}

    data = payload.get("data", {})
    key = data.get("key", {})

    # 1. Ignore if sent by the bot itself
    if key.get("fromMe", False):
        return {"status": "ignored", "reason": "message_from_bot"}

    remote_jid = key.get("remoteJid", "")
    # 2. Ignore group chats
    if not remote_jid or not remote_jid.endswith("@s.whatsapp.net"):
        return {"status": "ignored", "reason": "ignored_non_individual_chat"}

    sender_id = remote_jid.replace("@s.whatsapp.net", "").split(":")[0]

    # Extract text
    msg_dict = data.get("message", {}) or {}
    message_text = (
        msg_dict.get("conversation")
        or (msg_dict.get("extendedTextMessage", {}) or {}).get("text")
        or ""
    ).strip()

    if not message_text:
        return {"status": "ignored", "reason": "empty_or_media_message"}

    message_id = key.get("id") or str(uuid.uuid4())
    event_timestamp = datetime.now(timezone.utc)

    internal_event = WebhookEvent(
        message_id=message_id,
        sender_id=sender_id,
        message_text=message_text,
        timestamp=event_timestamp,
    )

    response = await process_webhook_message(
        event=internal_event,
        db=db,
        redis=redis,
        graph=graph,
    )

    if isinstance(response, WebhookResponse):
        if response.status == "success" and response.response_text:
            await send_evolution_message(sender_id, response.response_text)
        return response

    if isinstance(response, JSONResponse) and response.status_code == 429:
        await send_evolution_message(
            sender_id,
            "⚠️ Outra mensagem sua já está em processamento. Aguarde alguns instantes.",
        )

    return response
