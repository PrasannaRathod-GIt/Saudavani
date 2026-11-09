import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

_log = logging.getLogger("saudavani")

_GROQ_LANGUAGE = {
    "mr": "Marathi (Devanagari script)",
    "hi": "Hindi (Devanagari script)",
    "en": "English",
    "hinglish": "Hinglish (natural Roman-script Hindi mixed with common English trading words)",
}

# --- Groq reliability (Step 2F) ---------------------------------------------------------------------------------
GROQ_TIMEOUT_SECONDS = 8.0
GROQ_MAX_ATTEMPTS = 2
_GROQ_RETRY_DELAY_SECONDS = 0.3
# HTTP statuses that will not get better by retrying (bad request / auth / not found / validation).
_NON_RETRYABLE_STATUS = {400, 401, 403, 404, 422}

# Safe to expose on /health: only timestamps and an error CLASS name (optionally with an HTTP status). Never a key,
# a request body or an exception message.
GROQ_STATUS: dict[str, Any] = {"last_ok_at": None, "last_error": None, "last_error_at": None}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error_label(exc: BaseException) -> str:
    if isinstance(exc, asyncio.TimeoutError):
        return "Timeout"
    label = type(exc).__name__
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        label += f" (HTTP {status})"
    return label[:80]


def _record_ok() -> None:
    GROQ_STATUS["last_ok_at"] = _now_iso()


def _record_error(label: str) -> None:
    GROQ_STATUS["last_error"] = label
    GROQ_STATUS["last_error_at"] = _now_iso()


async def _groq_chat(
    messages: list[dict[str, str]],
    *,
    groq_client: Any,
    groq_model: str,
    temperature: float = 0.2,
    max_completion_tokens: int = 400,
) -> str:
    """One Groq chat completion with an 8 s timeout per attempt and at most two attempts.

    Returns the stripped answer text, or "" when both attempts fail (or no client is configured). It never raises,
    so a Groq failure cannot crash a conversation turn. Non-transient HTTP errors (400/401/403/404/422) are not
    retried. The existing AsyncGroq client and model are passed in by the caller (adapted from the plain signature
    `_groq_chat(messages)` because this project keeps the client in main.py).
    """
    if not groq_client:
        return ""
    for attempt in range(1, GROQ_MAX_ATTEMPTS + 1):
        try:
            response = await asyncio.wait_for(
                groq_client.chat.completions.create(
                    model=groq_model,
                    messages=messages,
                    temperature=temperature,
                    max_completion_tokens=max_completion_tokens,
                ),
                timeout=GROQ_TIMEOUT_SECONDS,
            )
            answer = (response.choices[0].message.content or "").strip()
            if answer:
                _record_ok()
                return answer
            _record_error("EmptyResponse")
            _log.warning("Groq returned an empty answer (attempt %d/%d)", attempt, GROQ_MAX_ATTEMPTS)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # timeouts and SDK/network errors; message text is never logged or stored
            label = _safe_error_label(exc)
            _record_error(label)
            _log.warning("Groq call failed (attempt %d/%d): %s", attempt, GROQ_MAX_ATTEMPTS, label)
            status = getattr(exc, "status_code", None)
            if isinstance(status, int) and status in _NON_RETRYABLE_STATUS:
                break
        if attempt < GROQ_MAX_ATTEMPTS:
            await asyncio.sleep(_GROQ_RETRY_DELAY_SECONDS)
    return ""


def _cut_at_sentence(text: str, limit: int = 700) -> str:
    """Keep text within `limit` characters, preferring a complete-sentence boundary (. ? ! or Devanagari danda)."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    window = text[:limit]
    for i in range(len(window) - 1, -1, -1):
        if window[i] in ".?!।":
            nxt = text[i + 1] if i + 1 < len(text) else ""
            # A real sentence end is followed by whitespace/end; this skips decimals such as "3,200.50".
            if (not nxt or nxt.isspace()) and i > 0:
                return window[: i + 1].strip()
    # No sentence boundary: cut at the last space so a word is not split, else hard cut.
    space = window.rfind(" ")
    cut = window[:space] if space > limit // 2 else window
    return cut.rstrip(" ,;:-") 


async def answer_off_topic(
    text: str,
    s: dict[str, Any],
    lang: str,
    *,
    groq_client: Any,
    groq_model: str,
    offer_active: Callable,
    ask_text: Callable,
    ui_lang: Callable,
    logger: Any,
) -> str:
    u = "hinglish" if lang == "hinglish" else ui_lang(lang)

    if not groq_client:
        return ask_text(lang, "offline_answer")

    pa = s.get("price_analysis") or {}

    facts = {
        "crop": s.get("commodity"),
        "product_form": s.get("product_form"),
        "variety": s.get("variety"),
        "quantity_quintals": s.get("quantity_quintals"),
        "district": s.get("district"),
        "market": s.get("market"),
        "quality_reported_by_farmer": s.get("quality") or {},
        "deal_status": s.get("deal_status"),
        "buyer_quote_reported_by_farmer_per_quintal": (
            s.get("reported_buyer_quote") or {}
        ).get("price_per_quintal"),
        "active_offer_per_quintal": (
            (s.get("buyer_offer") or {}).get("price_per_quintal")
            if offer_active(s)
            else None
        ),
        "farmer_counter_per_quintal": s.get("counter_price"),
        "verified_mandi_reference": (
            {
                "as_of": pa.get("as_of"),
                "stale": pa.get("stale"),
                "modal_per_quintal": pa.get("modal_reference"),
                "range_per_quintal": [
                    pa.get("fair_price_low"),
                    pa.get("fair_price_high"),
                ],
                "scope": pa.get("market_scope"),
            }
            if pa.get("available")
            else "none available"
        ),
    }

    system = (
        "You are SaudaVani, an experienced, friendly Indian mandi assistant talking to a farmer by voice. "
        f"Reply in {_GROQ_LANGUAGE[u]}; if the farmer mixes languages, stay natural but keep one language. "
        "Understand informal Marathi/Hindi/English farm vocabulary. Speak in at most 3 sentences, plain words, no lists or markdown. "
        "Use only the facts below and what the farmer said; never assume quality, variety or quantity that was not stated. "
        "Never invent mandi prices, buyer offers, MSP, quality premiums or payment status. Quote a price only from verified_mandi_reference, "
        "and say its date; if it is missing or stale, say no verified current price is available. "
        "Remember: all prices are INR per quintal, official data is a daily report not a live bid, and no real money moves in this prototype. "
        "If the question is unclear (a word or number you cannot understand), ask one short clarifying question. "
        "Do not ask for details already known. Ask at most one question. "
        "Never mention or hint at the farmer's private target or minimum price or any negotiation notes. "
        "If you do not know, say so briefly; never pretend to know official government facts.\n"
        f"Known facts: {json.dumps(facts, ensure_ascii=False, default=str)}"
    )

    recent = [
        {
            "role": m["role"],
            "content": str(m["content"])[:400],
        }
        for m in (s.get("history") or [])[-7:-1]
        if m.get("role") in {"user", "assistant"} and not m.get("private")
    ]

    messages = [
        {"role": "system", "content": system},
        *recent,
        {"role": "user", "content": text},
    ]

    answer = await _groq_chat(messages, groq_client=groq_client, groq_model=groq_model)
    if not answer:
        logger.warning("Groq fallback answer unavailable; using the offline answer")
        return ask_text(lang, "offline_answer")
    return _cut_at_sentence(answer, 700) or ask_text(lang, "offline_answer")