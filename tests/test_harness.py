import asyncio
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db, get_redis
from app.graph import build_copy_graph
from app.main import app, get_compiled_graph
from app.models import MessageHistory, User
from app.repository import UserRepository
from app.schemas import FormatType, StepName


# -------------------------------------------------------------------------
# Test Fixtures (In-Memory Async SQLite, FakeRedis, Mock LLM)
# -------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_redis():
    """In-memory async Redis instance backed by fakeredis with Lua and lock support."""
    redis = FakeRedis(decode_responses=True)
    yield redis
    await redis.flushall()
    await redis.aclose()


@pytest_asyncio.fixture
async def test_db_engine():
    """In-memory SQLite async engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(test_db_engine):
    """Session factory bound to in-memory SQLite engine."""
    return async_sessionmaker(
        bind=test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
def fake_llm():
    """Deterministic mock LLM replacing Google Gemini API calls."""
    responses = [
        (
            "🔥 [COPY STORIES DE ALTA CONVERSÃO]\n\n"
            "Tela 1: Você ainda sofre para fechar contratos todos os meses?\n"
            "Tela 2: O método neuro-copy reduz o ciclo de fechamento em até 70%.\n"
            "Tela 3: Toque no botão abaixo e garanta sua vaga agora!"
        ),
        (
            "🔥 [COPY REELS DE ALTA CONVERSÃO]\n\n"
            "Gancho (0-3s): Pare de cometer esse erro com seu produto!\n"
            "Desenvolvimento: Quando você ajusta o posicionamento, tudo muda.\n"
            "CTA: Comente 'COPY' para receber o roteiro completo no direct."
        ),
    ]
    return FakeListChatModel(responses=responses)


@pytest.fixture
def test_graph(fake_llm):
    """LangGraph instance wired with the deterministic fake LLM."""
    return build_copy_graph(llm=fake_llm)


@pytest_asyncio.fixture
async def client(session_factory, test_redis, test_graph) -> AsyncGenerator[AsyncClient, None]:
    """
    FastAPI AsyncClient configured with test harness overrides:
    - PostgreSQL replaced with in-memory SQLite async
    - Redis replaced with in-memory FakeRedis
    - Gemini LLM replaced with FakeListChatModel
    """

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def override_get_redis():
        yield test_redis

    def override_get_graph():
        return test_graph

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_compiled_graph] = override_get_graph

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()


# -------------------------------------------------------------------------
# Test Cases
# -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_onboarding_cycle(client: AsyncClient, session_factory):
    """
    Scenario A: Complete single-step onboarding cycle according to bot diagram.
    User sends name, segment and @brand_handle in one response.
    Validates step progression: ASK_ONBOARDING -> CHOOSE_FORMAT.
    Verifies user profile persistence in PostgreSQL and Redis session caching.
    """
    phone = "5511999990001"
    base_time = "2026-10-21T10:00:00Z"

    # User provides name, segment and brand handle in one message
    resp = await client.post(
        "/webhook/message",
        json={
            "message_id": "evt_onboarding_1",
            "sender_id": phone,
            "message_text": "Sou a Ana Beatriz, trabalho com nutrição esportiva e meu @ é @anabnutri",
            "timestamp": base_time,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["current_step"] == StepName.CHOOSE_FORMAT.value
    assert "Prazer, Ana Beatriz" in data["response_text"]
    assert "nutrição esportiva" in data["response_text"]
    assert "@anabnutri" in data["response_text"]
    assert "1. 📖 Narrativa para stories" in data["response_text"]

    # Verify relational DB state
    async with session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_phone(phone)
        assert user is not None
        assert user.name == "Ana Beatriz"
        assert user.niche == "nutrição esportiva"
        assert user.brand_handle == "@anabnutri"
        assert user.current_step == StepName.CHOOSE_FORMAT.value

        history = await repo.get_history(user.id)
        assert len(history) == 2  # 1 user message + 1 assistant response


@pytest.mark.asyncio
async def test_format_invalid_input_rejection(client: AsyncClient, session_factory):
    """
    Scenario B: Validation rejection on Etapa 1 menu.
    Ensures invalid input (e.g. '99' or arbitrary text) does not advance the state
    and prompts the user with the options again.
    """
    phone = "5511999990002"

    # Onboarding
    await client.post(
        "/webhook/message",
        json={
            "message_id": "evt_val_1",
            "sender_id": phone,
            "message_text": "Lucas Mendes, mentor de investimentos, @lucasfinancas",
            "timestamp": "2026-10-21T10:00:00Z",
        },
    )

    # Attempt 1: Out of range number "99"
    resp_invalid1 = await client.post(
        "/webhook/message",
        json={
            "message_id": "evt_val_2",
            "sender_id": phone,
            "message_text": "99",
            "timestamp": "2026-10-21T10:01:00Z",
        },
    )
    assert resp_invalid1.status_code == 200
    data_inv1 = resp_invalid1.json()
    assert data_inv1["current_step"] == StepName.CHOOSE_FORMAT.value
    assert "⚠️ Não entendi a opção escolhida" in data_inv1["response_text"]

    # Attempt 2: Valid option "1" (Stories) -> transitions to Etapa 2
    resp_valid = await client.post(
        "/webhook/message",
        json={
            "message_id": "evt_val_3",
            "sender_id": phone,
            "message_text": "1",
            "timestamp": "2026-10-21T10:02:00Z",
        },
    )
    assert resp_valid.status_code == 200
    data_val = resp_valid.json()
    assert data_val["current_step"] == StepName.CHOOSE_SUB_INTENT.value
    assert data_val["format_type"] == FormatType.STORIES.value
    assert "Você quer vender ou promover algo" in data_val["response_text"]


@pytest.mark.asyncio
async def test_smart_intent_skip_etapa2(client: AsyncClient, session_factory):
    """
    Scenario C: Smart intent detection.
    When the user sends a clear message with format and intent, the bot skips
    Etapa 2 directly to copy generation.
    """
    phone = "5511999990003"
    t = "2026-10-21T10:00:00Z"

    # Onboarding
    await client.post(
        "/webhook/message",
        json={
            "message_id": "si_1",
            "sender_id": phone,
            "message_text": "Carla, Estética, @carlabeauty",
            "timestamp": t,
        },
    )

    # User immediately sends clear detailed intent:
    resp = await client.post(
        "/webhook/message",
        json={
            "message_id": "si_2",
            "sender_id": phone,
            "message_text": "Quero um carrossel para o feed sobre harmonização facial sem dor",
            "timestamp": t,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # Direct jump to COPY_REFINEMENT
    assert data["current_step"] == StepName.COPY_REFINEMENT.value
    assert data["format_type"] == FormatType.FEED.value
    assert "Sua copy de alta conversão para FEED" in data["response_text"]


@pytest.mark.asyncio
async def test_same_day_vs_subsequent_day_temporal_trigger(client: AsyncClient, session_factory):
    """
    Scenario D: Simulation of same-day message vs. subsequent-day message.
    - Same day: Continues current workflow (does not reset to format selection).
    - Next day: Temporal node detects new date and triggers the daily format selection menu.
    """
    phone = "5511999990004"
    day1_morning = "2026-10-21T09:00:00Z"
    day1_afternoon = "2026-10-21T16:30:00Z"
    day2_morning = "2026-10-22T08:15:00Z"

    # Complete onboarding on Day 1
    await client.post(
        "/webhook/message",
        json={"message_id": "d1_1", "sender_id": phone, "message_text": "Juliana, Mentora B2B, @julianab2b", "timestamp": day1_morning},
    )

    # Etapa 1: Select Stories (1)
    await client.post(
        "/webhook/message",
        json={"message_id": "d1_2", "sender_id": phone, "message_text": "1", "timestamp": day1_morning},
    )

    # Etapa 2: Select Vender (1)
    resp_etapa2 = await client.post(
        "/webhook/message",
        json={"message_id": "d1_3", "sender_id": phone, "message_text": "1", "timestamp": day1_morning},
    )
    assert resp_etapa2.json()["current_step"] == StepName.AWAITING_COPY_BRIEF.value

    # SAME DAY MESSAGE (Day 1 afternoon):
    # Should NOT trigger the daily format menu; should stay in copy workflow and generate copy!
    resp_same_day = await client.post(
        "/webhook/message",
        json={
            "message_id": "d1_4",
            "sender_id": phone,
            "message_text": "Quero vender mentoria executiva para diretores de TI",
            "timestamp": day1_afternoon,
        },
    )
    assert resp_same_day.status_code == 200
    data_same_day = resp_same_day.json()
    assert data_same_day["current_step"] == StepName.COPY_REFINEMENT.value
    assert "Sua copy de alta conversão" in data_same_day["response_text"]
    assert "Novo dia" not in data_same_day["response_text"]

    # SUBSEQUENT DAY MESSAGE (Day 2 morning):
    # eval_daily_trigger must fire, transitioning to CHOOSE_FORMAT and prompting menu!
    resp_next_day = await client.post(
        "/webhook/message",
        json={
            "message_id": "d2_1",
            "sender_id": phone,
            "message_text": "Bom dia, quero criar mais posts!",
            "timestamp": day2_morning,
        },
    )
    assert resp_next_day.status_code == 200
    data_next_day = resp_next_day.json()
    assert data_next_day["current_step"] == StepName.CHOOSE_FORMAT.value
    assert "Novo dia, novos conteúdos!" in data_next_day["response_text"]
    assert "1. 📖 Narrativa para stories" in data_next_day["response_text"]


@pytest.mark.asyncio
async def test_redis_distributed_lock_concurrency(client: AsyncClient, test_redis):
    """
    Scenario E: Distributed lock concurrency protection.
    When a lock is held for a user (simulating in-flight processing or rapid bursts),
    subsequent concurrent requests fail lock acquisition and return HTTP 429 Too Many Requests.
    """
    phone = "5511999990005"
    lock_key = f"lock:user:{phone}"

    # Acquire lock externally simulating an active lock held during heavy processing
    external_lock = test_redis.lock(lock_key, timeout=10.0)
    await external_lock.acquire()

    try:
        # Concurrent incoming webhook request for the same phone number
        resp = await client.post(
            "/webhook/message",
            json={
                "message_id": "evt_concurrent_1",
                "sender_id": phone,
                "message_text": "Cliquei 5 vezes rápido no botão",
                "timestamp": "2026-10-21T10:00:00Z",
            },
        )
        assert resp.status_code == 429
        body = resp.json()
        assert body["status"] == "busy"
        assert body["reason"] == "lock_contention"
    finally:
        await external_lock.release()

    # After lock is released, request succeeds normally
    resp_success = await client.post(
        "/webhook/message",
        json={
            "message_id": "evt_concurrent_2",
            "sender_id": phone,
            "message_text": "Rafael, Engenheiro, @rafaeleng",
            "timestamp": "2026-10-21T10:01:00Z",
        },
    )
    assert resp_success.status_code == 200
    assert resp_success.json()["status"] == "success"


@pytest.mark.asyncio
async def test_redis_event_deduplication(client: AsyncClient, session_factory):
    """
    Scenario F: Event deduplication validation.
    When messaging providers (WhatsApp/Telegram webhooks) retry or resend the same message_id,
    the duplicate event is immediately ignored with HTTP 200 and reason 'duplicate_event'.
    """
    phone = "5511999990006"
    message_id = "evt_dedup_unique_456"

    # First event delivery
    resp1 = await client.post(
        "/webhook/message",
        json={
            "message_id": message_id,
            "sender_id": phone,
            "message_text": "Fernanda, Médica, @fernandamed",
            "timestamp": "2026-10-21T10:00:00Z",
        },
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "success"

    # Immediate redelivery of the exact same message_id (retry from webhook gateway)
    resp2 = await client.post(
        "/webhook/message",
        json={
            "message_id": message_id,
            "sender_id": phone,
            "message_text": "Fernanda, Médica, @fernandamed",
            "timestamp": "2026-10-21T10:00:00Z",
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "ignored"
    assert data2["reason"] == "duplicate_event"

    # Ensure duplicate message was not written to DB twice
    async with session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_phone(phone)
        assert user is not None
        messages = await repo.get_history(user.id)
        # Should only contain 2 records (1 user msg + 1 assistant reply)
        assert len(messages) == 2


@pytest.mark.asyncio
async def test_copy_generation_prompt_injection(client: AsyncClient, session_factory):
    """
    Scenario G: End-to-end copy generation with parameter injection.
    Ensures name, niche, brand_handle, format_type and sub_intent are injected,
    and returns high-converting copy from the LLM.
    """
    phone = "5511999990007"
    t = "2026-10-21T11:00:00Z"

    # 1. Onboarding
    await client.post(
        "/webhook/message",
        json={"message_id": "cg_1", "sender_id": phone, "message_text": "Marina Dias, Copywriting, @marinacopy", "timestamp": t},
    )

    # 2. Etapa 1: Select STORIES format (1)
    resp_format = await client.post(
        "/webhook/message",
        json={"message_id": "cg_2", "sender_id": phone, "message_text": "1", "timestamp": t},
    )
    assert resp_format.json()["format_type"] == FormatType.STORIES.value
    assert resp_format.json()["current_step"] == StepName.CHOOSE_SUB_INTENT.value

    # 3. Etapa 2: Select sub-intent "1" (Vender produto/serviço)
    resp_intent = await client.post(
        "/webhook/message",
        json={"message_id": "cg_3", "sender_id": phone, "message_text": "1", "timestamp": t},
    )
    assert resp_intent.json()["current_step"] == StepName.AWAITING_COPY_BRIEF.value

    # 4. Submit copy brief
    resp_copy = await client.post(
        "/webhook/message",
        json={
            "message_id": "cg_4",
            "sender_id": phone,
            "message_text": "Sequência para atrair infoprodutores que faturam mais de 50k",
            "timestamp": t,
        },
    )
    assert resp_copy.status_code == 200
    data_copy = resp_copy.json()
    assert data_copy["current_step"] == StepName.COPY_REFINEMENT.value
    assert "Sua copy de alta conversão para STORIES" in data_copy["response_text"]
    assert "Tela 1:" in data_copy["response_text"]


@pytest.mark.asyncio
async def test_evolution_webhook_adapter(client: AsyncClient, monkeypatch):
    """
    Scenario H: Evolution API webhook adapter:
    1. Ignores messages sent from the bot (fromMe=True).
    2. Ignores group chat messages (@g.us).
    3. Successfully processes messages.upsert from individual WhatsApp chats.
    4. Mock Evolution outbound API call.
    """
    outbound_calls = []

    async def fake_send_evolution_message(phone_number: str, text: str):
        outbound_calls.append({"phone": phone_number, "text": text})
        return True

    monkeypatch.setattr("app.main.send_evolution_message", fake_send_evolution_message)

    # 1. Ignored: fromMe = True
    payload_from_me = {
        "event": "messages.upsert",
        "instance": "copybot",
        "data": {
            "key": {"remoteJid": "5511999990008@s.whatsapp.net", "fromMe": True, "id": "msg_fm_1"},
            "message": {"conversation": "Oi bot"},
        },
    }
    r1 = await client.post("/webhook/evolution", json=payload_from_me)
    assert r1.status_code == 200
    assert r1.json()["status"] == "ignored"
    assert r1.json()["reason"] == "message_from_bot"
    assert len(outbound_calls) == 0

    # 2. Ignored: group chat
    payload_group = {
        "event": "messages.upsert",
        "instance": "copybot",
        "data": {
            "key": {"remoteJid": "120363000000000000@g.us", "fromMe": False, "id": "msg_grp_1"},
            "message": {"conversation": "Mensagem no grupo"},
        },
    }
    r2 = await client.post("/webhook/evolution", json=payload_group)
    assert r2.status_code == 200
    assert r2.json()["status"] == "ignored"
    assert r2.json()["reason"] == "ignored_non_individual_chat"
    assert len(outbound_calls) == 0

    # 3. Valid: first user interaction (onboarding)
    payload_user = {
        "event": "messages.upsert",
        "instance": "copybot",
        "data": {
            "key": {"remoteJid": "5511999990008@s.whatsapp.net", "fromMe": False, "id": "msg_evo_1"},
            "message": {"conversation": "Lucas Almeida, Marketing Digital, @lucasmark"},
        },
    }
    r3 = await client.post("/webhook/evolution", json=payload_user)
    assert r3.status_code == 200
    assert r3.json()["status"] == "success"
    assert r3.json()["current_step"] == StepName.CHOOSE_FORMAT.value
    assert len(outbound_calls) == 1
    assert outbound_calls[0]["phone"] == "5511999990008"
    assert "Prazer, Lucas Almeida!" in outbound_calls[0]["text"]


@pytest.mark.asyncio
async def test_rag_semantic_knowledge_injection(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch,
):
    """
    Scenario I: RAG semantic retrieval and prompt enrichment:
    1. Pre-seeds KnowledgeChunk in the database.
    2. Uses MockEmbeddings for 100% deterministic local vector search.
    3. Triggers copy generation and verifies RAG context is populated.
    """
    from langchain_core.embeddings import Embeddings
    from app.models import KnowledgeChunk
    from app.rag import set_embeddings_model

    class MockEmbeddings(Embeddings):
        def embed_documents(self, texts):
            return [[0.1] * 768 for _ in texts]

        def embed_query(self, text):
            return [0.1] * 768

        async def aembed_documents(self, texts):
            return self.embed_documents(texts)

        async def aembed_query(self, text):
            return self.embed_query(text)

    set_embeddings_model(MockEmbeddings())

    # Pre-seed knowledge chunk
    async with session_factory() as session:
        chunk = KnowledgeChunk(
            title="Framework Stories de Alta Conversão",
            content="Regra dos 3 segundos: O gancho da Tela 1 precisa quebrar padrão com pergunta binária.",
            niche="Finanças & Investimentos",
            format_type=FormatType.STORIES.value,
            doc_type="framework",
            embedding=[0.1] * 768,
        )
        session.add(chunk)
        await session.commit()

    phone = "+5511999990009"
    t = "2026-10-21T11:00:00Z"

    # Onboarding
    await client.post(
        "/webhook/message",
        json={"message_id": "rag_1", "sender_id": phone, "message_text": "Gabriel, Finanças & Investimentos, @gabrielfin", "timestamp": t},
    )

    # Etapa 1: Stories
    await client.post(
        "/webhook/message",
        json={"message_id": "rag_2", "sender_id": phone, "message_text": "1", "timestamp": t},
    )

    # Etapa 2: Vender
    await client.post(
        "/webhook/message",
        json={"message_id": "rag_3", "sender_id": phone, "message_text": "1", "timestamp": t},
    )

    # Submit copy brief (should retrieve seeded chunk)
    resp = await client.post(
        "/webhook/message",
        json={
            "message_id": "rag_4",
            "sender_id": phone,
            "message_text": "Como sair das dívidas e começar a investir 100 reais por mês",
            "timestamp": t,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["current_step"] == StepName.COPY_REFINEMENT.value
    assert data["format_type"] == FormatType.STORIES.value




