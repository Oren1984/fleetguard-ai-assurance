"""Replaceable LLM provider for explanation generation, plus a grounding
validator that guards against fabricated (ungrounded) AI output.

LLM_PROVIDER env var selects the backend:
  - "mock"      (default) - deterministic template built directly from the
                 evidence and retrieved SOP text. No network call, no key
                 required. Always grounded by construction.
  - "openai"    - calls the OpenAI Chat Completions API via HTTP.
  - "anthropic" - calls the Anthropic Messages API via HTTP.

Every explanation - mock or real - passes through validate_grounding()
before being persisted. If it fails, the system returns the fixed string
"Insufficient Evidence" instead of the model's text. The system must never
present a fabricated answer as if it were grounded.
"""
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings
from app.logging_config import get_logger
from app.rag import SopMatch

logger = get_logger("fleetguard.llm")

INSUFFICIENT_EVIDENCE = "Insufficient Evidence"


@dataclass
class ExplanationResult:
    text: str
    grounded: bool
    provider: str


def _format_evidence(evidence: dict, reasons: list[dict]) -> str:
    lines = [f"- {r['factor']}: {r['detail']} (contributes {r['score_contribution']} points)" for r in reasons]
    return (
        f"Cargo temperature: {evidence.get('cargo_temp_c')}°C (setpoint {evidence.get('setpoint_c')}°C)\n"
        f"External temperature: {evidence.get('external_temp_c')}°C\n"
        f"Route delay: {evidence.get('route_delay_minutes')} minutes\n"
        f"Weather data available: {evidence.get('weather_data_available')}\n"
        "Risk factors:\n" + "\n".join(lines)
    )


def _format_sop(sop_matches: list[SopMatch]) -> str:
    if not sop_matches:
        return "(no matching SOP section retrieved)"
    return "\n\n".join(f"[{m.doc} - {m.section}]\n{m.excerpt}" for m in sop_matches)


def _mock_explanation(
    truck_id: str,
    risk_level: str,
    recommended_action: str,
    evidence: dict,
    reasons: list[dict],
    sop_matches: list[SopMatch],
) -> str:
    reason_text = "; ".join(r["detail"] for r in reasons)
    if sop_matches:
        top = sop_matches[0]
        sop_text = f" Per {top.doc} ({top.section}), this pattern requires the recommended response."
    else:
        sop_text = ""

    return (
        f"Truck {truck_id} is classified {risk_level} risk based on the following observed data: "
        f"{reason_text}. Recommended action: {recommended_action.replace('_', ' ').title()}."
        f"{sop_text}"
    )


def _call_openai(prompt: str) -> str:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        json={
            "model": settings.OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call_anthropic(prompt: str) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": settings.ANTHROPIC_MODEL,
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def _build_prompt(truck_id: str, risk_level: str, recommended_action: str, evidence: dict, reasons: list[dict], sop_matches: list[SopMatch]) -> str:
    return (
        "You are FleetGuard AI, a cold-chain risk assurance assistant. Explain the following risk "
        "classification using ONLY the data and SOP text provided below. Cite concrete numbers. "
        "Do not invent facts, locations, or procedures that are not present in the provided context. "
        "If the provided context is not sufficient to justify a confident explanation, respond with "
        f'exactly: "{INSUFFICIENT_EVIDENCE}"\n\n'
        f"Truck: {truck_id}\nRisk level: {risk_level}\nRecommended action: {recommended_action}\n\n"
        f"Evidence:\n{_format_evidence(evidence, reasons)}\n\n"
        f"Relevant SOP excerpts:\n{_format_sop(sop_matches)}\n"
    )


def validate_grounding(text: str, evidence: dict, reasons: list[dict]) -> bool:
    """Heuristic grounding check: the explanation must be non-empty and must
    reference the actual measured cargo temperature. This blocks responses
    that don't engage with the real evidence (e.g. generic or fabricated
    text) from being presented as grounded."""
    if not text or not text.strip():
        return False
    if text.strip() == INSUFFICIENT_EVIDENCE:
        return True

    cargo_temp = evidence.get("cargo_temp_c")
    if cargo_temp is not None:
        candidates = {f"{cargo_temp:.1f}", f"{cargo_temp:.0f}", str(cargo_temp)}
        if not any(c in text for c in candidates):
            return False

    if reasons and reasons[0].get("factor") != "nominal":
        # At least one risk factor keyword must be reflected in the explanation.
        factor_words = [r["factor"].replace("_", " ") for r in reasons]
        if not any(word.split()[0] in text.lower() for word in factor_words):
            return False

    return True


def generate_explanation(
    truck_id: str,
    risk_level: str,
    recommended_action: str,
    evidence: dict,
    reasons: list[dict],
    sop_matches: list[SopMatch],
) -> ExplanationResult:
    provider = settings.LLM_PROVIDER

    try:
        if provider == "mock":
            text = _mock_explanation(truck_id, risk_level, recommended_action, evidence, reasons, sop_matches)
        elif provider in {"openai", "anthropic"}:
            prompt = _build_prompt(truck_id, risk_level, recommended_action, evidence, reasons, sop_matches)
            text = _call_openai(prompt) if provider == "openai" else _call_anthropic(prompt)
        else:
            logger.warning("unknown_llm_provider", extra={"extra_fields": {"provider": provider}})
            text = INSUFFICIENT_EVIDENCE
    except Exception as exc:  # network/provider failure must degrade safely, never crash the pipeline
        logger.error("llm_provider_call_failed", extra={"extra_fields": {"provider": provider, "error": str(exc)}})
        text = INSUFFICIENT_EVIDENCE

    grounded = validate_grounding(text, evidence, reasons)
    if not grounded:
        logger.warning(
            "ungrounded_response_blocked",
            extra={"extra_fields": {"truck_id": truck_id, "provider": provider, "original_text": text}},
        )
        text = INSUFFICIENT_EVIDENCE

    return ExplanationResult(text=text, grounded=grounded, provider=provider)
