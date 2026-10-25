import logging
from pathlib import Path
import re
from datetime import datetime
from typing import Any, Dict, Literal, Optional, Tuple

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph

from app.config import get_settings
from app.schemas import AgentState, FormatType, StepName

logger = logging.getLogger(__name__)
settings = get_settings()

_CACHED_MASTER_PROMPT: Optional[str] = None


def get_master_prompt() -> str:
    """Loads the master Neurocopy prompt from knowledge_base folder."""
    global _CACHED_MASTER_PROMPT
    if _CACHED_MASTER_PROMPT is not None:
        return _CACHED_MASTER_PROMPT

    knowledge_dir = Path(__file__).resolve().parent.parent / "knowledge_base"
    candidates = [
        knowledge_dir / "Prompt mãe.md",
        knowledge_dir / "Prompt mae.md",
        knowledge_dir / "prompt_mae.md",
        knowledge_dir / "prompt_mae.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                content = candidate.read_text(encoding="utf-8").strip()
                if content:
                    _CACHED_MASTER_PROMPT = content
                    logger.info(
                        "Successfully loaded Master Neurocopy Prompt from %s (%d chars)",
                        candidate.name,
                        len(content),
                    )
                    return _CACHED_MASTER_PROMPT
            except Exception as e:
                logger.warning("Error reading %s: %s", candidate, e)

    if knowledge_dir.exists():
        for p in knowledge_dir.iterdir():
            if "prompt" in p.name.lower() and p.suffix.lower() in (".md", ".txt"):
                try:
                    content = p.read_text(encoding="utf-8").strip()
                    if content:
                        _CACHED_MASTER_PROMPT = content
                        return _CACHED_MASTER_PROMPT
                except Exception:
                    pass

    _CACHED_MASTER_PROMPT = (
        "Você é um estrategista de Neurocopy especializado em percepção humana, "
        "comportamento de decisão, comunicação e narrativas de alta autoridade."
    )
    return _CACHED_MASTER_PROMPT


# ---------------------------------------------------------
# Dynamic Menus & Prompts from Bot Workflow Diagram
# ---------------------------------------------------------

ONBOARDING_GREETING_TEXT = (
    "Oi! Vamos configurar seu assistente de conteúdo. "
    "Qual é o seu nome, qual é o seu segmento e qual é o @ da sua marca?"
)

MENU_ETAPA1_TEXT = (
    "O que vamos criar hoje? Pode escolher uma opção ou me explicar sua ideia com suas próprias palavras:\n\n"
    "1. 📖 Narrativa para stories\n"
    "2. 🎬 Roteiro para reels\n"
    "3. 📰 Conteúdo para Feed\n"
    "4. 💬 Mensagem para leads no whatsapp\n\n"
    "👉 Responda com um número (1 a 4) ou me envie sua ideia!"
)

FORMAT_MAP: Dict[str, str] = {
    "1": FormatType.STORIES.value,
    "STORIES": FormatType.STORIES.value,
    "STORY": FormatType.STORIES.value,
    "NARRATIVA PARA STORIES": FormatType.STORIES.value,
    "2": FormatType.REELS.value,
    "REELS": FormatType.REELS.value,
    "REEL": FormatType.REELS.value,
    "ROTEIRO PARA REELS": FormatType.REELS.value,
    "3": FormatType.FEED.value,
    "FEED": FormatType.FEED.value,
    "POST": FormatType.FEED.value,
    "CONTEÚDO PARA FEED": FormatType.FEED.value,
    "CONTEUDO PARA FEED": FormatType.FEED.value,
    "4": FormatType.WHATSAPP_LEAD.value,
    "WHATSAPP": FormatType.WHATSAPP_LEAD.value,
    "LEADS": FormatType.WHATSAPP_LEAD.value,
    "MENSAGEM PARA LEADS": FormatType.WHATSAPP_LEAD.value,
}

ETAPA2_QUESTIONS: Dict[str, str] = {
    FormatType.STORIES.value: (
        "Você quer vender ou promover algo (produto ou serviço) ou é um conteúdo de rotina e conexão?\n\n"
        "1. 🛒 Quero vender / promover\n"
        "2. ☕ Conteúdo de rotina e criar conexão\n\n"
        "👉 Responda 1 ou 2."
    ),
    FormatType.REELS.value: (
        "Qual é o objetivo principal desse Reel?\n\n"
        "1. 🛒 Quero vender / promover produto ou serviço\n"
        "2. 🚀 Abordar tema viral / autoridade com ponto de vista disruptivo\n"
        "3. ☕ Conteúdo de rotina e criar conexão\n\n"
        "👉 Responda 1, 2 ou 3."
    ),
    FormatType.FEED.value: (
        "Como quer estruturar esse conteúdo de Feed?\n\n"
        "1. 🖼️ Post único (estático)\n"
        "2. 📑 Carrossel\n"
        "3. 💡 Me dê ideias baseadas no meu negócio\n\n"
        "👉 Responda 1, 2 ou 3."
    ),
    FormatType.WHATSAPP_LEAD.value: (
        "Qual é o objetivo da mensagem com o seu lead?\n\n"
        "1. ❄️ Abordagem inicial de novo lead\n"
        "2. 🤝 Apresentação de oferta e fechamento\n"
        "3. 🔥 Reativação de leads antigos\n\n"
        "👉 Responda 1, 2 ou 3."
    ),
}

ETAPA2_CHOICES: Dict[str, Dict[str, str]] = {
    FormatType.STORIES.value: {
        "1": "Vender produto/serviço",
        "2": "Rotina e conexão",
    },
    FormatType.REELS.value: {
        "1": "Vender produto/serviço",
        "2": "Viral e autoridade disruptiva",
        "3": "Rotina e conexão",
    },
    FormatType.FEED.value: {
        "1": "Post único estático",
        "2": "Carrossel",
        "3": "Ideias baseadas no negócio",
    },
    FormatType.WHATSAPP_LEAD.value: {
        "1": "Abordagem inicial",
        "2": "Apresentação de oferta e fechamento",
        "3": "Reativação de leads antigos",
    },
}

ONBOARDED_STEPS = {
    StepName.CHOOSE_FORMAT.value,
    StepName.CHOOSE_SUB_INTENT.value,
    StepName.AWAITING_COPY_BRIEF.value,
    StepName.GENERATE_COPY.value,
    StepName.COPY_REFINEMENT.value,
}


# ---------------------------------------------------------
# Extraction Helpers
# ---------------------------------------------------------


def parse_onboarding_input(text: str) -> Tuple[str, str, Optional[str]]:
    """
    Extracts name, segment/niche and @brand_handle from user's response.
    Example: "Sou o Lucas, trabalho com nutrição e meu @ é @lucasnutri"
    """
    clean_text = text.strip()

    # Extract @handle if present
    handle_match = re.search(r"@[A-Za-z0-9_\.]+", clean_text)
    brand_handle = handle_match.group(0) if handle_match else None

    # Remove handle from text for easier parsing
    text_without_handle = re.sub(r"@[A-Za-z0-9_\.]+", "", clean_text).strip()
    # Strip phrases referencing the handle
    text_without_handle = re.sub(
        r"(,\s*)?(e\s+)?(o\s+)?(meu\s+)?(@|arroba)(\s+da\s+minha\s+marca|\s+da\s+marca)?\s*(é)?\s*$",
        "",
        text_without_handle,
        flags=re.IGNORECASE,
    ).strip()

    # Split into parts
    parts = [
        p.strip()
        for p in re.split(
            r"[,;\n-]| e meu segmento é | e meu segmento | e trabalho com | e sou ",
            text_without_handle,
            flags=re.IGNORECASE,
        )
        if p.strip()
    ]

    name = "Criador"
    segment = "Geral"

    if len(parts) >= 2:
        name = re.sub(r"^(meu nome é|sou o|sou a|sou|me chamo|eu sou)\s*", "", parts[0], flags=re.IGNORECASE).strip()
        segment = re.sub(r"^(trabalho com|sou|meu segmento é|meu nicho é)\s*", "", parts[1], flags=re.IGNORECASE).strip()
        segment = re.sub(r"\s*(e\s+)?(meu\s+)?@.*$", "", segment, flags=re.IGNORECASE).strip()
    elif len(parts) == 1:
        words = parts[0].split()
        if len(words) >= 1:
            name = words[0].replace("Sou", "").replace("Eu", "").strip() or "Criador"
        if len(words) > 1:
            segment = " ".join(words[1:])

    return name, segment, brand_handle


def detect_clear_intent(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Detects if the user's message already contains explicit format and intent,
    allowing the bot to skip ETAPA 2 as specified in the flowchart.
    Returns: (format_type, sub_intent, brief)
    """
    t = text.lower()
    words = t.split()

    format_type = None
    sub_intent = None

    if "storie" in t or "story" in t:
        format_type = FormatType.STORIES.value
        if "vend" in t or "promo" in t or "oferta" in t:
            sub_intent = "Vender produto/serviço"
        elif "rotina" in t or "conex" in t or "dia a dia" in t:
            sub_intent = "Rotina e conexão"

    elif "reel" in t:
        format_type = FormatType.REELS.value
        if "vend" in t or "curso" in t:
            sub_intent = "Vender produto/serviço"
        elif "viral" in t or "autoridade" in t or "disrupt" in t:
            sub_intent = "Viral e autoridade disruptiva"
        elif "rotina" in t or "conex" in t:
            sub_intent = "Rotina e conexão"

    elif "feed" in t or "carrossel" in t or "post" in t:
        format_type = FormatType.FEED.value
        if "carrossel" in t:
            sub_intent = "Carrossel"
        elif "estatico" in t or "estático" in t or "foto" in t:
            sub_intent = "Post único estático"
        elif "ideia" in t or "sugest" in t:
            sub_intent = "Ideias baseadas no negócio"

    elif "whatsapp" in t or "lead" in t:
        format_type = FormatType.WHATSAPP_LEAD.value
        if "frio" in t or "novo" in t or "aborda" in t:
            sub_intent = "Abordagem inicial"
        elif "fech" in t or "proposta" in t:
            sub_intent = "Apresentação de oferta e fechamento"
        elif "reativ" in t or "antigo" in t:
            sub_intent = "Reativação de leads antigos"

    # If format is found and the user provided more than 4 words, it's a clear detailed intent!
    if format_type and len(words) >= 4:
        sub_intent = sub_intent or "Personalizado"
        return format_type, sub_intent, text

    return None, None, None


# ---------------------------------------------------------
# Graph Nodes
# ---------------------------------------------------------


def eval_daily_trigger(state: AgentState) -> Dict[str, Any]:
    """
    Temporal trigger node.
    Compares last_interaction_at::date with current message timestamp date.
    If it's a new day and onboarding is done, starts ETAPA 1.
    """
    last_interaction = state.get("last_interaction_at")
    message_time = state.get("message_timestamp") or datetime.now()
    current_step = state.get("current_step", StepName.ASK_ONBOARDING.value)
    name = state.get("name") or "Criador"

    is_onboarded = current_step in ONBOARDED_STEPS or bool(state.get("niche"))

    if last_interaction and is_onboarded:
        last_date = last_interaction.date() if isinstance(last_interaction, datetime) else last_interaction
        current_date = message_time.date() if isinstance(message_time, datetime) else message_time

        if current_date > last_date:
            logger.info("Daily trigger activated: new day for user %s", state.get("user_id"))
            return {
                "current_step": StepName.CHOOSE_FORMAT.value,
                "format_type": None,
                "sub_intent": None,
                "daily_trigger_fired": True,
                "response_text": (
                    f"👋 Olá {name}! Novo dia, novos conteúdos!\n\n"
                    f"{MENU_ETAPA1_TEXT}"
                ),
            }

    return {"daily_trigger_fired": False}


def onboarding_node(state: AgentState) -> Dict[str, Any]:
    """
    Onboarding: single comprehensive question to configure creator profile.
    'Oi! Vamos configurar seu assistente de conteúdo. Qual é o seu nome, qual é o seu segmento e qual é o @ da sua marca?'
    """
    input_text = (state.get("input_text") or "").strip()

    # Initial greeting trigger
    if input_text.lower() in {"oi", "olá", "ola", "começar", "comecar", "start", "iniciar", "bom dia", "boa tarde"}:
        return {
            "current_step": StepName.ASK_ONBOARDING.value,
            "response_text": ONBOARDING_GREETING_TEXT,
        }

    name, segment, brand_handle = parse_onboarding_input(input_text)
    brand_text = f" ({brand_handle})" if brand_handle else ""

    return {
        "name": name,
        "niche": segment,
        "profession": segment,
        "brand_handle": brand_handle,
        "current_step": StepName.CHOOSE_FORMAT.value,
        "response_text": (
            f"🎉 Prazer, {name}! Seu assistente está configurado para o segmento *{segment}*{brand_text}.\n\n"
            f"{MENU_ETAPA1_TEXT}"
        ),
    }


def format_selection_node(state: AgentState) -> Dict[str, Any]:
    """
    ETAPA 1:
    Detects format choice (1..4) or checks if the message already has a clear detailed intent.
    If clear: skips ETAPA 2 directly to generation.
    Otherwise: transitions to ETAPA 2 question for that format.
    """
    input_text = (state.get("input_text") or "").strip()
    raw_choice = input_text.upper()

    # 1. Smart intent check: does user message already explain what they want?
    detected_format, detected_sub_intent, brief = detect_clear_intent(input_text)
    if detected_format:
        logger.info("Smart intent detected: skipping Etapa 2 [format=%s, intent=%s]", detected_format, detected_sub_intent)
        return {
            "format_type": detected_format,
            "sub_intent": detected_sub_intent,
            "input_text": brief,
            "current_step": StepName.GENERATE_COPY.value,
        }

    # 2. Closed choice check (1, 2, 3, 4)
    if raw_choice not in FORMAT_MAP:
        return {
            "current_step": StepName.CHOOSE_FORMAT.value,
            "response_text": (
                "⚠️ Não entendi a opção escolhida.\n\n"
                f"{MENU_ETAPA1_TEXT}"
            ),
        }

    selected_format = FORMAT_MAP[raw_choice]
    question_etapa2 = ETAPA2_QUESTIONS.get(selected_format, "")

    return {
        "format_type": selected_format,
        "current_step": StepName.CHOOSE_SUB_INTENT.value,
        "response_text": f"🎯 Formato: *{selected_format}*\n\n{question_etapa2}",
    }


def sub_intent_node(state: AgentState) -> Dict[str, Any]:
    """
    ETAPA 2:
    Refines intent based on the selected format, then asks for copy details or generates ideas.
    """
    format_type = state.get("format_type") or FormatType.STORIES.value
    input_text = (state.get("input_text") or "").strip()
    choice_map = ETAPA2_CHOICES.get(format_type, {})

    sub_intent = choice_map.get(input_text) or input_text

    # Special case: Feed option 3 ("Me dê ideias baseadas no meu negócio")
    if format_type == FormatType.FEED.value and input_text == "3":
        return {
            "sub_intent": "Ideias baseadas no negócio",
            "input_text": "Gere 3 ideias e ângulos de conteúdo de alto valor e engajamento para meu nicho",
            "current_step": StepName.GENERATE_COPY.value,
        }

    return {
        "sub_intent": sub_intent,
        "current_step": StepName.AWAITING_COPY_BRIEF.value,
        "response_text": (
            f"✅ Foco definido: *{sub_intent}*.\n\n"
            "Agora me mande o tema central, produto ou ideia que você quer abordar nessa copy:"
        ),
    }


def create_generate_copy_node(llm: BaseChatModel):
    """Factory creating copy execution node with injected LLM and RAG context."""

    async def generate_copy_node(state: AgentState) -> Dict[str, Any]:
        name = state.get("name") or "Criador"
        profession = state.get("profession") or "Profissional"
        niche = state.get("niche") or "Geral"
        brand_handle = state.get("brand_handle") or ""
        format_type = state.get("format_type") or FormatType.FEED.value
        sub_intent = state.get("sub_intent") or "Alta Conversão"
        user_brief = (state.get("input_text") or "").strip()

        brand_line = f"- @ da Marca: {brand_handle}\n" if brand_handle else ""

        master_prompt = get_master_prompt()
        system_instruction = (
            f"{master_prompt}\n\n"
            "=== DIRETRIZ DE EXECUÇÃO PRÁTICA ===\n"
            "Aplique rigorosamente as leis, princípios de percepção humana, quebra de clichês e arquitetura "
            "de decisão do Sistema-Mestre de Neurocopy acima na elaboração da copy solicitada a seguir."
        )

        rag_context = (state.get("rag_context") or "").strip()
        rag_section = f"\n{rag_context}\n\n" if rag_context else ""

        user_prompt = (
            f"PERFIL DO NEGÓCIO:\n"
            f"- Nome: {name}\n"
            f"- Profissão/Segmento: {niche}\n"
            f"{brand_line}"
            f"- Formato Solicitado: {format_type}\n"
            f"- Objetivo/Intenção da Etapa 2: {sub_intent}\n\n"
            f"BRIEFING DO CRIADOR:\n"
            f"{user_brief}\n\n"
            f"{rag_section}"
            f"REQUISITOS MANDATÓRIOS:\n"
            f"1. Se STORIES: Estruture em sequência de telas numeradas (Gancho, Conexão/Dor, Oferta/Conteúdo, CTA).\n"
            f"2. Se REELS: Estruture em Roteiro com Gancho Visual/Áudio nos primeiros 3 segundos, Desenvolvimento dinâmico e CTA.\n"
            f"3. Se FEED: Se post único, crie legenda magnética com primeira linha irresistível; se carrossel, divida tela a tela com gancho na capa e CTA na última tela.\n"
            f"4. Se WHATSAPP: Escreva mensagem direta, humana, persuasiva e com pergunta de engajamento no final para facilitar a resposta do lead.\n"
            f"5. Respeite o objetivo '{sub_intent}' e converse diretamente com as dores do segmento '{niche}'."
        )

        messages = [
            SystemMessage(content=system_instruction),
            HumanMessage(content=user_prompt),
        ]

        logger.info("Invoking LLM for user %s [format=%s, sub_intent=%s]", state.get("user_id"), format_type, sub_intent)
        ai_response = await llm.ainvoke(messages)
        if isinstance(ai_response.content, str):
            copy_content = ai_response.content
        elif isinstance(ai_response.content, list):
            copy_content = "\n".join(
                p.get("text", "") if isinstance(p, dict) else getattr(p, "text", str(p))
                for p in ai_response.content
            )
        else:
            copy_content = str(ai_response.content)

        return {
            "current_step": StepName.COPY_REFINEMENT.value,
            "response_text": (
                f"🔥 *Sua copy de alta conversão para {format_type} ({sub_intent}) está pronta!*\n\n"
                f"{copy_content}\n\n"
                f"---\n"
                f"Gostou? Quer ajustar algo (tom, CTA, comprimento) ou criar outro formato?\n"
                f"Responda com seu ajuste ou digite 'MENU' para criar um novo conteúdo."
            ),
        }

    return generate_copy_node


# ---------------------------------------------------------
# Routing Logic
# ---------------------------------------------------------


def route_after_eval(state: AgentState) -> Literal["end", "onboarding", "format_selection", "sub_intent", "generate_copy"]:
    """Determines next node following temporal check."""
    if state.get("daily_trigger_fired"):
        return "end"

    current_step = state.get("current_step", StepName.ASK_ONBOARDING.value)
    input_text = (state.get("input_text") or "").strip().upper()

    # User typed MENU to return to format selection
    if input_text == "MENU" and current_step in ONBOARDED_STEPS:
        return "format_selection"

    if current_step == StepName.ASK_ONBOARDING.value:
        return "onboarding"

    if current_step == StepName.CHOOSE_FORMAT.value:
        return "format_selection"

    if current_step == StepName.CHOOSE_SUB_INTENT.value:
        return "sub_intent"

    if current_step in {StepName.AWAITING_COPY_BRIEF.value, StepName.GENERATE_COPY.value, StepName.COPY_REFINEMENT.value}:
        return "generate_copy"

    return "onboarding"


def route_after_format(state: AgentState) -> Literal["end", "generate_copy"]:
    """Routes to generation if smart intent skipped Etapa 2, otherwise ends turn."""
    if state.get("current_step") == StepName.GENERATE_COPY.value:
        return "generate_copy"
    return "end"


def route_after_sub_intent(state: AgentState) -> Literal["end", "generate_copy"]:
    """Routes to generation if Etapa 2 automatically triggered copy generation (e.g. Ideas)."""
    if state.get("current_step") == StepName.GENERATE_COPY.value:
        return "generate_copy"
    return "end"


# ---------------------------------------------------------
# Graph Builder Factory
# ---------------------------------------------------------


def build_copy_graph(llm: Optional[BaseChatModel] = None) -> StateGraph:
    """
    Constructs and compiles the StateGraph according to the new workflow.
    """
    if llm is None:
        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.7,
        )

    builder = StateGraph(AgentState)

    # Register nodes
    builder.add_node("eval_daily_trigger", eval_daily_trigger)
    builder.add_node("onboarding", onboarding_node)
    builder.add_node("format_selection", format_selection_node)
    builder.add_node("sub_intent", sub_intent_node)
    builder.add_node("generate_copy", create_generate_copy_node(llm))

    # Entry point
    builder.set_entry_point("eval_daily_trigger")

    # Routing from temporal node
    builder.add_conditional_edges(
        "eval_daily_trigger",
        route_after_eval,
        {
            "end": END,
            "onboarding": "onboarding",
            "format_selection": "format_selection",
            "sub_intent": "sub_intent",
            "generate_copy": "generate_copy",
        },
    )

    # Conditional routing after format selection (to skip Etapa 2 if intent clear)
    builder.add_conditional_edges(
        "format_selection",
        route_after_format,
        {
            "end": END,
            "generate_copy": "generate_copy",
        },
    )

    # Conditional routing after sub-intent (to generate ideas immediately if chosen)
    builder.add_conditional_edges(
        "sub_intent",
        route_after_sub_intent,
        {
            "end": END,
            "generate_copy": "generate_copy",
        },
    )

    builder.add_edge("onboarding", END)
    builder.add_edge("generate_copy", END)

    return builder.compile()
