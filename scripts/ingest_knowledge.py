"""
Ingestion script for RAG Knowledge Base in PostgreSQL (pgvector).
Scans knowledge_base/ folder for .md, .txt, and .pdf files,
chunks content, computes Gemini embeddings, and persists to PostgreSQL.
"""
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Force UTF-8 stdout
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_factory, init_db
from app.models import KnowledgeChunk

settings = get_settings()
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"


def extract_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """Extracts simple YAML-like frontmatter metadata if present."""
    metadata = {}
    pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        raw_meta = match.group(1)
        clean_content = content[match.end() :]
        for line in raw_meta.split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                metadata[k.strip().lower()] = v.strip()
        return metadata, clean_content
    return metadata, content


def load_file_content(filepath: Path) -> Tuple[str, Dict[str, str]]:
    """Reads PDF, Markdown or TXT and returns (clean_text, metadata)."""
    ext = filepath.suffix.lower()
    meta = {"title": filepath.stem.replace("_", " ").title()}

    if ext == ".pdf":
        reader = PdfReader(filepath)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text, meta
    elif ext == ".docx":
        import zipfile
        import xml.etree.ElementTree as ET
        try:
            with zipfile.ZipFile(filepath) as z:
                tree = ET.fromstring(z.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs = []
            for p in tree.iterfind(".//w:p", ns):
                t = "".join(node.text for node in p.iterfind(".//w:t", ns) if node.text)
                if t.strip():
                    paragraphs.append(t.strip())
            clean_text = "\n\n".join(paragraphs)
            meta["niche"] = "Dermatologia / Estética"
            meta["doc_type"] = "narrativas_profissoes"
            return clean_text, meta
        except Exception as exc:
            print(f"❌ Erro ao ler docx {filepath}: {exc}")
            return "", meta
    elif ext in (".md", ".txt"):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        extracted_meta, clean_text = extract_frontmatter(raw)
        meta.update(extracted_meta)
        return clean_text, meta
    return "", meta


async def ingest_knowledge_base():
    print("🚀 Iniciando ingestão da Base de Conhecimento RAG (PostgreSQL + pgvector)...")
    await init_db()

    if not KNOWLEDGE_DIR.exists():
        print(f"❌ Diretório {KNOWLEDGE_DIR} não encontrado.")
        return

    files = [
        f for f in KNOWLEDGE_DIR.iterdir() if f.suffix.lower() in (".md", ".txt", ".pdf", ".docx")
    ]
    if not files:
        print(f"ℹ️ Nenhum arquivo encontrado em {KNOWLEDGE_DIR}.")
        return

    print(f"📂 Encontrados {len(files)} arquivos para processamento.")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " "],
    )

    embedder = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=settings.GEMINI_API_KEY,
        output_dimensionality=768,
    )

    total_chunks = 0
    async with async_session_factory() as session:
        # Clear existing knowledge chunks before re-ingestion
        print("🧹 Limpando chunks anteriores no PostgreSQL...")
        await session.execute(delete(KnowledgeChunk))
        await session.commit()

        for filepath in sorted(files):
            print(f"📄 Processando: {filepath.name}...")
            content, meta = load_file_content(filepath)
            if not content.strip():
                continue

            chunks = text_splitter.split_text(content)
            print(f"   ↳ Dividido em {len(chunks)} trechos. Gerando embeddings Gemini...")

            for i, chunk_text in enumerate(chunks, 1):
                try:
                    embedding = await embedder.aembed_query(chunk_text)
                except Exception as exc:
                    print(f"   ❌ Erro gerando embedding: {exc}")
                    continue

                title = meta.get("title", filepath.stem)
                chunk_record = KnowledgeChunk(
                    title=f"{title} (Parte {i})" if len(chunks) > 1 else title,
                    content=chunk_text,
                    niche=meta.get("niche"),
                    format_type=meta.get("format_type"),
                    doc_type=meta.get("doc_type", "playbook"),
                    embedding=embedding,
                )
                session.add(chunk_record)
                total_chunks += 1

            await session.commit()

    print(f"\n🎉 Ingestão concluída com sucesso! Total de {total_chunks} trechos indexados no pgvector.")


if __name__ == "__main__":
    asyncio.run(ingest_knowledge_base())
