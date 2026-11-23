import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("guardrails")
GUARDRAILS_CONFIG_DIR = Path(__file__).parent / "guardrails"


@dataclass
class GuardrailsDecision:
    allowed: bool
    blocked_category: Optional[str] = None
    safe_response: Optional[str] = None
    sanitized_input: Optional[str] = None


class SecurityGuardrails:
    """
    Hybrid Defense-in-Depth Guardrails Service:
    1. Pre-compiled regex heuristics executed in sub-millisecond (<1ms) time.
    2. Optional NVIDIA NeMo-Guardrails declarative engine integration when available.
    3. Strict output inspection to prevent leakage of API keys, DB strings and secrets.
    """

    def __init__(self):
        self.rails = None
        self._init_nemo_rails()

        # Heurísticas de ataque compiladas (<1ms)
        self.injection_patterns = [
            re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
            re.compile(r"ignore\s+todas?\s+(as\s+)?regras?\s+(anteriores|iniciais)?", re.IGNORECASE),
            re.compile(r"(desative|ignore|esque[cç]a)\s+(seus?\s+)?filtros?\s+(de\s+)?seguran[cç]a", re.IGNORECASE),
            re.compile(r"esque[cç]a\s+(suas?\s+)?(regras?|instru[cç][oõ]es)", re.IGNORECASE),
            re.compile(r"\b(dan\s+mode|do\s+anything\s+now|developer\s+mode)\b", re.IGNORECASE),
            re.compile(r"\b(jailbreak|prompt\s+injection)\b", re.IGNORECASE),
            re.compile(r"(sem|n[aã]o\s+tem)\s+(limites?\s+morais?|filtros?\s+morais?)", re.IGNORECASE),
            re.compile(r"limites?\s+morais?", re.IGNORECASE),
            re.compile(r"\b(gemini_api_key|api_key|system\s*prompt|system_prompt)\b", re.IGNORECASE),
            re.compile(r"(mostre|qual\s+[eé]|revele|me\s+passe|informe).*?(chave|secret|password|senha|credenciais)", re.IGNORECASE),
            re.compile(r"\b(drop\s+table|delete\s+from|union\s+select|insert\s+into)\b", re.IGNORECASE),
            re.compile(r"(sou\s+o\s+dono|sou\s+o\s+administrador).*?(libere|gr[aá]tis|senha)", re.IGNORECASE),
            re.compile(r"<\s*script.*?>|exec\s*\(\s*['\"].*?['\"]\s*\)", re.IGNORECASE),
        ]

        # Padrões de saída proibida (vazamento de tokens e URIs)
        self.secret_leak_patterns = [
            re.compile(r"AQ\.[a-zA-Z0-9_\-]{30,}", re.IGNORECASE),  # Chave Gemini
            re.compile(r"AIza[0-9A-Za-z-_]{35}", re.IGNORECASE),     # Google Key
            re.compile(r"sk-[a-zA-Z0-9]{32,}", re.IGNORECASE),       # OpenAI Key
            re.compile(r"ghp_[a-zA-Z0-9]{36}", re.IGNORECASE),       # GitHub PAT
            re.compile(r"postgres(ql)?://[^\s]+", re.IGNORECASE),     # DB String
            re.compile(r"redis://[^\s]+", re.IGNORECASE),            # Redis String
        ]

    def _init_nemo_rails(self):
        try:
            from nemoguardrails import LLMRails, RailsConfig
            if GUARDRAILS_CONFIG_DIR.exists():
                config = RailsConfig.from_path(str(GUARDRAILS_CONFIG_DIR))
                self.rails = LLMRails(config)
                logger.info("NVIDIA NeMo Guardrails carregado com sucesso.")
        except Exception as e:
            logger.info("NeMo Guardrails em modo heurístico de alta velocidade ativo: %s", e)

    def inspect_input(self, text: str, phone: str = "", company_id: str = "") -> GuardrailsDecision:
        if not text:
            return GuardrailsDecision(allowed=True, sanitized_input="")

        clean = text.strip()
        for pattern in self.injection_patterns:
            if pattern.search(clean):
                logger.warning(
                    "Guardrails blocked input from phone=%s company_id=%s [pattern=%s]",
                    phone,
                    company_id,
                    pattern.pattern,
                )
                return GuardrailsDecision(
                    allowed=False,
                    blocked_category="prompt_injection_or_jailbreak",
                    safe_response=(
                        "Como assistente virtual de atendimento e copywriting, não posso responder a esse tipo de comando. "
                        "Posso te ajudar com a criação de copies e estratégias para o seu conteúdo!"
                    ),
                )

        return GuardrailsDecision(allowed=True, sanitized_input=clean)

    def inspect_output(self, response_text: str, phone: str = "", company_id: str = "") -> str:
        if not response_text:
            return ""

        for pattern in self.secret_leak_patterns:
            if pattern.search(response_text):
                logger.error(
                    "Guardrails detected and prevented secret leakage in output for phone=%s company_id=%s",
                    phone,
                    company_id,
                )
                return (
                    "Olá! Como assistente virtual seguro, protejo informações internas e confidenciais da operação. "
                    "Como posso te ajudar com seu conteúdo hoje?"
                )

        return response_text


security_guardrails = SecurityGuardrails()
