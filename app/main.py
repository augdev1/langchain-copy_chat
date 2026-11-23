import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import AsyncGenerator, List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import (
    DistributedLock,
    EventDeduplicator,
    LockAcquisitionError,
    MessageDebouncer,
    SessionCache,
    get_db,
    get_redis,
    init_db,
    redis_client,
)
from app.graph import build_copy_graph
from app.models import AuditLog
from app.rag import format_rag_context, retrieve_relevant_knowledge
from app.repository import AuditRepository, UserRepository
from app.schemas import (
    AgentState,
    AuditEventType,
    AuditLogResponse,
    StepName,
    WebhookEvent,
    WebhookResponse,
)
from app.security import verify_admin_key, verify_webhook_secret

# Structured rotating file logger for audit trail
os.makedirs("logs", exist_ok=True)
audit_handler = RotatingFileHandler(
    "logs/audit.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
audit_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] [AUDIT] %(message)s")
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.addHandler(audit_handler)

settings = get_settings()

# Default singleton graph
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
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        logger.info("Redis client closed.")


app = FastAPI(
    title="High-Conversion Copywriting Bot API",
    version="1.0.0",
    description="Deterministic LangGraph + Redis Concurrency + Defensive Guardrails + PostgreSQL for WhatsApp",
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
    _auth: bool = Depends(verify_webhook_secret),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    graph=Depends(get_compiled_graph),
):
    """
    Process incoming messaging events with guaranteed idempotency, security and concurrency isolation:
    1. Cryptographic webhook verification (constant-time).
    2. Deduplicates events by message_id in Redis (5-min TTL).
    3. Enforces Distributed Lock by company_id and sender phone number via Lua script.
    4. Evaluates NeMo Guardrails (<1ms) and Human-in-the-Loop gates.
    5. Runs LangGraph state machine over PostgreSQL relational state.
    6. Persists transitions and immutable audit events to PostgreSQL.
    7. Releases lock and outputs standardized response.
    """
    start_time = time.perf_counter()
    company_id = event.company_id or "default"
    dedup = EventDeduplicator(redis, ttl_seconds=settings.REDIS_DEDUP_TTL_SECONDS)
    session_cache = SessionCache(redis, ttl_seconds=settings.REDIS_SESSION_CACHE_TTL_SECONDS)
    repo = UserRepository(db)
    audit_repo = AuditRepository(db)

    # 1. Event Deduplication
    is_dup = await dedup.is_duplicate(event.message_id)
    if is_dup:
        logger.warning("Duplicate event detected: %s. Skipping with HTTP 200.", event.message_id)
        await audit_repo.log_event(
            event_type=AuditEventType.DEDUP_BLOCKED.value,
            phone_number=event.sender_id,
            company_id=company_id,
            status="IGNORED",
            payload={"message_id": event.message_id},
        )
        await db.commit()
        return WebhookResponse(
            status="ignored",
            reason="duplicate_event",
            response_text=None,
            company_id=company_id,
        )

    # 2. Acquire Distributed Lock based on tenant and sender phone number
    try:
        async with DistributedLock(
            redis=redis,
            phone_number=event.sender_id,
            company_id=company_id,
            timeout=settings.REDIS_LOCK_TIMEOUT_SECONDS,
            blocking_timeout=settings.REDIS_LOCK_BLOCKING_TIMEOUT_SECONDS,
        ):
            # 3. Retrieve or initialize user record
            user, is_new = await repo.get_or_create(
                phone_number=event.sender_id,
                company_id=company_id,
                current_time=event.timestamp,
            )

            # Check cache or sync current_step and format_type
            cached_step = await session_cache.get_cached_step(event.sender_id, company_id=company_id)
            effective_step = cached_step if cached_step else user.current_step

            cached_format = await session_cache.get_cached_format(event.sender_id, company_id=company_id)
            effective_format = cached_format if cached_format else user.format_type

            # Check if this interaction needs RAG context
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
                    await audit_repo.log_event(
                        event_type=AuditEventType.RAG_RETRIEVAL.value,
                        phone_number=event.sender_id,
                        company_id=company_id,
                        user_id=user.id,
                        format_type=effective_format,
                        payload={
                            "query": event.message_text,
                            "chunks_count": len(chunks),
                            "chunk_titles": [c.title for c in chunks],
                        },
                    )

            # Assemble AgentState for LangGraph
            state: AgentState = {
                "user_id": user.id,
                "phone_number": user.phone_number,
                "company_id": company_id,
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
                "human_handoff": user.is_human_handoff,
                "pending_action": user.pending_action,
            }

            # 4. Invoke LangGraph state machine (incorporating Security Guardrails and HITL)
            output_state: AgentState = await graph.ainvoke(state)

            new_step = output_state.get("current_step", effective_step)
            response_text = output_state.get("response_text")
            new_format = output_state.get("format_type", effective_format)
            new_brand_handle = output_state.get("brand_handle", user.brand_handle)
            new_sub_intent = output_state.get("sub_intent", user.sub_intent)
            is_human_handoff = output_state.get("human_handoff", False)
            pending_action = output_state.get("pending_action")
            error_code = output_state.get("error")
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            # 5. Security & HITL Event Determination
            if error_code == "GUARDRAILS_BLOCKED_INPUT":
                audit_type = AuditEventType.GUARDRAILS_BLOCKED_INPUT.value
                resp_status = "blocked"
            elif is_human_handoff and not user.is_human_handoff:
                audit_type = AuditEventType.HUMAN_HANDOFF_TRIGGERED.value
                resp_status = "success"
            elif new_step == StepName.AWAITING_CONFIRMATION.value:
                audit_type = AuditEventType.CRITICAL_ACTION_PENDING.value
                resp_status = "success"
            elif effective_step == StepName.AWAITING_CONFIRMATION.value and new_step == StepName.ASK_ONBOARDING.value:
                audit_type = AuditEventType.CRITICAL_ACTION_CONFIRMED.value
                resp_status = "success"
                await repo.reset_user_profile(user, now=event.timestamp)
            elif effective_step == StepName.AWAITING_CONFIRMATION.value and "cancelada" in (response_text or "").lower():
                audit_type = AuditEventType.CRITICAL_ACTION_CANCELLED.value
                resp_status = "success"
            elif effective_step == "ASK_ONBOARDING" and new_step == "CHOOSE_FORMAT":
                audit_type = AuditEventType.ONBOARDING_COMPLETED.value
                resp_status = "success"
            elif new_step == "COPY_REFINEMENT":
                audit_type = AuditEventType.COPY_GENERATED.value
                resp_status = "success"
            else:
                audit_type = AuditEventType.STATE_TRANSITION.value
                resp_status = "success"

            # 6. Persist updated user state and message logs to PostgreSQL
            if not (effective_step == StepName.AWAITING_CONFIRMATION.value and new_step == StepName.ASK_ONBOARDING.value):
                await repo.update_user(
                    user,
                    name=output_state.get("name", user.name),
                    profession=output_state.get("profession", user.profession),
                    niche=output_state.get("niche", user.niche),
                    brand_handle=new_brand_handle,
                    sub_intent=new_sub_intent,
                    format_type=new_format,
                    current_step=new_step,
                    is_human_handoff=is_human_handoff,
                    pending_action=pending_action,
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

            # Record audit event
            await audit_repo.log_event(
                event_type=audit_type,
                phone_number=event.sender_id,
                company_id=company_id,
                user_id=user.id,
                step_from=effective_step,
                step_to=new_step,
                format_type=new_format,
                sub_intent=new_sub_intent,
                execution_time_ms=elapsed_ms,
                status="BLOCKED" if resp_status == "blocked" else "SUCCESS",
                payload={
                    "input_text": event.message_text,
                    "response_sample": response_text[:120] if response_text else None,
                    "name": output_state.get("name"),
                    "niche": output_state.get("niche"),
                    "brand_handle": new_brand_handle,
                    "error": error_code,
                    "human_handoff": is_human_handoff,
                    "pending_action": pending_action,
                },
            )

            await db.commit()

            # Warm ephemeral session cache in Redis
            await session_cache.set_cached_step(event.sender_id, new_step, company_id=company_id)
            await session_cache.set_cached_format(event.sender_id, new_format, company_id=company_id)

            return WebhookResponse(
                status=resp_status,
                reason="guardrails_blocked" if resp_status == "blocked" else None,
                response_text=response_text,
                current_step=new_step,
                user_id=user.id,
                format_type=new_format,
                sub_intent=new_sub_intent,
                human_handoff=is_human_handoff,
                company_id=company_id,
            )

    except LockAcquisitionError as e:
        logger.warning("Lock contention for sender %s: %s", event.sender_id, e)
        await audit_repo.log_event(
            event_type=AuditEventType.LOCK_CONTENTION.value,
            phone_number=event.sender_id,
            company_id=company_id,
            status="BLOCKED",
            payload={"error": str(e), "message_id": event.message_id},
        )
        await db.commit()
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
    _auth: bool = Depends(verify_webhook_secret),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    graph=Depends(get_compiled_graph),
):
    """
    Adapter endpoint for Evolution API webhooks (MESSAGES_UPSERT).
    Extracts sender, message text, and message_id, applies security filters
    (discards fromMe and group messages), executes the LangGraph state machine,
    and sends the response back to WhatsApp.
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
    # 2. Ignore group chats (@g.us) and non-individual messages
    if not remote_jid or "@g.us" in remote_jid or not remote_jid.endswith("@s.whatsapp.net"):
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

    # 3. Message Debounce check (optional for handling rapid bursts)
    if settings.DEBOUNCE_WAIT_SECONDS > 0:
        debouncer = MessageDebouncer(redis, wait_seconds=settings.DEBOUNCE_WAIT_SECONDS)
        is_leader, aggregated_text = await debouncer.buffer_and_wait(
            phone=sender_id,
            text=message_text,
            company_id="default",
        )
        if not is_leader:
            # Yielded to newer message in burst
            return {"status": "buffered", "reason": "debounced_into_subsequent_chunk"}
        message_text = aggregated_text

    internal_event = WebhookEvent(
        message_id=message_id,
        sender_id=sender_id,
        message_text=message_text,
        timestamp=event_timestamp,
        company_id="default",
    )

    response = await process_webhook_message(
        event=internal_event,
        db=db,
        redis=redis,
        graph=graph,
    )

    if isinstance(response, WebhookResponse):
        if response.status in ("success", "blocked") and response.response_text:
            sent = await send_evolution_message(sender_id, response.response_text)
            audit_repo = AuditRepository(db)
            await audit_repo.log_event(
                event_type=AuditEventType.OUTBOUND_DISPATCH.value,
                phone_number=sender_id,
                company_id="default",
                user_id=response.user_id,
                format_type=response.format_type,
                sub_intent=response.sub_intent,
                status="SUCCESS" if sent else "ERROR",
                payload={"response_length": len(response.response_text), "sent": sent},
            )
            await db.commit()
        return response

    if isinstance(response, JSONResponse) and response.status_code == 429:
        await send_evolution_message(
            sender_id,
            "Outra mensagem sua já está em processamento. Aguarde alguns instantes.",
        )

    return response


@app.get(
    "/audit/logs",
    response_model=List[AuditLogResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_admin_key)],
    tags=["Audit & Compliance"],
)
async def get_audit_logs(
    phone_number: Optional[str] = Query(None, description="Filtrar por número de telefone"),
    company_id: Optional[str] = Query(None, description="Filtrar por tenant"),
    event_type: Optional[str] = Query(None, description="Filtrar por tipo de evento"),
    limit: int = Query(50, ge=1, le=500, description="Quantidade máxima de registros"),
    offset: int = Query(0, ge=0, description="Deslocamento de paginação"),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna logs imutáveis de auditoria com paginação e filtros opcionais.
    Requer autenticação administrativa (X-Admin-Key ou Bearer Token).
    """
    audit_repo = AuditRepository(db)
    logs = await audit_repo.query_logs(
        phone_number=phone_number,
        company_id=company_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return logs


@app.get(
    "/audit/stats",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_admin_key)],
    tags=["Audit & Compliance"],
)
async def get_audit_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna estatísticas consolidadas da trilha de auditoria.
    Requer autenticação administrativa (X-Admin-Key ou Bearer Token).
    """
    total_events_query = select(func.count(AuditLog.id))
    total_res = await db.execute(total_events_query)
    total_events = total_res.scalar() or 0

    by_type_query = (
        select(AuditLog.event_type, func.count(AuditLog.id))
        .group_by(AuditLog.event_type)
    )
    by_type_res = await db.execute(by_type_query)
    by_type = {row[0]: row[1] for row in by_type_res.all()}

    by_status_query = (
        select(AuditLog.status, func.count(AuditLog.id))
        .group_by(AuditLog.status)
    )
    by_status_res = await db.execute(by_status_query)
    by_status = {row[0]: row[1] for row in by_status_res.all()}

    return {
        "total_audit_events": total_events,
        "events_by_type": by_type,
        "events_by_status": by_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
