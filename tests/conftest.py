import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.graph import build_copy_graph


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
