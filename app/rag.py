import logging
from typing import List, Optional

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import KnowledgeChunk

logger = logging.getLogger(__name__)
settings = get_settings()

_embeddings_client: Optional[Embeddings] = None


def get_embeddings_model() -> Embeddings:
    """Returns or instantiates the default Gemini embeddings client."""
    global _embeddings_client
    if _embeddings_client is None:
        _embeddings_client = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=settings.GEMINI_API_KEY,
            output_dimensionality=768,
        )
    return _embeddings_client


def set_embeddings_model(model: Optional[Embeddings]) -> None:
    """Allows test harness to inject fake or mock embeddings."""
    global _embeddings_client
    _embeddings_client = model


async def retrieve_relevant_knowledge(
    db: AsyncSession,
    query: str,
    niche: Optional[str] = None,
    format_type: Optional[str] = None,
    top_k: int = 3,
    embeddings_model: Optional[Embeddings] = None,
) -> List[KnowledgeChunk]:
    """
    Performs cosine similarity search using pgvector over KnowledgeChunk records,
    with intelligent fallback to general copywriting frameworks.
    """
    embedder = embeddings_model or get_embeddings_model()
    try:
        query_vector = await embedder.aembed_query(query)
    except Exception as exc:
        logger.warning("Could not generate query embedding: %s. Continuing without RAG.", exc)
        return []

    # Build similarity query with optional niche/format preference
    filters = []
    if niche:
        filters.append(
            or_(
                KnowledgeChunk.niche == niche,
                KnowledgeChunk.niche.is_(None),
                KnowledgeChunk.niche == "Geral",
            )
        )
    if format_type:
        filters.append(
            or_(
                KnowledgeChunk.format_type == format_type,
                KnowledgeChunk.format_type.is_(None),
                KnowledgeChunk.format_type == "GERAL",
            )
        )

    stmt = select(KnowledgeChunk)
    if filters:
        stmt = stmt.where(and_(*filters))

    # Try native pgvector cosine distance search (PostgreSQL with pgvector)
    try:
        stmt_pg = stmt.order_by(KnowledgeChunk.embedding.cosine_distance(query_vector)).limit(top_k)
        result = await db.execute(stmt_pg)
        return list(result.scalars().all())
    except Exception as exc:
        # Fallback for SQLite in test harness where pgvector <=> operator is unavailable
        try:
            stmt_sqlite = stmt.limit(top_k)
            result = await db.execute(stmt_sqlite)
            return list(result.scalars().all())
        except Exception:
            logger.error("RAG search error: %s", exc)
            return []


def format_rag_context(chunks: List[KnowledgeChunk]) -> str:
    """Formats retrieved knowledge chunks into structured instructions for the LLM prompt."""
    if not chunks:
        return ""

    header = "🎯 REFERÊNCIAS E DIRETRIZES DA NOSSA BASE DE CONHECIMENTO (PLAYBOOK VALIDADO):"
    blocks = [header]
    for idx, c in enumerate(chunks, 1):
        tags = []
        if c.niche:
            tags.append(f"Nicho: {c.niche}")
        if c.format_type:
            tags.append(f"Formato: {c.format_type}")
        if c.doc_type:
            tags.append(f"Tipo: {c.doc_type}")
        tag_line = f" [{', '.join(tags)}]" if tags else ""

        blocks.append(f"### Referência {idx}: {c.title}{tag_line}\n{c.content.strip()}")

    blocks.append(
        "⚡ INSTRUÇÃO MANDATÓRIA: Utilize os frameworks, ganchos e estruturas acima para nortear "
        "a persuasão e os elementos da copy gerada."
    )
    return "\n\n".join(blocks)
