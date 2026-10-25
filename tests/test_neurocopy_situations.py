import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from fakeredis.aioredis import FakeRedis

from app.database import Base, get_db, get_redis
from app.graph import build_copy_graph, get_master_prompt
from app.main import app, get_compiled_graph
from app.schemas import FormatType, StepName


@pytest.fixture
def master_prompt_content():
    """Verify master system prompt is loaded from knowledge_base/Prompt mãe.md."""
    prompt = get_master_prompt()
    assert "SISTEMA-MESTRE DE NEUROCOPY" in prompt or "Neurocopy" in prompt
    assert len(prompt) > 1000
    return prompt


async def make_test_client(response_text: str):
    """Factory creating an isolated async client with a dedicated FakeListChatModel response."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis = FakeRedis(decode_responses=True)
    llm = FakeListChatModel(responses=[response_text])
    graph = build_copy_graph(llm=llm)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def override_get_redis():
        yield redis

    def override_get_graph():
        return graph

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_compiled_graph] = override_get_graph

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://testserver")

    async def cleanup():
        await client.aclose()
        app.dependency_overrides.clear()
        await redis.flushall()
        await redis.aclose()
        await engine.dispose()

    return client, cleanup


@pytest.mark.asyncio
async def test_situation_1_stories_quase_resultado(master_prompt_content):
    """
    Situação 1: "Quase Resultado" / Frustração Silenciosa (Instagram Stories - Venda)
    Nicho: Personal Trainer de Alta Performance.
    Aplica o conceito do Prompt Mãe: Quebra da crença comum do fitness e mecanismo de sobrecarga.
    """
    copy_response = (
        "🔥 [NARRATIVA DE STORIES — NEUROCOPY]\n\n"
        "Tela 1 (Gancho de Interrupção): A pior sensação não é fracassar... é viver eternamente no 'quase', né?\n"
        "Tela 2 (Sintoma vs Mecanismo): Você treina 6x na semana, corta carboidratos, mas o espelho continua estagnado. O erro não é a sua disciplina.\n"
        "Tela 3 (O Mecanismo Invisível): Seu sistema nervoso está operando em sobrecarga crônica de cortisol, sinalizando ao corpo para reter gordura como mecanismo de sobrevivência.\n"
        "Tela 4 (Reorganização de Critério): Mais treino não conserta uma sinalização bioquímica desregulada. O segredo é precisão de estímulo, não volume cego.\n"
        "Tela 5 (Ação por Compreensão): Se você quer ajustar sua sinalização metabólica e sair do 'quase', responda 'PROTOCOLO' aqui no direct."
    )
    client, cleanup = await make_test_client(copy_response)
    try:
        phone = "5511991110001"
        # Onboarding
        r1 = await client.post(
            "/webhook/message",
            json={"message_id": "s1_1", "sender_id": phone, "message_text": "Rodrigo Silva, Personal Trainer, @rodrigopersonal", "timestamp": "2026-10-25T10:00:00Z"},
        )
        assert r1.status_code == 200

        # Etapa 1: Stories (1)
        r2 = await client.post(
            "/webhook/message",
            json={"message_id": "s1_2", "sender_id": phone, "message_text": "1", "timestamp": "2026-10-25T10:01:00Z"},
        )
        assert r2.json()["format_type"] == FormatType.STORIES.value

        # Etapa 2: Vender (1)
        r3 = await client.post(
            "/webhook/message",
            json={"message_id": "s1_3", "sender_id": phone, "message_text": "1", "timestamp": "2026-10-25T10:02:00Z"},
        )
        assert r3.json()["current_step"] == StepName.AWAITING_COPY_BRIEF.value

        # Briefing com a dor do "Quase Resultado"
        r4 = await client.post(
            "/webhook/message",
            json={
                "message_id": "s1_4",
                "sender_id": phone,
                "message_text": "A pior sensação não é fracassar... é viver no quase resultado, treinando 6x na semana sem ver definição",
                "timestamp": "2026-10-25T10:03:00Z",
            },
        )
        assert r4.status_code == 200
        data = r4.json()
        assert data["status"] == "success"
        assert data["current_step"] == StepName.COPY_REFINEMENT.value
        assert "viver eternamente no 'quase'" in data["response_text"]
        assert "Sua copy de alta conversão para STORIES" in data["response_text"]
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_situation_2_reels_choque_intelectual():
    """
    Situação 2: Choque Intelectual & Desmistificação de Crença Comum (Reels - Viral e Disruptivo)
    Nicho: Finanças & Investimentos.
    Aplica o conceito do Prompt Mãe: Reinterpretação causal e distinção de risco aparente vs real.
    """
    copy_response = (
        "🎬 [ROTEIRO REELS — QUEBRA DE CRENÇA]\n\n"
        "Gancho (0-3s): O investimento mais perigoso do Brasil se disfarça de 'seguro'.\n"
        "Desenvolvimento: Quando você deixa 50 mil reais na poupança ou num CDB de bancão, você não está se protegendo da volatilidade. Você está aceitando uma perda líquida garantida de poder de compra pela inflação real dos alimentos e serviços.\n"
        "Contraste Conceitual: Segurança aparente no presente é risco multiplicado no futuro.\n"
        "CTA: Comente 'CRITÉRIO' para entender a matriz de proteção patrimonial."
    )
    client, cleanup = await make_test_client(copy_response)
    try:
        phone = "5511991110002"
        # Onboarding
        await client.post(
            "/webhook/message",
            json={"message_id": "s2_1", "sender_id": phone, "message_text": "Lucas Mendes, Mentor Financeiro, @lucasfinancas", "timestamp": "2026-10-25T10:00:00Z"},
        )

        # Etapa 1: Reels (2)
        await client.post(
            "/webhook/message",
            json={"message_id": "s2_2", "sender_id": phone, "message_text": "2", "timestamp": "2026-10-25T10:01:00Z"},
        )

        # Etapa 2: Viral e autoridade disruptiva (2)
        await client.post(
            "/webhook/message",
            json={"message_id": "s2_3", "sender_id": phone, "message_text": "2", "timestamp": "2026-10-25T10:02:00Z"},
        )

        # Briefing
        r4 = await client.post(
            "/webhook/message",
            json={
                "message_id": "s2_4",
                "sender_id": phone,
                "message_text": "Por que a poupança e o CDB de bancão estão empobrecendo a classe média com falsa ilusão de segurança",
                "timestamp": "2026-10-25T10:03:00Z",
            },
        )
        assert r4.status_code == 200
        data = r4.json()
        assert "Gancho (0-3s)" in data["response_text"]
        assert "Sua copy de alta conversão para REELS" in data["response_text"]
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_situation_3_feed_mecanismo_invisivel():
    """
    Situação 3: Mecanismo Invisível & Distinção Técnica Sem Clichês (Feed Carrossel)
    Nicho: Dermatologia & Estética Avançada.
    Aplica o conceito do Prompt Mãe: Explicar o mecanismo estrutural em vez de vender por vaidade rasa.
    """
    copy_response = (
        "📰 [CARROSSEL FEED — ANATOMIA DO ENVELHECIMENTO REAL]\n\n"
        "Slide 1 (Capa): Por que preencher rugas isoladas quase sempre deixa o rosto artificial?\n"
        "Slide 2: A maioria trata a ruga como o problema. Mas a ruga é apenas a dobra de um tecido que perdeu sustentação estrutural.\n"
        "Slide 3: O envelhecimento começa na reabsorção óssea e na atrofia dos coxins de gordura profunda. Quando você apenas preenche o vinco superficial, cria volume onde deveria haver ancoragem.\n"
        "Slide 4: O objetivo da dermatologia de precisão não é inflar o rosto, é restaurar os vetores anatômicos de sustentação.\n"
        "Slide 5: Rejuvenescer não é mudar seus traços, é devolver a luz para os pontos certos."
    )
    client, cleanup = await make_test_client(copy_response)
    try:
        phone = "5511991110003"
        await client.post(
            "/webhook/message",
            json={"message_id": "s3_1", "sender_id": phone, "message_text": "Dra. Camila Santos, Dermatologista, @dracamiladermato", "timestamp": "2026-10-25T10:00:00Z"},
        )

        # Etapa 1: Feed (3)
        await client.post(
            "/webhook/message",
            json={"message_id": "s3_2", "sender_id": phone, "message_text": "3", "timestamp": "2026-10-25T10:01:00Z"},
        )

        # Etapa 2: Carrossel (2)
        await client.post(
            "/webhook/message",
            json={"message_id": "s3_3", "sender_id": phone, "message_text": "2", "timestamp": "2026-10-25T10:02:00Z"},
        )

        # Briefing
        r4 = await client.post(
            "/webhook/message",
            json={
                "message_id": "s3_4",
                "sender_id": phone,
                "message_text": "Explicar por que preencher rugas deixa artificial e como o suporte ósseo profundo é o verdadeiro segredo",
                "timestamp": "2026-10-25T10:03:00Z",
            },
        )
        assert r4.status_code == 200
        data = r4.json()
        assert "Slide 1 (Capa)" in data["response_text"]
        assert "Sua copy de alta conversão para FEED" in data["response_text"]
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_situation_4_whatsapp_quebra_objecao():
    """
    Situação 4: Arquitetura de Decisão & Quebra de Objeção Sem Pressão (WhatsApp Lead)
    Nicho: Consultoria B2B.
    Aplica o conceito do Prompt Mãe: Transformar a desculpa de 'falta de tempo' na prova da necessidade da solução.
    """
    copy_response = (
        "💬 [MENSAGEM WHATSAPP — REENQUADRAMENTO DE TEMPO]\n\n"
        "Olá Carlos! Pensando na sua resposta sobre 'não ter tempo agora para a consultoria':\n\n"
        "A falta de tempo na sua rotina não é o motivo para adiar o projeto — ela é o sintoma visível de uma operação onde você centraliza o operacional por falta de processos mapeados.\n\n"
        "Cada mês sem estruturação custa à sua empresa cerca de 25 horas semanais do seu foco estratégico.\n\n"
        "Faz sentido conversarmos 15 minutos na quinta às 10h para eu te mostrar como a implementação da fase 1 exige apenas 2 horas do seu time?"
    )
    client, cleanup = await make_test_client(copy_response)
    try:
        phone = "5511991110004"
        await client.post(
            "/webhook/message",
            json={"message_id": "s4_1", "sender_id": phone, "message_text": "Marcos Vale, Consultor de Processos B2B, @marcosvale.gestao", "timestamp": "2026-10-25T10:00:00Z"},
        )

        # Etapa 1: WhatsApp (4)
        await client.post(
            "/webhook/message",
            json={"message_id": "s4_2", "sender_id": phone, "message_text": "4", "timestamp": "2026-10-25T10:01:00Z"},
        )

        # Etapa 2: Oferta e Fechamento (2)
        await client.post(
            "/webhook/message",
            json={"message_id": "s4_3", "sender_id": phone, "message_text": "2", "timestamp": "2026-10-25T10:02:00Z"},
        )

        # Briefing
        r4 = await client.post(
            "/webhook/message",
            json={
                "message_id": "s4_4",
                "sender_id": phone,
                "message_text": "Lead que diz não ter tempo agora para implementar a consultoria de processos",
                "timestamp": "2026-10-25T10:03:00Z",
            },
        )
        assert r4.status_code == 200
        data = r4.json()
        assert "A falta de tempo na sua rotina não é o motivo para adiar" in data["response_text"]
        assert "Sua copy de alta conversão para WHATSAPP_LEAD" in data["response_text"]
    finally:
        await cleanup()


@pytest.mark.asyncio
async def test_situation_5_smart_intent_territorio_mental():
    """
    Situação 5: Smart Intent Bypass com Reorganização de Critério Mental (Instagram Feed)
    Nicho: Estrategista de Negócios Digitais.
    Aplica o conceito do Prompt Mãe: Distinção entre atenção dispersa e território mental qualificado.
    """
    copy_response = (
        "📰 [POST FEED — ATENÇÃO VS TERRITÓRIO MENTAL]\n\n"
        "Seguidor não é cliente. Curtiu não significa comprou.\n\n"
        "A grande ilusão do mercado digital nos últimos anos foi confundir retenção de atenção com construção de critério de escolha.\n\n"
        "Atenção passageira se compra com dancinha e polêmica vazia. Território mental se constrói quando a sua explicação sobre o problema do cliente é mais precisa do que a dele mesmo.\n\n"
        "Quem domina a explicação de um mecanismo, domina a preferência de compra."
    )
    client, cleanup = await make_test_client(copy_response)
    try:
        phone = "5511991110005"
        # Onboarding
        await client.post(
            "/webhook/message",
            json={"message_id": "s5_1", "sender_id": phone, "message_text": "Juliana Copy, Estrategista Digital, @julianacopy", "timestamp": "2026-10-25T10:00:00Z"},
        )

        # Smart Intent Bypass direto para Feed
        r2 = await client.post(
            "/webhook/message",
            json={
                "message_id": "s5_2",
                "sender_id": phone,
                "message_text": "Quero um post para o feed sobre por que audiência não é garantia de vendas e como construir território mental",
                "timestamp": "2026-10-25T10:01:00Z",
            },
        )
        assert r2.status_code == 200
        data = r2.json()
        # Verified: bypassed Etapa 2 directly to COPY_REFINEMENT
        assert data["current_step"] == StepName.COPY_REFINEMENT.value
        assert data["format_type"] == FormatType.FEED.value
        assert "Seguidor não é cliente" in data["response_text"]
        assert "Sua copy de alta conversão para FEED" in data["response_text"]
    finally:
        await cleanup()
