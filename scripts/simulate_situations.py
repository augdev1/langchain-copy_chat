"""
Simulador de Testes Locais para o Bot de Neurocopy.
Testa 5 situações reais baseadas no Sistema-Mestre de Neurocopy (Prompt Mãe).
Se GEMINI_API_KEY estiver configurada no .env com uma chave válida, realiza
chamadas reais com o Gemini 2.5 Flash. Caso contrário, executa em modo de simulação estruturada.
"""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

# Force UTF-8 on Windows
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.config import get_settings
from app.graph import build_copy_graph, get_master_prompt
from app.schemas import AgentState, FormatType, StepName


SITUATIONS = [
    {
        "id": 1,
        "title": "Situação 1: O 'Quase Resultado' e Frustração Silenciosa (Stories)",
        "niche": "Personal Trainer de Alta Performance",
        "name": "Rodrigo Silva",
        "brand_handle": "@rodrigopersonal",
        "format": FormatType.STORIES.value,
        "sub_intent": "Vender produto/serviço",
        "brief": "A pior sensação não é fracassar... é viver no quase resultado, treinando 6x na semana sem ver definição muscular real.",
        "neurocopy_concept": "Quebra da falsa crença do 'treinar mais / comer menos' e revelação do mecanismo de sobrecarga crônica do sistema nervoso e cortisol.",
    },
    {
        "id": 2,
        "title": "Situação 2: Choque Intelectual e Desmistificação de Crença Comum (Reels)",
        "niche": "Finanças & Blindagem Patrimonial",
        "name": "Lucas Mendes",
        "brand_handle": "@lucasfinancas",
        "format": FormatType.REELS.value,
        "sub_intent": "Viral e autoridade disruptiva",
        "brief": "Por que a poupança e o CDB de bancão estão empobrecendo a classe média com a falsa sensação de segurança.",
        "neurocopy_concept": "Distinção entre risco aparente e risco real (perda silenciosa do poder de compra acumulado vs volatilidade controlada).",
    },
    {
        "id": 3,
        "title": "Situação 3: Mecanismo Invisível e Distinção Técnica Sem Clichês (Feed Carrossel)",
        "niche": "Dermatologia & Rejuvenescimento Natural",
        "name": "Dra. Camila Santos",
        "brand_handle": "@dracamiladermato",
        "format": FormatType.FEED.value,
        "sub_intent": "Carrossel",
        "brief": "Por que preencher rugas isoladas deixa o rosto artificial e como o suporte ósseo profundo e coxins de gordura explicam o envelhecimento.",
        "neurocopy_concept": "Pensamento anatômico estrutural vs solução superficial; autoridade técnica sem arrogância e sem clichês de antes/depois.",
    },
    {
        "id": 4,
        "title": "Situação 4: Arquitetura de Decisão e Quebra de Objeção Sem Pressão (WhatsApp Leads)",
        "niche": "Consultoria em Gestão de Processos B2B",
        "name": "Marcos Vale",
        "brand_handle": "@marcosvale.gestao",
        "format": FormatType.WHATSAPP_LEAD.value,
        "sub_intent": "Apresentação de oferta e fechamento",
        "brief": "Lead qualificado que recebeu proposta comercial mas disse 'estou sem tempo para implementar a consultoria agora'.",
        "neurocopy_concept": "Reenquadramento de valor: a falta de tempo não é motivo para adiar, é o sintoma exato da ausência dos processos da consultoria.",
    },
    {
        "id": 5,
        "title": "Situação 5: Smart Intent Bypass com Reorganização de Território Mental (Feed Post)",
        "niche": "Estratégia de Negócios Digitais",
        "name": "Juliana Copy",
        "brand_handle": "@julianacopy",
        "format": FormatType.FEED.value,
        "sub_intent": "Personalizado (Bypass Etapa 2)",
        "brief": "Quero um post para o feed sobre por que audiência não é garantia de vendas e como construir território mental em vez de atrair curiosos.",
        "neurocopy_concept": "Smart Intent Bypass com separação conceitual entre retenção de atenção efêmera e construção de critério de escolha duradouro.",
    },
]


async def run_simulation():
    settings = get_settings()
    master_prompt = get_master_prompt()

    has_real_key = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here" and settings.GEMINI_API_KEY != "mock-api-key")

    print("=" * 70, flush=True)
    print("🧠 SIMULADOR DE NEUROCOPY — SISTEMA-MESTRE DE ENGENHARIA DE PERCEPÇÃO", flush=True)
    print("=" * 70, flush=True)
    print(f"📄 Prompt Mãe Carregado: {len(master_prompt)} caracteres", flush=True)
    print(f"🔑 Modelo Utilizado: {settings.GEMINI_MODEL}", flush=True)
    print("=" * 70, flush=True)

    graph = build_copy_graph()
    report_lines = [
        "# Resultados dos Testes Locais: 5 Situações Reais de Neurocopy\n",
        f"**Modelo Utilizado:** `{settings.GEMINI_MODEL}`  ",
        f"**Prompt Mãe Carregado:** `{len(master_prompt)}` caracteres de diretrizes estratégicas.\n",
        "---\n",
    ]

    for item in SITUATIONS:
        header = f"📌 {item['title']}"
        meta_info = f"👤 Criador: {item['name']} | Nicho: {item['niche']} ({item['brand_handle']})\n🎯 Formato: {item['format']} | Foco: {item['sub_intent']}\n💡 Conceito Neurocopy: {item['neurocopy_concept']}\n📝 Briefing: \"{item['brief']}\""

        print(f"\n{'#' * 70}", flush=True)
        print(header, flush=True)
        print(meta_info, flush=True)
        print(f"{'-' * 70}", flush=True)

        report_lines.append(f"## {item['title']}\n")
        report_lines.append(f"- **Criador:** {item['name']} ({item['brand_handle']})")
        report_lines.append(f"- **Nicho:** {item['niche']}")
        report_lines.append(f"- **Formato:** {item['format']} ({item['sub_intent']})")
        report_lines.append(f"- **Conceito Neurocopy:** {item['neurocopy_concept']}")
        report_lines.append(f"- **Briefing Submetido:** *\"{item['brief']}\"*\n")

        state: AgentState = {
            "name": item["name"],
            "profession": item["niche"],
            "niche": item["niche"],
            "brand_handle": item["brand_handle"],
            "current_step": StepName.GENERATE_COPY.value,
            "format_type": item["format"],
            "sub_intent": item["sub_intent"],
            "input_text": item["brief"],
            "message_timestamp": datetime.now(),
        }

        try:
            result = await graph.ainvoke(state)
            output = result.get("response_text", "")
            print(output, flush=True)
            report_lines.append("### Copy Gerada pelo Bot:\n")
            report_lines.append(output)
            report_lines.append("\n---\n")
        except Exception as e:
            err_msg = f"⚠️ Erro ao chamar Gemini: {e}"
            print(err_msg, flush=True)
            report_lines.append(f"*{err_msg}*\n\n---\n")

    report_path = Path("resultado_5_situacoes.md").resolve()
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"\n{'=' * 70}", flush=True)
    print(f"🎉 Simulação concluída! Relatório salvo em: {report_path}", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    asyncio.run(run_simulation())
