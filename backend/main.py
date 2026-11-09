"""SaudaVani - Indic Mandi Voice Assistant

Single-file FastAPI prototype with:
- 12 Maharashtra-first commodity catalogue and spoken aliases
- Commodity-specific variety and quality intake
- District + optional mandi intake (district is required for the official price lookup)
- Gnani Vachana REST STT/TTS
- Optional Groq assistant for off-flow questions (grounded in session state)
- data.gov.in / AGMARKNET variety-wise daily mandi-price lookup (curl or httpx transport)
- Evidence-based price range and counter-offer guidance
- Two-party deal confirmation and SQLite persistence
- SIMULATED escrow ledger (lock + release records only; actual money transferred is always INR 0)

IMPORTANT:
- AGMARKNET/data.gov.in prices are daily reported market data, not live auction bids.
- A deal lock is a record of agreed terms only. This prototype does not move money.
  Advance / remaining amounts are SIMULATED demo calculations.
- The confirmation endpoints are not authenticated; add real farmer/buyer auth before production.
  This prototype is NOT production-ready for real trading. The unauthenticated HTTP deal actions (buyer offer,
  confirm, escrow release, cancel) AND the spoken final confirmation / cancellation are DISABLED unless
  DEMO_ALLOW_UNAUTHENTICATED_ACTIONS=true (fails closed; DEMO_SINGLE_PARTY_LOCK cannot bypass it).
- LIMITATION: a session ID is NOT proof of identity. Anyone who knows it can read the public session state, join the
  WebSocket room and talk to /api/voice/process. Private farmer prices are therefore never spoken or returned, but
  per-user privacy is not guaranteed until real farmer/buyer authentication exists.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import logging
import mimetypes
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
import re
import shutil
import sqlite3
import statistics
import subprocess
import time
import unicodedata
import uuid
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlencode
from llm import answer_off_topic as _answer_off_topic_impl, GROQ_STATUS
from faq import detect_faq, faq_answer
from replies import _MSG, ask_text

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from groq import AsyncGroq
except Exception:  # Groq is optional for deterministic core-flow operation
    AsyncGroq = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------

load_dotenv()


from config import (
    GNANI_API_KEY,
    GNANI_BASE_URL,
    GNANI_STT_URL,
    GNANI_TTS_URL,
    GNANI_STT_MODEL,
    GNANI_STT_LANGUAGE,
    GNANI_STT_FORMAT,
    GNANI_TTS_MODEL,
    GNANI_TTS_VOICE,
    FFMPEG_BIN,
    GROQ_API_KEY,
    GROQ_MODEL,
    VERIFIED_RESOURCE_ID,
    LEGACY_RESOURCE_ID,
    DATA_GOV_IN_API_KEY,
    DATA_GOV_RESOURCE_ID,
    _RESOURCE_ID_OVERRIDDEN,
    _env_api_url,
    _API_URL_IGNORED,
    DATA_GOV_API_URL,
    DATA_GOV_STATE,
    DATA_GOV_LIMIT,
    DATA_GOV_TIMEOUT,
    DATA_GOV_TRANSPORT,
    DATA_GOV_CURL_URL_IN_ARGS,
    DATA_GOV_MAX_ATTEMPTS,
    PRICE_CACHE_SECONDS,
    PRICE_STALE_HOURS,
    DB_PATH,
    ADVANCE_PERCENT,
    DEMO_SINGLE_PARTY_LOCK,
    DEMO_ALLOW_UNAUTHENTICATED_ACTIONS,
    SESSION_HISTORY_LIMIT,
    DEFAULT_OFFER_VALID_MINUTES,
    MAX_AUDIO_BYTES,
    DEVA_DIGITS,
    IST,
    SESSION_ID_RE,
)

from offers import (
    _PUBLIC_OFFER_FIELDS,
    _public_offer,
    public_state,
    _offer_active,
    _submit_farmer_counter,
    _counter_sent_text,
    _mark_buyer_offer_unavailable,
    _handle_missing_buyer_offer,
    _market_display,
    _confirmation_readback,
    _market_counter_target,
    _offer_recommendation,
    _parse_offer_expiry,
    _expire_offer_if_needed,
    _reject_offer,
    _expire_offer,
    _expired_reply,
    ESCROW_SIM_NOTICE,
    _escrow_event,
    _create_simulated_escrow,
    _release_simulated_escrow,
    _lock_deal,
    configure_offer_helpers,
)
from prices import (
    _CURL_MARKER,
    _find_curl,
    _norm_market_value,
    _parse_market_date,
    _record_age_hours,
    _float_or_none,
    _run_curl,
    _data_gov_request,
    _fetch_data_gov_rows,
    _normalise_market_row,
    percentile,
    _price_unavailable,
    _record_key,
    _dedupe_market_variety,
    _collapse_per_market,
    _VARIETY_UNSPECIFIED,
    _LOCAL_VARIETY_KEYS,
    _LOCAL_VARIETY_TOKENS,
    _GENERIC_RECORD_VARIETIES,
    _variety_row_matches,
    fetch_mandi_benchmark,
    configure_price_helpers,
)

from state import (
    SESSIONS,
    SESSION_LOCKS,
    PRICE_CACHE,
    session_lock,
    new_session,
    db_connect,
    init_db,
    load_session,
    save_session,
    peek_session,
    log_deal_event,
)

from text_utils import (
    LANGUAGE_PROFILES,
    _MR_MARKERS,
    _HI_MARKERS,
    _EN_MARKERS,
    _ACK_TOKENS,
    _CODESWITCH_WORDS,
    _QUESTION_TOKENS,
    normalize_text,
    _alias_in,
    _lang_from_hint,
    detect_language,
    ui_lang,
    match_commodity,
    match_variety,
    find_district,
    canonical_district,
    district_variants,
    find_market,
    _NUMBER_WORDS,
    _HUNDRED_WORDS,
    _THOUSAND_WORDS,
    _SADE_WORDS,
    _QTY_QUINTAL_WORDS,
    _QTY_QUINTAL_DEVA,
    _QTY_KG_WORDS,
    _QTY_KG_DEVA,
    _QTY_TON_WORDS,
    _QTY_TON_DEVA,
    _QTY_PER_WORDS,
    _QTY_NEG_BEFORE,
    _QTY_NEG_AFTER,
    _QTY_FILLERS,
    _QTY_BLOCK_TOKENS,
    _unit_factor,
    _qty_tokens,
    _number_value,
    _number_phrase,
    _quantity_matches,
    parse_quantity,
    parse_bare_quantity,
    _DEVA,
    _QTY_STRIP,
    parse_price,
    parse_moisture_answer,
)

from catalog import (
    COMMODITIES,
    MARKET_COMMODITY_TERMS,
    DISTRICTS,
    MARKET_ALIASES,
    KNOWN_MARKETS,
    MARKET_WORDS,
    _MARKET_SKIP_TOKENS,
    _OTHER_VARIETY_TOKENS,
    _ANY_MARKET_TOKENS,
    _MARKET_FILLER_TOKENS,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

log = logging.getLogger("saudavani")

_groq_client = AsyncGroq(api_key=GROQ_API_KEY) if (GROQ_API_KEY and AsyncGroq) else None

# ---------------------------------------------------------------------------
# 2. Commodity catalogue (aliases are deliberately broad; canonical IDs are stable)
# ---------------------------------------------------------------------------



# Candidate EXACT values for filters[Commodity] (the API filter is case-sensitive).
# The AGMARKNET labels below are tried in order until one returns records; every returned row is
# re-checked against the label that was queried, so an HTTP 200 alone is never treated as success.



def commodity_terms(commodity_id: str, product_form: Optional[str] = None) -> list[str]:
    """Commodity labels to query, honouring raw-vs-processed product form."""
    form = normalize_text(product_form or "")
    base = list(MARKET_COMMODITY_TERMS.get(commodity_id, [COMMODITIES[commodity_id]["name"]]))
    if commodity_id == "paddy_rice":
        if "processed rice" in form:
            return ["Rice", "Basmati Rice"]
        return ["Paddy(Dhan)(Common)", "Paddy", "Paddy (Dhan)"]
    if commodity_id == "tur" and ("dal" in form or "डाळ" in form or "दाल" in form):
        return ["Arhar Dal(Tur Dal)", "Tur Dal"]
    if commodity_id == "urad" and ("dal" in form or "split" in form or "डाळ" in form or "दाल" in form):
        return ["Black Gram Dal (Urd Dal)", "Urad Dal"]
    if commodity_id == "cotton" and ("kapas" in form or "raw" in form):
        return ["Kapas", "Cotton", "Raw Cotton"]
    return base


# Maharashtra districts: (canonical name, API name variants to try, spoken aliases).
# District is NOT the same thing as the mandi/market (e.g. District Nashik, Market Lasalgaon).


def _is_any_market(value: Any) -> bool:
    """True for 'any market' style answers in any supported language (never a real APMC name)."""
    toks = normalize_text(str(value or "")).split()
    core = [t for t in toks if t not in _MARKET_FILLER_TOKENS]
    return bool(core) and len(toks) <= 6 and all(t in _ANY_MARKET_TOKENS for t in core)

configure_price_helpers(
    commodity_terms_fn=commodity_terms,
    is_any_market_fn=_is_any_market,
)


# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# 5. AGMARKNET / data.gov.in market-price integration
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# 6. Session state, question planning and deterministic conversation
# ---------------------------------------------------------------------------


def _toks(text: str) -> list[str]:
    return normalize_text(text).split()


def _phrase_in(norm: str, phrases: Any) -> bool:
    padded = f" {norm} "
    return any(f" {normalize_text(p)} " in padded for p in phrases)


def _tok_in(tokens: list[str], vocab: set[str]) -> bool:
    """Token match tolerant to speech-to-text spelling drift (Latin tokens only, conservative)."""
    for t in tokens:
        if t in vocab:
            return True
        if len(t) >= 4 and t.isascii():
            for v in vocab:
                if v.isascii() and len(v) >= 4 and abs(len(v) - len(t)) <= 2 and SequenceMatcher(None, t, v).ratio() >= 0.86:
                    return True
    return False


_SKIP_PHRASES = [
    "dont know", "don't know", "not sure", "no idea", "dunno", "unknown", "mahiti nahi", "mahit nahi", "mahiti nai", "pata nahi", "pata nai", "pata nhi", "pta nahi",
    "pta nhi", "nahi pata", "nhi pata", "maloom nahi", "malum nahi", "maloom nhi", "nahi maloom", "idea nahi", "thauk nahi", "thaук nahi", "kalpana nahi",
    "माहित नाही", "माहीत नाही", "माहिती नाही", "मला माहित नाही", "ठाऊक नाही", "ठाउक नाही", "कल्पना नाही", "आयडिया नाही",
    "पता नहीं", "पता नही", "पता नाही", "नहीं पता", "नही पता", "मालूम नहीं", "मालुम नहीं", "नहीं मालूम", "पत्ता नहीं", "आइडिया नहीं",
]


def skip_answer(text: str) -> bool:
    t = normalize_text(text)
    return any(normalize_text(x) in t for x in _SKIP_PHRASES)


def is_cancel(text: str) -> bool:
    t = normalize_text(text)
    return any(x in t for x in ["cancel", "रद्द", "सौदा नको", "deal nako", "cancel karo", "nako deal", "रद्द करो", "रद्द करा", "सौदा नहीं चाहिए", "deal cancel"])


_INCREASE_TOKENS = {"increase", "higher", "more", "badhao", "badhaye", "badhana", "badhav", "vadhva", "vadhav", "vadhava", "zyada", "jyada", "jasta", "jast",
                    "वाढवा", "वाढव", "वाढवून", "बढ़ाओ", "बढाओ", "बढ़ाइए", "बढ़ाएं", "ज्यादा", "जादा", "जास्त", "अधिक", "ऊपर"}
_DECREASE_TOKENS = {"decrease", "lower", "less", "reduce", "kam", "kami", "ghata", "ghatava", "ghatao", "कम", "कमी", "घटवा", "घटा", "घटाओ", "घटाइए", "खाली", "नीचे"}


def is_increase(text: str) -> bool:
    return _tok_in(_toks(text), _INCREASE_TOKENS)


def is_decrease(text: str) -> bool:
    return _tok_in(_toks(text), _DECREASE_TOKENS)


def is_negotiate(text: str) -> bool:
    t = normalize_text(text)
    return (any(x in t for x in ["negotiate", "counter", "vadha", "vadhva", "vadhav", "jasta", "zyada", "more price", "increase", "भाव वाढवा", "जास्त भाव", "वाढवा", "बोलणी",
                                 "बात करो", "बातचीत", "bol ni", "bolni", "bat karo", "mol bhav", "मोलभाव", "भाव बढ़ा", "ज्यादा भाव"])
            or is_increase(text))


_ACCEPT_POSITIVE = {"ho", "hoy", "haan", "haa", "ha", "haanji", "hanji", "haji", "yes", "yeah", "yep", "ok", "okay", "okey", "okk", "okkk", "accept", "accepted", "agree", "agreed",
                    "barobar", "chalel", "chalega", "chalo", "theek", "thik", "tik", "pakka", "lock", "locked", "confirm", "confirmed", "manzoor", "manjur", "kabul", "sahi",
                    "done", "kardo", "kara", "karo", "चालेल", "चलेगा", "चलो", "हो", "होय", "हां", "हाँ", "हा", "हाजी", "मान्य", "मंजूर", "मंज़ूर", "मनज़ूर", "कबूल", "पक्का",
                    "ठीक", "बरोबर", "सही", "करा", "करो", "कर", "लॉक", "लोक", "कन्फर्म", "ओके", "ओके।"}
_ACCEPT_NEGATIVE = {"nahi", "nahin", "nhi", "nai", "no", "not", "mat", "naka", "nako", "naahi", "नाही", "नहीं", "नही", "नको", "नका", "मत", "नकोच"}
_ACCEPT_QUALIFIERS = {"pan", "but", "lekin", "magar", "par", "पण", "लेकिन", "मगर", "पर", "जास्त", "वाढवा", "थोडे", "थोड़ा", "ज्यादा", "zyada", "jasta", "more", "increase"}


def is_accept(text: str) -> bool:
    tokens = _toks(text)
    token_set = set(tokens)
    return (_tok_in(tokens, _ACCEPT_POSITIVE) and not (token_set & _ACCEPT_NEGATIVE) and not (token_set & _ACCEPT_QUALIFIERS) and len(tokens) <= 6)


_REJECT_PHRASES = ["reject", "rejected", "not accept", "dont accept", "don't accept", "nahi chalega", "nahin chalega", "nahi manunga", "nahi manzoor", "manzoor nahi",
                   "manjur nahi", "nakar", "nakara", "nakarla", "naamanjur", "namanjur", "manya nahi", "nahi chalel", "naka chalel", "inkar", "इनकार", "अस्वीकार", "नाकार",
                   "नाकारा", "नामंजूर", "नामंज़ूर", "मंजूर नहीं", "मंज़ूर नहीं", "मान्य नाही", "नहीं चलेगा", "नाही चालेल", "नहीं मानूंगा", "नहीं मानूँगा", "नको हा भाव", "ये भाव नहीं"]


def is_reject(text: str) -> bool:
    return _phrase_in(normalize_text(text), _REJECT_PHRASES)


def is_send_counter(text: str) -> bool:
    t = normalize_text(text)
    return any(x in t for x in ["send", "bhej", "bhejo", "pathva", "pathav", "पाठवा", "पाठव", "भेज", "भेजो", "भेजिए"])


_LOCK_TOKENS = {"lock", "locked", "लॉक", "लोक", "lok", "final", "फाइनल", "confirm", "कन्फर्म", "pakka", "पक्का"}


def is_lock_confirm(text: str) -> bool:
    return _tok_in(_toks(text), _LOCK_TOKENS)


_SAME_REF_TOKENS = {"yahi", "yehi", "yahee", "vahi", "wahi", "wohi", "isi", "same", "यही", "यहीं", "वही", "इसी", "हाच", "हेच", "तोच", "हीच", "hach", "hech", "toch"}
_SAME_REF_PHRASES = ["yahi wala", "yahi wali", "यही वाला", "यही वाली", "वही वाला", "हाच वाला", "हाच भाव", "same price", "same as reference", "isi bhav", "इसी भाव"]
_REFERENCE_PHRASES = ["mandi price", "mandi bhav", "mandi rate", "reference price", "market price", "मंडी भाव", "मंडी का भाव", "मंडी रेट", "मंडीचा भाव", "मंडी दर", "संदर्भ भाव", "संदर्भ दर", "संदर्भ"]
_BUYER_WORDS = {"buyer", "kharidar", "kharedidar", "khareedar", "vyapari", "vyapaari", "trader", "party", "aadhatiya", "खरीदार", "खरेदीदार", "व्यापारी", "आडतिया", "offer", "ऑफर", "quote"}
_NO_OFFER_PHRASES = ["no offer", "offer nahi", "koi offer nahi", "ऑफर नहीं", "ऑफर नाही", "कोई ऑफर नहीं", "भाव नहीं मिला", "भाव नाही मिळाला", "abhi nahi", "अभी नहीं", "अजून नाही", "kuch nahi mila"]


def is_same_as_reference(text: str) -> bool:
    tokens = _toks(text)
    return len(tokens) <= 7 and (_phrase_in(normalize_text(text), _SAME_REF_PHRASES) or _tok_in(tokens, _SAME_REF_TOKENS))


def _says_reference(text: str) -> bool:
    return _phrase_in(normalize_text(text), _REFERENCE_PHRASES)


def _says_buyer_offer(text: str) -> bool:
    return _tok_in(_toks(text), _BUYER_WORDS)


def is_no_offer(text: str) -> bool:
    n = normalize_text(text)
    return _phrase_in(n, _NO_OFFER_PHRASES) or n in {"nahi", "nahin", "nhi", "no", "नहीं", "नही", "नाही", "नको"}

_NO_SEND = [
    "offer नको", "ऑफर नको", "offer नका", "पाठवू नका", "पाठवु नका",
    "तयार करायचा नाही", "offer तयार करायचा नाही",
    "offer मत", "ऑफर मत", "मत भेज", "मत बना",
    "do not send", "dont send", "don't send",
    "do not create", "dont create", "don't create",
    "just information", "just info", "only information", "just an idea",
    "सिर्फ जानकारी", "सिर्फ़ जानकारी", "फक्त अंदाज", "फक्त माहिती",
]

_HOLD = [
    "wait", "hold on", "hold", "let me think",
    "थांबा", "मला विचार करायचा आहे",
    "मला आधी विचार करायचा आहे",
    "आधी विचार करायचा आहे",
    "अजून विचार करू द्या",
    "रुको", "सोचना है", "ruko",
]


def no_send_kind(text: str):
    raw = str(text or "").lower()
    n = normalize_text(text)

    explicit_hold = (
        "मला आधी विचार करायचा आहे" in raw
        or "आधी विचार करायचा आहे" in raw
        or "अजून विचार करू द्या" in raw
        or "let me think" in raw
        or "hold on" in raw
        or _phrase_in(n, _HOLD)
    )

    if explicit_hold:
        return "hold"

    if _phrase_in(n, _NO_SEND):
        return "no_send"
        return None

    return None
def is_no_buyer_offer(text: str, waiting_for: Optional[str]) -> bool:
    return (
        waiting_for in {"buyer_offer", "buyer_offer_clarify"}
        and not no_send_kind(text)
        and is_no_offer(text)
    )

def _is_question(text: str) -> bool:
    tokens = normalize_text(text).split()
    return "?" in text or "？" in text or bool(tokens and tokens[0] in _QUESTION_TOKENS)


_REFRESH_PHRASES = ["refresh", "retry", "check again", "पुन्हा तपास", "भाव दाखवा", "दर दाखवा", "फिर से चेक", "फिर से देख", "punha tapas"]


def _wants_price_refresh(text: str) -> bool:
    t = normalize_text(text)
    return any(p in t for p in _REFRESH_PHRASES)


def commodity_label(s: dict[str, Any], lang: str) -> str:
    if not s.get("commodity_id"):
        return ""
    item = COMMODITIES[s["commodity_id"]]
    if lang == "hinglish":
        return _HINGLISH_CROP.get(s["commodity_id"], item["name"])
    lang = ui_lang(lang)
    return item["hi"] if lang == "hi" else item["mr"] if lang == "mr" else item["name"]
_QUALITY_LABELS = {
    "mr": {"moisture": "ओलावा", "cleanliness": "स्वच्छता", "grain_condition": "दाण्यांची स्थिती", "seed_condition": "बियाण्यांची स्थिती", "product_form": "मालाचा प्रकार", "size": "आकार", "firmness": "घट्टपणा", "damage": "नुकसान", "trash": "कचरा"},
    "hi": {"moisture": "नमी", "cleanliness": "सफाई", "grain_condition": "दाने की स्थिति", "seed_condition": "बीज की स्थिति", "product_form": "माल का प्रकार", "size": "आकार", "firmness": "मजबूती", "damage": "नुकसान", "trash": "कचरा"},
    "en": {"moisture": "moisture", "cleanliness": "cleanliness", "grain_condition": "grain condition", "seed_condition": "seed condition", "product_form": "product form", "size": "size", "firmness": "firmness", "damage": "damage", "trash": "trash"},
    "hn": {"moisture": "nami (moisture)", "cleanliness": "safai", "grain_condition": "daane ki condition", "seed_condition": "daane ki condition", "product_form": "maal ka prakar", "size": "size", "firmness": "sakhti", "damage": "nuksaan", "trash": "kachra"},
}


def _quality_summary(s: dict[str, Any], lang: str) -> str:
    u = "hn" if lang == "hinglish" else ui_lang(lang)
    parts: list[str] = []
    for key, value in (s.get("quality") or {}).items():
        if isinstance(value, dict):
            if value.get("reported_percent") is not None:
                shown = f"{value['reported_percent']:g}%"
            elif value.get("description") == "dry_self_reported":
                shown = {"mr": "सुका असल्याचे शेतकऱ्याने सांगितले", "hi": "किसान ने सूखा बताया", "en": "farmer reported dry", "hn": "kisan ne sukha bataya"}[u]
            elif value.get("description") == "moist_self_reported":
                shown = {"mr": "ओलसर असल्याचे शेतकऱ्याने सांगितले", "hi": "किसान ने नम बताया", "en": "farmer reported moist", "hn": "kisan ne geela bataya"}[u]
            else:
                shown = str(value.get("answer") or ("not provided" if u == "en" else "jaankari nahi di" if u == "hn" else "माहिती दिलेली नाही"))
        else:
            shown = str(value)
        parts.append(f"{_QUALITY_LABELS[u].get(key, key)}: {shown}")
    return "; ".join(parts) if parts else ("not provided" if u == "en" else "jaankari nahi di" if u == "hn" else "माहिती दिलेली नाही")

configure_offer_helpers(
    skip_answer_fn=skip_answer,
    is_no_offer_fn=is_no_buyer_offer,
    says_buyer_offer_fn=_says_buyer_offer,
    says_reference_fn=_says_reference,
    same_as_reference_fn=is_same_as_reference,
    commodity_label_fn=commodity_label,
    quality_summary_fn=_quality_summary,
)

_HINGLISH_CROP = {"soybean": "soybean", "wheat": "gehun", "jowar": "jowar", "moong": "moong", "urad": "urad", "maize": "makka", "onion": "pyaaz",
                  "bajra": "bajra", "chana": "chana", "tur": "tur", "cotton": "kapas", "paddy_rice": "dhan/chawal"}
_HINGLISH_Q = {
    "moisture": "{crop} mein nami (moisture) kitni hai? Percent pata na ho to bataiye maal sukha hai ya geela.",
    "cleanliness": "{crop} mein mitti, kachra ya doosri milawat hai kya?",
    "grain_condition": "Daane bhare hue aur ek jaise hain? Toote, kide lage ya kharab daane hain kya?",
    "seed_condition": "Daane bhare aur ek jaise hain? Toote, daagdaar ya kide lage daane hain kya?",
    "size": "{crop} chhota, medium ya bada hai? Size lagbhag ek jaisa hai kya?",
    "firmness": "{crop} sakht aur sukha hai? Naram ya geela maal hai kya?",
    "damage": "Sade hue, phate hue, ankur nikle ya daag wale {crop} hain kya?",
    "trash": "{crop} mein patte, kachra, dhool ya daag kitne hain?",
}
_HINGLISH_PRODUCT_FORM = {"urad": "Yeh poora (whole) urad hai ya dal / toota hua urad?", "tur": "Yeh poora (whole) tur hai ya processed tur dal?",
                          "cotton": "Yeh khet ka kaccha kapas hai ya ginning kiya hua cotton?"}


# Commodity-specific quality questions in Roman-script Hinglish (the catalogue's 5th tuple element is Devanagari
# Marathi + English words and must not be shown to a Hinglish speaker). Keys match COMMODITIES[...]["questions"].
_HINGLISH_COMMODITY_Q: dict[str, dict[str, str]] = {
    "soybean": {"moisture": "Soybean mein nami kitni hai? Napa hua percent pata na ho to bataiye maal sukha hai ya geela.",
                "cleanliness": "Maal mein mitti, kachra ya doosri milawat hai kya?",
                "seed_condition": "Daane bhare hue aur ek jaise hain, ya toote/daagdaar daane bhi hain?"},
    "wheat": {"moisture": "Gehun mein nami kitni hai? Napa hua percent pata na ho to bataiye sukha hai ya geela.",
              "cleanliness": "Gehun saaf hai? Mitti, kachra ya doosre anaaj mile hain kya?",
              "grain_condition": "Daane bhare aur ek jaise hain? Keede lage ya toote daane hain kya?"},
    "jowar": {"moisture": "Jowar mein nami kitni hai? Sukhi hai ya geeli?",
              "cleanliness": "Daano mein mitti, kachra ya milawat hai kya?",
              "grain_condition": "Daane ek jaise hain? Toote, adhpake ya keede lage daane hain kya?"},
    "moong": {"moisture": "Moong mein nami kitni hai? Sukhi hai ya geeli?",
              "cleanliness": "Moong mein mitti, kachra ya doosra anaaj mila hai kya?",
              "seed_condition": "Daane hare aur ek jaise hain? Toote, daagdaar ya keede lage hain kya?"},
    "urad": {"moisture": "Urad mein nami kitni hai? Sukhi hai ya geeli?",
             "cleanliness": "Mitti, kachra, toote ya keede lage daane kitne dikhte hain?"},
    "maize": {"moisture": "Makka mein nami kitni hai? Napa hua percent pata na ho to bataiye sukhi hai ya geeli.",
              "cleanliness": "Daano mein dhool, kachra ya milawat hai kya?",
              "grain_condition": "Daane toote, kaale ya fafoondi lage hue hain kya?"},
    "onion": {"size": "Pyaaz chhota, medium ya bada hai? Size lagbhag ek jaisa hai kya?",
              "firmness": "Pyaaz sakht aur sukha hai? Naram ya geele pyaaz hain kya?",
              "damage": "Sade hue, phate hue, ankur nikle ya daag wale pyaaz hain kya?"},
    "bajra": {"moisture": "Bajra mein nami kitni hai? Sukha hai ya geela?",
              "cleanliness": "Bajra mein mitti, kachra ya doosra anaaj mila hai kya?",
              "grain_condition": "Daane ek jaise hain? Keede lage ya adhpake daane hain kya?"},
    "chana": {"moisture": "Chana mein nami kitni hai? Sukha hai ya geela?",
              "cleanliness": "Chana mein mitti, patthar ya milawat hai kya?",
              "seed_condition": "Daane toote, daagdaar ya keede lage hue hain kya?"},
    "tur": {"moisture": "Tur mein nami kitni hai? Sukhi hai ya geeli?",
            "cleanliness": "Daano mein mitti, doosra anaaj, toote ya keede lage daane hain kya?"},
    "cotton": {"moisture": "Kapas mein nami hai kya? Maal sukha hai ya damp?",
               "trash": "Kapas mein patte, kachra, dhool ya daag kitne hain?"},
    "paddy_rice": {"moisture": "Dhan/chawal mein nami kitni hai? Napa hua percent pata na ho to bataiye sukha hai ya geela.",
                   "cleanliness": "Maal mein mitti, kachra ya doosri variety ke daane mile hain kya?",
                   "grain_condition": "Daane toote, adhpake, daagdaar ya keede lage hue hain kya?"},
}


def _hinglish_quality_question(s: dict[str, Any], key: str) -> str:
    cid = s.get("commodity_id") or ""
    if key == "product_form" and cid in _HINGLISH_PRODUCT_FORM:
        return _HINGLISH_PRODUCT_FORM[cid]
    specific = _HINGLISH_COMMODITY_Q.get(cid, {}).get(key)
    if specific:
        return specific
    crop = _HINGLISH_CROP.get(cid, COMMODITIES.get(cid, {}).get("name", ""))
    return _HINGLISH_Q.get(key, "{crop} ke baare mein thoda aur bataiye.").format(crop=crop[:1].upper() + crop[1:])





def _store_history(s: dict[str, Any], role: str, content: str, private: bool = False) -> None:
    entry = {"role": role, "content": content, "at": datetime.now(timezone.utc).isoformat()}
    if private:
        entry["private"] = True  # never forwarded to the AI assistant (farmer price answers / private replies)
    s.setdefault("history", []).append(entry)
    s["history"] = s["history"][-SESSION_HISTORY_LIMIT:]




def _invalidate_price(s: dict[str, Any]) -> None:
    """Drop a cached benchmark when the inputs it was built from change (before any offer is active)."""
    if _offer_active(s) or s.get("deal_status") in {"LOCKED", "LOCKED_DEMO"}:
        return
    s["price_analysis"] = None
    s["price_status"] = "not_requested"


def _set_district(s: dict[str, Any], district: Optional[str]) -> None:
    district = canonical_district(district)
    if district and district != s.get("district"):
        changed = bool(s.get("district"))
        s["district"] = district
        if changed:
            s["market"], s["market_skipped"] = None, False  # the old mandi belongs to the old district
            s["market_retry"] = 0
            _invalidate_price(s)


def _set_market(s: dict[str, Any], market: Optional[str]) -> None:
    if market and _is_any_market(market):  # "Any market" = whole district, never a literal APMC name
        s["market"], s["market_skipped"] = None, True
        s["market_retry"] = 0
        _invalidate_price(s)
        return
    if market and market != s.get("market"):
        s["market"], s["market_skipped"] = market, False
        s["market_retry"] = 0
        _invalidate_price(s)

def _is_buyer_quote_statement(text: str) -> bool:
    raw = str(text or "").lower()

    has_buyer = any(x in raw for x in (
        "buyer", "खरेदीदार", "खरीदार", "व्यापारी"
    ))
    has_quote = any(x in raw for x in (
        "सांगितले", "सांगितला", "सांगितलं",
        "दिले", "दिला", "मिळाले",
        "said", "told", "quoted", "offered",
        "sangitla", "sangitle"
    ))

    return has_buyer and has_quote
def _extract_waiting_answer(s: dict[str, Any], text: str) -> None:
    waiting = s.get("waiting_for")
    if not waiting:
        return
    if waiting == "variety" and s.get("commodity_id") and not s.get("variety"):
        detected = match_variety(s["commodity_id"], text)
        norm_tokens = set(normalize_text(text).split())
        if detected:
            s["variety"] = detected
        elif skip_answer(text):
            s["variety"] = "Not sure"
        elif norm_tokens & _OTHER_VARIETY_TOKENS:
            s["variety"] = "Other/Not sure"
        elif not _is_question(text) and not re.search(r"\d", text) and 0 < len(text.split()) <= 4:
            s["variety"] = text.strip()[:80]  # a short free-text local variety name
        if s.get("variety"):
            cid = s["commodity_id"]
            chosen = str(s["variety"]).lower()
            raw = normalize_text(text)
            if cid == "cotton":
                if "raw kapas" in chosen or "कच्चा कापूस" in raw or "कच्चा कपास" in raw:
                    s["product_form"] = "Raw Kapas"
                elif "ginned" in chosen or "lint" in chosen or "jinning" in raw or "जिनिंग" in raw:
                    s["product_form"] = "Ginned Cotton/Lint"
            elif cid == "tur":
                if "dal" in chosen or "दाल" in raw or "डाळ" in raw:
                    s["product_form"] = "Processed Tur Dal"
                elif "whole" in chosen or "अख्खा" in raw or "साबुत" in raw:
                    s["product_form"] = "Whole Tur"
            elif cid == "urad":
                if "dal" in chosen or "दाल" in raw or "डाळ" in raw or "split" in chosen:
                    s["product_form"] = "Split Urad Dal"
                elif "whole" in chosen or "अख्खा" in raw or "साबुत" in raw:
                    s["product_form"] = "Whole Urad"
            if s.get("product_form"):
                _invalidate_price(s)
    elif waiting == "product_form" and s.get("commodity_id") == "paddy_rice" and not s.get("product_form"):
        t = normalize_text(text)
        if any(w in t for w in ["processed", "milled", "सोललेला", "तयार"]) or (any(w in t for w in ["rice", "chawal", "tandul", "चावल", "तांदूळ", "तांदुळ"]) and not any(w in t for w in ["paddy", "dhan", "धान", "भात", "raw", "कच्चा"])):
            s["product_form"] = "Processed rice"
        elif any(w in t for w in ["paddy", "dhan", "धान", "भात", "raw", "कच्चा", "शेतातील", "साळ"]):
            s["product_form"] = "Raw paddy"
        elif skip_answer(text):
            s["product_form"] = "Not sure"
    elif waiting == "quantity" and s.get("quantity_quintals") is None:
        qty = parse_quantity(text)
        if qty is None:
            qty = parse_bare_quantity(text)  # "दोन" / "two" / "50" alone = quintals, because quantity was just asked
        if qty and 0 < qty <= 100000:
            s["quantity_quintals"] = qty
    elif waiting == "district" and not s.get("district"):
        found = find_district(text)
        if found:
            _set_district(s, found)
        else:
            norm = normalize_text(text)
            # A district we do not list is accepted as typed (short, alphabetic, not a question).
            if norm and not _is_question(text) and not skip_answer(text) and not re.search(r"\d", norm) and len(norm.split()) <= 3:
                _set_district(s, text.strip())
    elif waiting == "market" and not s.get("market") and not s.get("market_skipped"):
        tokens = set(normalize_text(text).split())
        found = find_market(text)
        if found:
            _set_market(s, found)
        elif _is_any_market(text) or skip_answer(text) or tokens & _MARKET_SKIP_TOKENS:
            s["market"], s["market_skipped"] = None, True
            s["market_retry"] = 0
            _invalidate_price(s)
        elif (normalize_text(text) and not _is_question(text) and not re.search(r"\d", text)
              and detect_faq(text) is None):
            # Not a recognised market and not a question/price/FAQ: never store it as a market name.
            # First time -> ask again (market_clarify); second time -> treat the market as optional and move on.
            s["market_retry"] = int(s.get("market_retry") or 0) + 1
            if s["market_retry"] >= 2:
                s["market"], s["market_skipped"] = None, True
                s["market_retry"] = 0
                _invalidate_price(s)
    elif waiting.startswith("quality:"):
        key = waiting.split(":", 1)[1]
        if key == "product_form":
            if not _is_question(text):
                s["product_form"] = "Not sure" if skip_answer(text) else text.strip()[:100]
                s.setdefault("quality", {})[key] = {"answer": s["product_form"], "source": "farmer_self_reported"}
                _invalidate_price(s)
        elif key == "moisture":
            parsed = parse_moisture_answer(text)
            if not (parsed.get("description") == "self_reported" and _is_question(text)):
                s.setdefault("quality", {})[key] = parsed
        elif skip_answer(text):
            s.setdefault("quality", {})[key] = {"unknown": True, "answer": "Not provided"}
        elif not _is_question(text):
            s.setdefault("quality", {})[key] = {"answer": text.strip()[:200], "source": "farmer_self_reported"}
    elif waiting == "farmer_target":
        price = parse_price(text)

        # Keep a buyer's quoted price separate from the farmer's target.
        if price and 100 <= price <= 1_000_000 and _is_buyer_quote_statement(text):
            s["reported_buyer_quote"] = {
                "price_per_quintal": float(price),
                "quantity_quintals": s.get("quantity_quintals"),
                "source": "farmer_reported_buyer_offer",
                "verified": False,
                "reported_at": datetime.now(timezone.utc).isoformat(),
            }
            return

        if price is None and is_same_as_reference(text):
            ref = (s.get("price_analysis") or {}).get("modal_reference")
            price = float(ref) if ref else None

        desired = price if price and 100 <= price <= 1_000_000 else None
        s["farmer_target_price"] = desired
        s["farmer_desired_price"] = desired
        s["waiting_for"] = "farmer_minimum"
    elif waiting == "farmer_minimum":
        price = parse_price(text)
        s["farmer_min_price"] = price if price and 100 <= price <= 1_000_000 else None
        s["waiting_for"] = "buyer_offer"
    elif waiting in {"buyer_offer", "buyer_offer_clarify"}:
        price = parse_price(text)
        if price and 100 <= price <= 1_000_000:
            s["offer_version"] = int(s.get("offer_version", 0)) + 1  # lets the buyer confirm this exact version
            s["buyer_offer"] = {
                "price_per_quintal": price,
                "source": "farmer_reported_buyer_offer",
                "buyer_confirmed": False,
                "active": True,
                "reported_at": datetime.now(timezone.utc).isoformat(),
            }
            s["farmer_confirmed"] = False
            s["buyer_confirmed"] = False
            s["offer_expires_at"] = (datetime.now(timezone.utc) + timedelta(minutes=DEFAULT_OFFER_VALID_MINUTES)).isoformat()
            s["counter_price"] = None
            s["buyer_offer"]["verified"] = False
            s["reported_buyer_quote"] = dict(s["buyer_offer"])  # preserved separately from any later counter
            s["original_buyer_offer"] = None
            s["buyer_offer_status"] = "farmer_reported"
            s["waiting_for"] = "buyer_offer"
    elif waiting == "farmer_counter":
        price = parse_price(text)
        if price and (is_increase(text) or is_decrease(text)):
            ref = float(((s.get("buyer_offer") or {}).get("price_per_quintal")) or (s.get("price_analysis") or {}).get("modal_reference") or 0)
            if ref and not (0.4 * ref <= price <= 2.5 * ref):
                price = None  # looks like a relative amount ("200 more"), not a price per quintal: ask instead of inventing a counter
        s["counter_price"] = price if price and 100 <= price <= 1_000_000 else None  # never reuse a stale counter


def _update_entities(s: dict[str, Any], text: str, lang: str, market_form: Optional[str] = None,
                     district_form: Optional[str] = None) -> Optional[list[str]]:
    """Extract facts from the utterance. Returns ambiguity candidates when relevant."""
    waiting = s.get("waiting_for")
    # While an offer is active the transaction terms are frozen: crop, variety, quantity, district and
    # market cannot silently change. To change them the farmer must counter or cancel (new offer needed).
    frozen = _offer_active(s)
    commodity_id, ambiguous = (None, []) if frozen else match_commodity(text)
    if commodity_id and not s.get("commodity_id"):
        s["commodity_id"] = commodity_id
        s["commodity"] = COMMODITIES[commodity_id]["name"]
    elif commodity_id and s.get("commodity_id") and commodity_id != s["commodity_id"]:
        # A crop switch is accepted only before an offer exists.
        if not _offer_active(s) and s.get("deal_status") not in {"LOCKED", "LOCKED_DEMO"}:
            s["commodity_id"] = commodity_id
            s["commodity"] = COMMODITIES[commodity_id]["name"]
            s["variety"] = None
            s["product_form"] = None
            s["quality"] = {}
            s["price_analysis"] = None
            s["price_status"] = "not_requested"

    _extract_waiting_answer(s, text)
    if frozen:
        return None

    # Variety is auto-detected only while it is still unknown (never overwritten by later quality answers).
    if s.get("commodity_id") and not s.get("variety") and waiting in {"commodity", "variety", None}:
        detected_variety = match_variety(s["commodity_id"], text)
        if detected_variety:
            s["variety"] = detected_variety

    # An explicit "number + unit" replaces the saved quantity (a correction). Kilograms are ignored while a quality
    # question is open ("10 kilo kachra") so a quality answer can never overwrite the quantity.
    qty = parse_quantity(text, allow_kg=not str(waiting or "").startswith("quality:"))
    if qty is not None:
        s["quantity_quintals"] = qty

    # District and market are separate fields. District can be volunteered at any time while unknown.
    if district_form:
        _set_district(s, district_form)
    elif waiting != "district" and not s.get("district"):
        _set_district(s, find_district(text))

    if market_form:
        _set_market(s, market_form.strip()[:100])
    elif waiting != "market" and not s.get("market") and any(w in normalize_text(text) for w in MARKET_WORDS):
        _set_market(s, find_market(text))

    # Product form may also appear before the explicit clarification question.
    if s.get("commodity_id") == "paddy_rice" and not s.get("product_form"):
        t = normalize_text(text)
        if any(w in t for w in ["paddy", "dhan", "धान", "भात", "raw paddy"]):
            s["product_form"] = "Raw paddy"
        elif any(w in t for w in ["processed rice", "chawal", "tandul", "चावल", "तांदूळ", "तांदुळ"]):
            s["product_form"] = "Processed rice"

    return ambiguous or None


def next_required_step(s: dict[str, Any]) -> Optional[str]:
    cid = s.get("commodity_id")
    if not cid:
        return "commodity"
    if cid == "paddy_rice" and not s.get("product_form"):
        return "product_form"
    if not s.get("variety"):
        return "variety"
    if not s.get("quantity_quintals"):
        return "quantity"
    if not s.get("district"):
        return "district"  # required for the district-filtered official price lookup
    if not s.get("market") and not s.get("market_skipped"):
        return "market"
    for key, *_ in COMMODITIES[cid]["questions"]:
        if key not in s.get("quality", {}):
            # product_form is already asked in its dedicated branch for tur/urad/cotton too.
            if key == "product_form" and s.get("product_form"):
                continue
            if key == "product_form" and cid not in {"tur", "urad", "cotton"}:
                continue
            return f"quality:{key}"
    return None


def make_question(s: dict[str, Any], step: str, lang: str) -> str:
    if step == "commodity":
        return ask_text(lang, "commodity")
    if step == "product_form":
        return ask_text(lang, "product_form")
    if step == "variety":
        item = COMMODITIES[s["commodity_id"]]
        return ask_text(lang, "variety", options=", ".join(item["varieties"]))
    if step == "quantity":
        return ask_text(lang, "quantity")
    if step == "district":
        return ask_text(lang, "district")
    if step == "market":
        if int(s.get("market_retry") or 0) >= 1:
            return ask_text(lang, "market_clarify", district=s.get("district") or "")
        return ask_text(lang, "market", district=s.get("district") or "")
    if step.startswith("quality:"):
        key = step.split(":", 1)[1]
        for qkey, _label, mr, hi, en in COMMODITIES[s["commodity_id"]]["questions"]:
            if qkey == key:
                if lang == "hinglish":
                    return ask_text(lang, "quality", question=_hinglish_quality_question(s, key))
                u = ui_lang(lang)
                return ask_text(lang, "quality", question=mr if u == "mr" else hi if u == "hi" else en)
    return ask_text(lang, "commodity")


def is_price_ready(s: dict[str, Any]) -> bool:
    return next_required_step(s) is None


def _commodity_for_price_sentence(s: dict[str, Any], lang: str) -> str:
    if ui_lang(lang) == "mr":
        forms = {
            "soybean": "सोयाबीनसाठी", "wheat": "गव्हासाठी", "jowar": "ज्वारीसाठी", "moong": "मुगासाठी",
            "urad": "उडदासाठी", "maize": "मक्यासाठी", "onion": "कांद्यासाठी", "bajra": "बाजरीसाठी",
            "chana": "हरभऱ्यासाठी", "tur": "तुरीसाठी", "cotton": "कापसासाठी", "paddy_rice": "भात/तांदळासाठी",
        }
        return forms.get(s.get("commodity_id"), f"{commodity_label(s, lang)}साठी")
    return commodity_label(s, lang)


def _price_detail_text(pa: dict[str, Any], lang: str) -> str:
    """Localised price facts. Actual market modal, calculated median and fallback record are always worded
    differently; a median or another variety's modal is never called the modal of the requested variety."""
    u = "hn" if lang == "hinglish" else ui_lang(lang)
    f = lambda v: f"₹{float(v):,.0f}"
    rt = pa.get("reference_type")
    lo, hi_ = pa.get("lowest_market_min"), pa.get("highest_market_max")
    words = {"en": ("minimum", "maximum"), "hi": ("न्यूनतम", "अधिकतम"), "mr": ("किमान", "कमाल"), "hn": ("minimum", "maximum")}[u]

    def mm(low: Any, high: Any) -> str:
        bits = ([f"{words[0]} {f(low)}"] if low is not None else []) + ([f"{words[1]} {f(high)}"] if high is not None else [])
        return (", " + ", ".join(bits)) if bits else ""

    if rt == "market_actual":
        m_ = f(pa["official_market_modal"]) + mm(lo, hi_)
        return {"en": f"the actual reported modal price is {m_} per quintal. ", "hi": f"वास्तविक दर्ज मोडल भाव {m_} प्रति क्विंटल है। ",
                "mr": f"प्रत्यक्ष नोंदलेला मोडल दर {m_} प्रति क्विंटल आहे. ", "hn": f"actual reported modal bhav {m_} prati quintal hai. "}[u]
    if rt == "fallback_record":
        fr = pa.get("fallback_record") or {}
        mk, vr = fr.get("market") or "-", fr.get("variety") or "-"
        m_ = f(fr.get("modal_price")) + mm(fr.get("min_price"), fr.get("max_price"))
        return {"en": f"the only available record is a fallback ({mk}, variety {vr}) reporting a modal of {m_} per quintal; this is NOT the modal price of your requested variety/market. ",
                "hi": f"केवल एक विकल्प (fallback) रिकॉर्ड मिला ({mk}, किस्म {vr}) जिसमें मोडल {m_} प्रति क्विंटल दर्ज है; यह आपकी बताई किस्म/मंडी का मोडल भाव नहीं है। ",
                "mr": f"फक्त एक पर्यायी (fallback) नोंद मिळाली ({mk}, वाण {vr}); त्यात मोडल {m_} प्रति क्विंटल आहे; हा तुम्ही सांगितलेल्या वाण/मंडीचा मोडल दर नाही. ",
                "hn": f"sirf ek fallback record mila ({mk}, variety {vr}) jisme modal {m_} prati quintal hai; yeh aapki bataayi variety/mandi ka modal bhav nahi hai. "}[u]
    n, k = pa.get("market_count") or 0, pa.get("varieties_combined") or 1
    med, a, b = pa.get("calculated_median_modal"), pa.get("modal_spread_low"), pa.get("modal_spread_high")
    if n > 1:
        basis = {"en": f"{n} markets", "hi": f"{n} मंडियों", "mr": f"{n} मंडी", "hn": f"{n} mandiyon"}[u]
    else:
        basis = {"en": f"{k} varieties in this market", "hi": f"इस मंडी की {k} किस्मों", "mr": f"या मंडीतील {k} वाणांच्या", "hn": f"is mandi ki {k} varieties"}[u]
    en = f"based on {basis}, the calculated median of their modal prices is {f(med)} (a calculated figure, not an official mandi modal)"
    hi = f"{basis} के आधार पर उनके मोडल भावों का गणना किया हुआ मध्यमान {f(med)} है (यह गणना है, आधिकारिक मंडी मोडल नहीं)"
    mr = f"{basis} आधारे त्यांच्या मोडल दरांचा काढलेला मध्यक {f(med)} आहे (हे गणन आहे, अधिकृत मंडी मोडल नाही)"
    hn = f"{basis} ke aadhaar par unke modal bhavon ka calculated median {f(med)} hai (yeh calculation hai, official mandi modal nahi)"
    if lo is not None:
        en += f"; lowest reported market minimum {f(lo)}"; hi += f"; सबसे कम दर्ज मंडी न्यूनतम {f(lo)}"; mr += f"; सर्वात कमी नोंदलेला मंडी किमान {f(lo)}"; hn += f"; sabse kam reported market minimum {f(lo)}"
    if hi_ is not None:
        en += f"; highest reported market maximum {f(hi_)}"; hi += f"; सबसे ज्यादा दर्ज मंडी अधिकतम {f(hi_)}"; mr += f"; सर्वाधिक नोंदलेला मंडी कमाल {f(hi_)}"; hn += f"; sabse zyada reported market maximum {f(hi_)}"
    en += f"; modal spread {f(a)} to {f(b)} per quintal. "
    hi += f"; मोडल भावों का दायरा {f(a)} से {f(b)} प्रति क्विंटल है। "
    mr += f"; मोडल दरांची व्याप्ती {f(a)} ते {f(b)} प्रति क्विंटल आहे. "
    hn += f"; modal bhavon ka spread {f(a)} se {f(b)} prati quintal hai. "
    return {"en": en, "hi": hi, "mr": mr, "hn": hn}[u]


def _build_price_guidance(s: dict[str, Any], pa: dict[str, Any], lang: str) -> str:
    if not pa.get("available"):
        return ask_text(lang, "price_unavailable")
    as_of = pa.get("as_of_display") or pa.get("as_of") or "unknown"
    # Variety / market fallback is disclosed for fresh AND stale prices.
    notes: list[str] = []
    if pa.get("variety_match") is False:
        notes.append(ask_text(lang, "variety_note"))
    if pa.get("market_matched") is False:
        notes.append(ask_text(lang, "market_note", market=pa.get("market_requested") or ""))
    if pa.get("stale"):
        stale_text = ask_text(lang, "price_stale", commodity=_commodity_for_price_sentence(s, lang), as_of=as_of,
                              modal=pa.get("modal_reference") or 0)
        return " ".join(notes + [stale_text])
    base = ask_text(
        lang, "price_ready", commodity=_commodity_for_price_sentence(s, lang), market_scope=pa.get("market_scope", DATA_GOV_STATE),
        as_of=as_of,
        price_detail=_price_detail_text(pa, lang),
    )
    return " ".join(notes + [base])


_QUALITY_LABELS = {
    "mr": {"moisture": "ओलावा", "cleanliness": "स्वच्छता", "grain_condition": "दाण्यांची स्थिती", "seed_condition": "बियाण्यांची स्थिती", "product_form": "मालाचा प्रकार", "size": "आकार", "firmness": "घट्टपणा", "damage": "नुकसान", "trash": "कचरा"},
    "hi": {"moisture": "नमी", "cleanliness": "सफाई", "grain_condition": "दाने की स्थिति", "seed_condition": "बीज की स्थिति", "product_form": "माल का प्रकार", "size": "आकार", "firmness": "मजबूती", "damage": "नुकसान", "trash": "कचरा"},
    "en": {"moisture": "moisture", "cleanliness": "cleanliness", "grain_condition": "grain condition", "seed_condition": "seed condition", "product_form": "product form", "size": "size", "firmness": "firmness", "damage": "damage", "trash": "trash"},
    "hn": {"moisture": "nami (moisture)", "cleanliness": "safai", "grain_condition": "daane ki condition", "seed_condition": "daane ki condition", "product_form": "maal ka prakar", "size": "size", "firmness": "sakhti", "damage": "nuksaan", "trash": "kachra"},
}






def _has_explicit_sell_intent(text: str) -> bool:
    """Require a clear selling intent before a crop mention can rotate an existing transaction."""
    tokens = set(normalize_text(text).split())
    sell_tokens = {
        "sell", "selling", "bech", "bechna", "bechni", "bechunga", "bechungi",
        "vikaycha", "vikaychi", "vikayche", "vikayla", "viknar", "viknaray", "viknar aahe",
        "बेचना", "बेचनी", "बेचूंगा", "बेचूंगी", "बेचेंगे", "बेचूँगा", "बेचूँगी",
        "विकायचे", "विकायचा", "विकायची", "विकायला", "विकणार", "विकणार आहे",
    }
    if tokens & sell_tokens:
        return True
    normalized = normalize_text(text)
    sell_phrases = (
        "want to sell", "i will sell", "i am selling", "selling my", "sell my",
        "mala vikaycha aahe", "mala vikaychi aahe", "mala vikayche aahe",
        "mujhe bechna hai", "main bechna chahta", "main bechna chahti",
    )
    return any(phrase in normalized for phrase in sell_phrases)


def _new_commodity_request(s: dict[str, Any], text: str) -> Optional[str]:
    """Rotate only when the farmer starts selling a DIFFERENT crop, not when asking its price."""
    if not s.get("commodity_id"):
        return None
    if _is_pure_info(s, text):  # "how do I sell maize?" / "maize price?" is a question, not a new sale
        return None
    wf = s.get("waiting_for") or ""
    if wf.startswith("quality:") or wf == "variety":
        return None
    if not _has_explicit_sell_intent(text):
        return None
    new_cid, ambiguous = match_commodity(text)
    if not new_cid or ambiguous or new_cid == s["commodity_id"]:
        return None
    progressed = bool(s.get("variety") or s.get("quantity_quintals") or s.get("price_analysis")
                      or s.get("buyer_offer") or s.get("deal_status") != "GATHERING_DETAILS")
    return new_cid if progressed else None


def _rotated_session_id(old_id: str, commodity_id: str) -> str:
    return f"{old_id[:90]}-{commodity_id}-{uuid.uuid4().hex[:8]}"   # matches SESSION_ID_RE, always unique



# ---------------------------------------------------------------------------
# 6b. Selling intent, information questions and interruptions
# ---------------------------------------------------------------------------
# An information question (a mandi price, MSP, "what does modal price mean", ...) is answered WITHOUT touching the
# selling session: price lookups use a temporary query dict (kept in s["info_query"] only while it waits for a
# district / crop), `waiting_for` is never changed, and after the answer the pending selling question is asked again.

_INTAKE_WAITS = {"commodity", "product_form", "variety", "quantity", "district", "market"}
_PRICE_STATES = {"farmer_target", "farmer_minimum", "buyer_offer", "buyer_offer_clarify", "farmer_counter",
                 "counter_decision", "farmer_decision", "farmer_confirm", "farmer_final_confirm", "counter_confirm"}
_DECISION_STATES = {"farmer_counter", "counter_decision", "farmer_decision", "farmer_confirm",
                    "farmer_final_confirm", "counter_confirm"}
_FINISHED_DEALS = {"LOCKED", "LOCKED_DEMO", "CANCELLED"}

_SELL_EXTRA_TOKENS = {
    "sale", "bikri", "bikna", "vikri", "vikna", "bechne", "bechenge", "becho", "bechein", "bechta", "bechti", "becha",
    "vikto", "vikte", "viktoy", "vikayche", "vikaychay", "vikane", "विक्री", "विकणे", "विकण्यासाठी", "विकण्याचा", "विकण्याचे",
    "विकतो", "विकते", "विकायचंय", "विकायचं", "बेचने", "बेचता", "बेचती", "बेचूं", "बेचें", "बिक्री", "बेचकर",
}
_SELL_EXTRA_PHRASES = [
    "for sale", "sell karna", "sell kar", "sell karne", "sell karunga", "bechna chahta", "bechna chahti", "bechna chahte",
    "bechna hai", "bechne ke liye", "bechne wala", "vikaycha aahe", "vikayche aahe", "बेचने के लिए", "बेचना है", "बेचना चाहता",
    "विकायचा आहे", "विकायचे आहे", "विकण्यासाठी आहे",
]
_HAVE_PHRASES = [
    "i have", "ive got", "i ve got", "we have", "mere paas", "mere pass", "mere pas", "hamare paas", "hamare pass",
    "majhyakade", "majhya kade", "mazyakade", "mazya kade", "majyakade", "aamchyakade", "amchyakade",
    "माझ्याकडे", "माझ्या कडे", "माझ्याजवळ", "माझ्या जवळ", "आमच्याकडे", "मेरे पास", "हमारे पास",
]
_PRODUCE_WORDS = {"maal", "mal", "माल", "produce", "crop", "crops", "fasal", "fasl", "फसल", "पीक", "pik", "उपज", "शेतमाल",
                  "shetmal", "उत्पादन", "harvest", "stock"}
_HOWTO_SELL_PHRASES = [
    "how do i sell", "how to sell", "how can i sell", "how should i sell", "how do we sell", "selling process", "sell process",
    "process of selling", "kaise bechu", "kaise bechun", "kaise bechna", "kaise bechein", "kaise bechte", "sell kaise", "sell kase",
    "kase vikaycha", "kase vikayche", "kasa vikaycha", "kashi vikaychi", "kase vikaychi", "bechne ka tarika",
    "कसे विकायचे", "कसा विकायचा", "कशी विकायची", "कैसे बेचूं", "कैसे बेचूँ", "कैसे बेचें", "कैसे बेचना", "कैसे बेचते",
    "बेचना कैसे", "विकायचे कसे", "विकायचा कसा", "बेचने का तरीका", "विकण्याची पद्धत", "विक्रीची प्रक्रिया",
]
_WH_TOKENS = set(
    "what whats which how why when where who whom whose kya kyaa kyun kyu kyon kaise kaisa kaisi kitna kitne kitni kaun kaunsa "
    "kaunsi kab kahan kidhar kay kasa kashi kase kiti kon konta kontya kadhi kuthe kuthla "
    "काय क्या क्यों क्यूं क्यूँ कैसे कैसा कैसी कितना कितने कितनी कौन कौनसा कौनसी कब कहाँ कहां किधर कसा कशी कसे कसं किती कोण "
    "कोणता कोणती कोणते कधी कुठे कुठला".split())
_AUX_TOKENS = {"is", "are", "does", "can", "could", "should", "would", "was", "were"}
_AUX_PHRASES = ("do you", "did you", "will i", "will the", "will it", "are there", "is there")
_REQUEST_TOKENS = set(
    "batao bataiye bataye batayiye bata sang sanga sangaa dikhao dikha dakhva dakhava tell show check janna jaanna "
    "बताओ बताइए बताइये बताएं बताएँ बता सांग सांगा सांगाल दाखवा दिखाओ दिखाइए जानना".split())
_PRICE_TOKENS = set("price prices rate rates bhav bhaav bhaw bhao bhaao daam kimat kimmat keemat dar modal pricing भाव दर दाम रेट कीमत किंमत मूल्य".split())
_PRICE_STEMS_DEVA = ("भाव", "रेट", "कीमत", "किंमत", "किमत", "दाम", "मूल्य", "मोडल", "मॉडल")
_PRICE_PHRASES = [
    "kitne ka", "kitne mein", "kitne me", "kitne rupaye", "kitna chal", "chal raha", "chal rahi", "kiti la", "kiti rupaye",
    "how much is", "how much for", "कितने का", "कितने में", "चल रहा है", "चल रही है", "किती ला", "किती रुपये",
]
_TIME_TOKENS = set("today aaj aj ajcha ajche latest current currently now abhi sadhya atta aata लेटेस्ट करंट".split())
_TIME_STEMS_DEVA = ("आज", "सध्या", "अभी", "आता", "ताज", "करंट")
_WANT_TOKENS = set("pahije pahijet chahiye chahie hava havi want need expect expecting chahta chahte चाहिए पाहिजे हवा हवी अपेक्षित".split())
_MSP_TOKENS = {"msp"}
_MSP_PHRASES = ["support price", "minimum support", "guaranteed price", "एमएसपी", "हमी भाव", "हमीभाव", "हमीचा भाव", "हमी दर",
                "हमीदर", "समर्थन मूल्य", "आधारभूत"]
_LIVE_TOKENS = {"live", "auction", "auctions", "realtime"}
_LIVE_STEMS_DEVA = ("लाइव", "लाईव", "लिलाव", "नीलामी", "ऑक्शन")
_MODAL_STEMS_DEVA = ("मोडल", "मॉडल")
_MEANING_TOKENS = set("mean means meaning define definition explain calculated calculate calculation computed compute matlab arth".split())
_MEANING_STEMS_DEVA = ("मतलब", "अर्थ", "म्हणजे", "निकाल", "काढ")
_DISMISS_PHRASES = ["never mind", "nevermind", "leave it", "forget it", "skip", "rehne do", "rahne do", "chhod do", "chhodo",
                    "jane do", "jaane do", "no need", "dont need", "don't need", "nako", "नको", "रहने दो", "छोड़ो", "छोडो",
                    "जाऊ द्या", "जाउ द्या", "सोडा", "नहीं चाहिए"]

# A mandi named without its district (the API needs a district). Only well-known, unambiguous APMC towns.
_MARKET_DISTRICT = {
    "Baramati": "Pune", "Indapur": "Pune", "Daund": "Pune", "Khed": "Pune", "Lasalgaon": "Nashik", "Yeola": "Nashik",
    "Manmad": "Nashik", "Sinner": "Nashik", "Satana": "Nashik", "Nandgaon": "Nashik", "Pimpalgaon": "Nashik",
    "Kalwan": "Nashik", "Chandwad": "Nashik", "Rahuri": "Ahilyanagar", "Shrirampur": "Ahilyanagar", "Karmala": "Solapur",
}


def _signals(text: str) -> tuple[bool, bool, bool]:
    """(wh-word, auxiliary-question-start, request verb) - independent of any question mark."""
    norm = normalize_text(text)
    toks = norm.split()
    wh = bool(set(toks) & _WH_TOKENS)
    aux = bool(toks and toks[0] in _AUX_TOKENS) or any(norm.startswith(p) for p in _AUX_PHRASES)
    req = bool(set(toks) & _REQUEST_TOKENS)
    return wh, aux, req


def _interrogative_signal(text: str) -> bool:
    return any(_signals(text))


def _has_sell_intent(text: str) -> bool:
    """Explicit 'I want to sell ...' OR 'I have <produce>' in Marathi / Hindi / Hinglish / English. Not a question."""
    if _has_explicit_sell_intent(text):
        return True
    norm = normalize_text(text)
    toks = set(norm.split())
    if toks & _SELL_EXTRA_TOKENS or _phrase_in(norm, _SELL_EXTRA_PHRASES):
        return True
    if _phrase_in(norm, _HAVE_PHRASES):  # "I have two quintals of maize" / "mere paas do quintal maal hai"
        cid, _amb = match_commodity(text)
        return bool(cid or parse_quantity(text) is not None or toks & _PRODUCE_WORDS)
    return False


def _asks_howto_sell(text: str) -> bool:
    return _phrase_in(normalize_text(text), _HOWTO_SELL_PHRASES)


def _price_topic(text: str) -> bool:
    norm = normalize_text(text)
    if set(norm.split()) & _PRICE_TOKENS or any(st in norm for st in _PRICE_STEMS_DEVA):
        return True
    if re.search(r"(?<![\u0900-\u097f])दर(?:ा|ाने|ात|ाचा|ाचे|ाची|ांचा)?(?![\u0900-\u097f])", norm):
        return True
    return _phrase_in(norm, _PRICE_PHRASES)


def _msp_topic(text: str) -> bool:
    norm = normalize_text(text)
    return bool(set(norm.split()) & _MSP_TOKENS) or any(p in norm for p in _MSP_PHRASES)


def _live_topic(text: str) -> bool:
    norm = normalize_text(text)
    return bool(set(norm.split()) & _LIVE_TOKENS) or any(p in norm for p in _LIVE_STEMS_DEVA) or "real time" in norm


def _modal_word(text: str) -> bool:
    norm = normalize_text(text)
    return bool(set(norm.split()) & {"modal", "modals"}) or any(p in norm for p in _MODAL_STEMS_DEVA)


def _meaning_words(text: str) -> bool:
    norm = normalize_text(text)
    return bool(set(norm.split()) & _MEANING_TOKENS) or any(p in norm for p in _MEANING_STEMS_DEVA)


def _has_time_marker(text: str) -> bool:
    norm = normalize_text(text)
    return bool(set(norm.split()) & _TIME_TOKENS) or any(p in norm for p in _TIME_STEMS_DEVA)


def _commodity_named(text: str) -> bool:
    cid, amb = match_commodity(text)
    return bool(cid or amb)


def _market_word(text: str) -> bool:
    norm = normalize_text(text)
    return any(w in norm for w in MARKET_WORDS)


def _strict_state(s: dict[str, Any]) -> bool:
    """True while the farmer is giving a price / deciding on an offer: only clear questions are information requests."""
    return s.get("waiting_for") in _PRICE_STATES or _offer_active(s)


def _is_price_question(text: str, strict: bool, signal: bool, asking: bool) -> bool:
    if not _price_topic(text):
        return False
    toks = normalize_text(text).split()
    if set(toks) & _WANT_TOKENS:  # "mala changla bhav pahije" is a wish, not a question
        return False
    amount = parse_price(text) is not None
    named = _commodity_named(text) or bool(find_district(text)) or bool(find_market(text)) or _market_word(text)
    timey = _has_time_marker(text)
    if strict:
        if amount or is_same_as_reference(text):
            return False
        return signal and (named or timey or len(toks) <= 6)
    if amount and not asking:
        return False
    return bool(asking or timey or (named and len(toks) <= 6))


def _classify_info(s: dict[str, Any], text: str, strict: bool) -> Optional[str]:
    """howto | msp | live | modal | price | general | None. Never depends on a question mark alone."""
    norm = normalize_text(text)
    if not norm or skip_answer(text) or _wants_price_refresh(text):
        return None
    toks = norm.split()
    wh, aux, req = _signals(text)
    signal = wh or aux or req
    qmark = "?" in text or "？" in text
    asking = signal or (qmark and not strict)
    amount = parse_price(text) is not None
    if _asks_howto_sell(text):
        return "howto"
    if _msp_topic(text) and (asking or (not strict and not amount)):
        return "msp"
    if _live_topic(text) and asking and not amount:
        return "live"
    if _modal_word(text) and asking and (_meaning_words(text) or not (_commodity_named(text) or _has_time_marker(text))):
        return "modal"
    if _is_price_question(text, strict, signal, asking):
        return "price"
    if strict and amount:
        return None
    if s.get("waiting_for") in _DECISION_STATES and (is_accept(text) or is_reject(text) or is_negotiate(text)
                                                     or is_decrease(text) or is_send_counter(text) or is_lock_confirm(text)):
        return None  # a decision about the offer, not a question
    if ((wh or aux) and (len(toks) >= 2 or qmark)) or (req and len(toks) >= 3) or (qmark and len(toks) >= 4):
        return "general"
    return None


def _split_clauses(text: str) -> list[str]:
    parts = re.split(r"(?<=[?।!;])\s*|(?<=\.)\s+|,\s+|\n+", (text or "").strip())
    clauses = [p.strip() for p in parts if p and p.strip()]
    return clauses or [(text or "").strip()]


def _selling_active(s: dict[str, Any]) -> bool:
    return bool(s.get("selling_started") or s.get("commodity_id") or s.get("quantity_quintals") or s.get("variety")
                or s.get("district") or s.get("market"))


def _answers_pending(s: dict[str, Any], text: str, lang: str, market_form: Optional[str], district_form: Optional[str]) -> bool:
    """Would this utterance fill the pending intake field? Evaluated on a COPY, the real session is never touched."""
    waiting = s.get("waiting_for") or ""
    if not (waiting in _INTAKE_WAITS or waiting.startswith("quality:")):
        return False
    trial = copy.deepcopy(s)
    _update_entities(trial, text, lang, market_form, district_form)
    keys = ("commodity_id", "variety", "quantity_quintals", "district", "market", "market_skipped", "product_form")
    return any(trial.get(k) != s.get(k) for k in keys) or trial.get("quality") != s.get("quality")


def _has_selling_content(s: dict[str, Any], text: str) -> bool:
    """Does this (non-question) part of an utterance carry a selling detail that must not be lost?"""
    waiting = s.get("waiting_for") or ""
    if _has_sell_intent(text) or match_commodity(text)[0] or parse_quantity(text) is not None or find_district(text):
        return True
    if s.get("commodity_id") and match_variety(s["commodity_id"], text):
        return True
    if waiting == "quantity" and parse_bare_quantity(text) is not None:
        return True
    if waiting == "market" and (find_market(text) or _is_any_market(text)):
        return True
    if waiting == "quality:moisture":
        parsed = parse_moisture_answer(text)
        return parsed.get("description") != "self_reported" or parsed.get("reported_percent") is not None
    return False


def _is_pure_info(s: dict[str, Any], text: str) -> bool:
    """True when every clause is an information request (used to stop 'how do I sell maize?' rotating the session)."""
    strict = _strict_state(s)
    kinds = [_classify_info(s, c, strict) for c in _split_clauses(text)]
    return bool(kinds) and all(k in {"howto", "msp", "live", "modal", "price"} for k in kinds)

DRAFT_FRESH_MINUTES = 5


def _draft_fresh(d):
    raw = (d or {}).get("summary_shown_at")
    if not isinstance(raw, str) or not raw.strip():
        return False

    try:
        ts = datetime.fromisoformat(raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return False

    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return 0 <= age <= DRAFT_FRESH_MINUTES * 60


def counter_summary_text(s, lang):
    d = s.get("draft_offer") or {}
    price = float(d.get("price") or 0)
    quantity = float(s.get("quantity_quintals") or 0)

    return ask_text(
        lang,
        "counter_summary",
        commodity=commodity_label(s, lang),
        qty=quantity,
        district=s.get("district") or "",
        price=price,
        total=price * quantity,
    )


def propose_counter(s, price, lang):
    old_draft = s.get("draft_offer") or {}

    previous_wait = (
        old_draft.get("prev_wait")
        if s.get("waiting_for") == "counter_confirm"
        else s.get("waiting_for")
    )

    now = datetime.now(timezone.utc)

    s["farmer_desired_price"] = float(price)
    s["draft_offer"] = {
        "price": float(price),
        "version": int(s.get("offer_version", 0)) + 1,
        "prev_wait": previous_wait,
        "nonce": os.urandom(3).hex(),
        "summary_shown_at": now.isoformat(),
    }

    s["waiting_for"] = "counter_confirm"
    s["last_question"] = "counter_confirm"

    return counter_summary_text(s, lang)


_COUNTER_YES = {
    "yes", "yeah", "haan", "han", "ha", "ho", "hoy",
    "ok", "okay", "हो", "होय", "हां", "हाँ", "ठीक",
}

_COUNTER_SEND = {
    "send", "submit", "lock", "confirm",
    "bhej", "bhejo", "bhejiye",
    "पाठवा", "पाठव", "भेज", "भेजो", "भेजिए",
    "लॉक", "कन्फर्म",
}

_COUNTER_NEGATIVE = {
    "no", "not", "dont", "don't", "never",
    "नको", "नका", "नाही", "नहीं", "मत",
}

_COUNTER_QUALIFIERS = {
    "but", "maybe", "later", "tomorrow", "after",
    "increase", "more", "raise", "जास्त", "थोडा",
    "लेकिन", "पर", "शायद",
}


def is_explicit_send_confirm(text):
    tokens = _toks(text)
    token_set = set(tokens)

    if not tokens or len(tokens) > 30:
        return False

    if token_set & _COUNTER_NEGATIVE:
        return False

    if token_set & _COUNTER_QUALIFIERS:
        return False

    has_yes = bool(token_set & _COUNTER_YES)
    has_send = bool(token_set & _COUNTER_SEND) or is_send_counter(text)

    return (has_yes and has_send) or (has_yes and len(tokens) <= 2)
def _pending_question(s: dict[str, Any], lang: str) -> str:
    """The exact question the farmer still owes an answer to (empty when nothing is pending)."""
    if s.get("deal_status") in _FINISHED_DEALS:
        return ""
    wf = s.get("waiting_for") or ""
    if wf in _INTAKE_WAITS or wf.startswith("quality:"):
        step = next_required_step(s)
        return make_question(s, step, lang) if step else ""
    if wf == "farmer_target":
        return ask_text(lang, "ask_target")
    if wf == "farmer_minimum":
        return ask_text(lang, "ask_minimum")
    if wf in {"buyer_offer", "buyer_offer_clarify"}:
        return ask_text(lang, "ask_buyer_offer")
    if wf == "counter_confirm":
        return counter_summary_text(s, lang) if s.get("draft_offer") else ""
    if wf == "farmer_counter":
        return ask_text(lang, "ask_counter")
    if wf in {"farmer_decision", "farmer_confirm", "counter_decision"}:
        return ask_text(lang, "pending_decision")
    if wf == "farmer_final_confirm" and _offer_active(s):
        return _confirmation_readback(s, lang)
    return ""


def _resume_text(s: dict[str, Any], lang: str, kind: str) -> str:
    if s.get("deal_status") in _FINISHED_DEALS:
        return ""
    if _selling_active(s):
        return _pending_question(s, lang)
    return ask_text(lang, "commodity") if kind == "howto" else ask_text(lang, "offer_sell")


def _build_price_query(s: dict[str, Any], clause: str, full: str, market_form: Optional[str] = None,
                       district_form: Optional[str] = None, forced_commodity: Optional[str] = None,
                       forced_district: Optional[str] = None) -> dict[str, Any]:
    """Temporary, read-only query for an informational price question. Never written into the selling session."""
    cid = forced_commodity
    if not cid:
        c1, amb1 = match_commodity(clause)
        if c1:
            cid = c1
        elif not amb1:
            c2, amb2 = match_commodity(full) if full != clause else (None, [])
            cid = c2 or (None if amb2 else s.get("commodity_id"))
    same_crop = bool(cid and cid == s.get("commodity_id"))
    text_district = forced_district or find_district(clause) or (find_district(full) if full != clause else None)
    market = None
    mk = find_market(clause)
    if mk and (_market_word(clause) or not find_district(mk)):
        market = mk
    district = text_district or (_MARKET_DISTRICT.get(market) if market else None)
    district = district or s.get("district") or canonical_district(district_form)
    if not market and same_crop and not text_district and s.get("market") and not s.get("market_skipped") and district == s.get("district"):
        market = s["market"]
    variety = match_variety(cid, clause) if cid else None
    if not variety and same_crop and s.get("variety") and normalize_text(str(s["variety"])) not in _VARIETY_UNSPECIFIED:
        variety = s["variety"]
    product_form = s.get("product_form") if same_crop else None
    if cid == "paddy_rice" and not product_form:
        t = normalize_text(clause)
        if any(w in t for w in ["chawal", "tandul", "चावल", "तांदूळ", "तांदुळ", "processed rice"]):
            product_form = "Processed rice"
        elif any(w in t for w in ["paddy", "dhan", "धान", "भात", "साळ"]):
            product_form = "Raw paddy"
    return {"kind": "price", "commodity_id": cid, "variety": variety, "product_form": product_form,
            "district": district, "market": market, "text": clause}


def _info_price_text(q: dict[str, Any], pa: dict[str, Any], lang: str) -> str:
    """Honest wording of an official daily report: date, exact vs fallback, calculated median, stale, unavailable."""
    tmp = {"commodity_id": q["commodity_id"]}
    if not pa.get("available"):
        return ask_text(lang, "info_price_unavailable", commodity=commodity_label(tmp, lang), district=q.get("district") or "")
    as_of = pa.get("as_of_display") or pa.get("as_of") or "unknown"
    notes: list[str] = []
    if pa.get("variety_match") is False:
        notes.append(ask_text(lang, "variety_note"))
    if pa.get("market_matched") is False:
        notes.append(ask_text(lang, "market_note", market=pa.get("market_requested") or ""))
    key = "info_price_stale" if pa.get("stale") else "info_price"
    body = ask_text(lang, key, commodity=_commodity_for_price_sentence(tmp, lang), market_scope=pa.get("market_scope", DATA_GOV_STATE),
                    as_of=as_of, price_detail=_price_detail_text(pa, lang))
    return " ".join(notes + [body])


async def _info_price_turn(s: dict[str, Any], q: dict[str, Any], lang: str) -> tuple[str, bool, dict[str, Any]]:
    """(text, answered, plan). answered=False means text is ONE clarification question and s['info_query'] keeps the query."""
    if not q.get("commodity_id"):
        s["info_query"] = {**q, "awaiting": "commodity", "retries": int((s.get("info_query") or {}).get("retries", 0))}
        return ask_text(lang, "info_ask_commodity"), False, {"event": "info_needs_commodity"}
    if not q.get("district"):
        s["info_query"] = {**q, "awaiting": "district", "retries": int((s.get("info_query") or {}).get("retries", 0))}
        return ask_text(lang, "info_ask_district", commodity=commodity_label({"commodity_id": q["commodity_id"]}, lang)), False, {"event": "info_needs_district"}
    s["info_query"] = None
    pa = await fetch_mandi_benchmark(q["commodity_id"], q.get("market"), q.get("variety"), q.get("product_form"), q["district"])
    return _info_price_text(q, pa, lang), True, {"event": "info_price_answer", "info_price_as_of": pa.get("as_of")}


async def _info_turn(s: dict[str, Any], kind: str, q: Optional[dict[str, Any]], info_text: str, lang: str) -> tuple[str, bool, dict[str, Any]]:
    if kind == "price" and q is not None:
        text, answered, plan = await _info_price_turn(s, q, lang)
    elif kind == "msp":
        text, answered, plan = ask_text(lang, "info_msp"), True, {"event": "info_msp"}
    elif kind == "modal":
        text, answered, plan = ask_text(lang, "info_modal"), True, {"event": "info_glossary"}
    elif kind == "live":
        text, answered, plan = ask_text(lang, "info_live"), True, {"event": "info_glossary"}
    elif kind == "howto":
        text, answered, plan = ask_text(lang, "howto_sell"), True, {"event": "howto_sell"}
    else:
        text = await answer_off_topic(info_text, s, lang)  # Groq when configured, honest fallback otherwise
        answered = True
        plan = {"event": "general_response_with_pending" if (_selling_active(s) and _pending_question(s, lang)) else "general_response"}
    return text, answered, {**plan, "answered": answered, "info_kind": kind}


def _is_dismissal(text: str) -> bool:
    return _phrase_in(normalize_text(text), _DISMISS_PHRASES)


async def _continue_info_query(s: dict[str, Any], iq: dict[str, Any], text: str, lang: str) -> Optional[tuple[str, dict[str, Any], Optional[str], str]]:
    """An earlier price question is waiting for a district / crop. None = this turn is not the answer (normal flow)."""
    awaiting = iq.get("awaiting")
    forced_district = find_district(text) if awaiting == "district" else None
    forced_cid = match_commodity(text)[0] if awaiting == "commodity" else None
    if forced_district or forced_cid:
        q = _build_price_query(s, iq.get("text") or "", iq.get("text") or "", None, None,
                               forced_commodity=forced_cid or iq.get("commodity_id"),
                               forced_district=forced_district or iq.get("district"))
        reply, answered, plan = await _info_price_turn(s, q, lang)
        if answered:
            tail = _resume_text(s, lang, "price")
            reply = f"{reply} {tail}".strip()
        return reply, {**plan, "answered": answered, "info_kind": "price"}, None, "pure"
    if _is_dismissal(text):
        s["info_query"] = None
        return _resume_text(s, lang, "price"), {"event": "info_dropped"}, None, "pure"
    if _classify_info(s, text, _strict_state(s)) or _has_sell_intent(text) or _answers_pending(s, text, lang, None, None):
        s["info_query"] = None  # a new question or a selling answer: the old price question is dropped
        return None
    if int(iq.get("retries", 0)) < 1:
        iq["retries"] = int(iq.get("retries", 0)) + 1
        if awaiting == "commodity":
            return ask_text(lang, "info_ask_commodity"), {"event": "info_needs_commodity"}, None, "pure"
        return (ask_text(lang, "info_ask_district", commodity=commodity_label({"commodity_id": iq.get("commodity_id")}, lang)),
                {"event": "info_needs_district"}, None, "pure")
    s["info_query"] = None
    return None


async def _maybe_handle_info(s: dict[str, Any], text: str, lang: str, market_form: Optional[str] = None,
                             district_form: Optional[str] = None) -> Optional[tuple[str, dict[str, Any], Optional[str], str]]:
    """None -> not an information turn (normal selling flow).
    Otherwise (reply, plan, remaining_selling_text, mode): mode 'pure' = reply is the whole answer (answer + the
    pending question); 'prefix' = answer first, then the selling flow continues on remaining_text; 'replace' = the
    side question needs a clarification, so that one question is asked (selling details were still captured)."""
    iq = s.get("info_query")
    if iq:
        res = await _continue_info_query(s, iq, text, lang)
        if res is not None:
            return res
    strict = _strict_state(s)
    info_clauses: list[tuple[str, str]] = []
    other: list[str] = []
    for clause in _split_clauses(text):
        kind = _classify_info(s, clause, strict)
        if kind == "general":
            toks = normalize_text(clause).split()
            if (len(toks) <= 4 or re.search(r"\d", clause)) and _answers_pending(s, clause, lang, market_form, district_form):
                kind = None  # a short reply that fills the pending field ("Lokwan kya?") is an answer, not a question
        if kind:
            info_clauses.append((clause, kind))
        else:
            other.append(clause)
    if not info_clauses:
        return None
    info_text, kind = info_clauses[0]
    rest = " ".join(other).strip()
    has_rest = bool(rest) and _has_selling_content(s, rest)
    if not has_rest and kind in {"price", "general"} and _has_sell_intent(info_text):
        rest, has_rest = info_text, True  # "I have 2 quintal wheat and what is the price in Pune"
    query = _build_price_query(s, info_text, text, market_form, district_form) if kind == "price" else None
    reply, answered, plan = await _info_turn(s, kind, query, info_text, lang)
    if not has_rest:
        if answered:
            tail = _resume_text(s, lang, kind)
            reply = f"{reply} {tail}".strip()
        return reply, plan, None, "pure"
    return reply, plan, rest, ("prefix" if answered else "replace")


async def process_conversation_turn(s: dict[str, Any], text: str, lang_hint: str, market_form: Optional[str] = None,
                                    district_form: Optional[str] = None) -> tuple[str, dict[str, Any]]:
    # The language chosen in the UI applies from the start of a session (and when the farmer changes the choice);
    # afterwards short/ambiguous replies keep the session language and only clear switches change it.
    if s.get("lang_hint") != lang_hint:
        if s.get("lang_hint") is None and s.get("history"):
            pass  # session saved by an older version: keep the language it already had
        else:
            s["lang"] = _lang_from_hint(lang_hint)
        s["lang_hint"] = lang_hint
    lang = detect_language(text, s.get("lang") or lang_hint)
    s["lang"] = lang
    # Answers to the private price questions are kept out of the history that is sent to the AI assistant.
    _store_history(
    s,
    "user",
    text,
    private=s.get("waiting_for") in {
        "farmer_target",
        "farmer_minimum",
        "farmer_counter",
        "counter_confirm",
        "counter_decision",
        "farmer_decision",
        "farmer_confirm",
        "farmer_final_confirm",
    },
)
    info_mode: Optional[str] = None  # "prefix" | "replace": a side question was asked inside a longer utterance
    faq_topic: Optional[str] = None  # set when a farmer FAQ was answered at the start of this turn
    info_reply = ""
    info_plan: dict[str, Any] = {}

    def done(reply: str, plan: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if info_mode == "prefix" and info_reply:
            reply, plan = f"{info_reply} {reply}".strip(), {**plan, "info_answered": True}
            if faq_topic:
                plan["faq_topic"] = faq_topic
        elif info_mode == "replace" and info_reply:
            reply, plan = info_reply, {**info_plan, "selling_details_updated": True}
        _store_history(s, "assistant", reply, private=plan.get("event") in _PRIVATE_EVENTS)
        return reply, plan

    # Handle explicit no-send / hold instructions before information or selling logic.
    kind = no_send_kind(text)

    if kind:
        if kind == "no_send":
            if s.get("waiting_for") == "counter_confirm":
                s["waiting_for"] = (s.get("draft_offer") or {}).get("prev_wait")
            s["no_offer"] = True
            s["draft_offer"] = None
        else:
            s["hold"] = True

        return done(
            ask_text(lang, "no_send_ack" if kind == "no_send" else "hold_ack"),
            {"event": kind},
        )

    # Farmer FAQ (escrow, payment, verification, weighing...) works at any point, even before crop details.
    # Read-only: it never touches waiting_for, offers, confirmations or deal state.
    topic = detect_faq(text)
    if topic:
        faq_reply = faq_answer(topic, lang)
        faq_clauses = [c for c in _split_clauses(text) if detect_faq(c) is None]
        rest = " ".join(faq_clauses).strip()
        if rest and _has_selling_content(s, rest):
            # "5 quintal wheat, when will I get paid?" -> answer the FAQ, then continue the selling flow.
            info_reply, info_plan, info_mode, faq_topic = faq_reply, {"event": "faq", "topic": topic}, "prefix", topic
            text = rest
        else:
            tail = _pending_question(s, lang) if _selling_active(s) else ""
            return done(f"{faq_reply} {tail}".strip(), {"event": "faq", "topic": topic})

    if (s.get("no_offer") or s.get("hold")) and is_send_counter(text):
        s["no_offer"] = False
        s["hold"] = False
    # Information questions are answered first and read-only.

    handled = await _maybe_handle_info(s, text, lang, market_form, district_form)
    if handled is not None:
        info_reply, info_plan, remaining, mode = handled
        if remaining is None:
            return done(info_reply, info_plan)
        text, info_mode = remaining, mode

    if s.get("deal_status") in {"LOCKED", "LOCKED_DEMO"}:
        return done(
            ask_text(lang, "already_locked", voucher=(s.get("voucher") or {}).get("voucher_id", "")),
            {"event": "already_locked"},
        )

    if is_cancel(text):
        if not DEMO_ALLOW_UNAUTHENTICATED_ACTIONS:
            # Same fail-closed safeguard as the HTTP endpoints: a session ID is not proof of identity, so a spoken
            # "cancel" must not change deal state. Nothing is modified.
            log_deal_event(s["session_id"], "voice_cancel_blocked", {"reason": "unauthenticated_actions_disabled"})
            return done(ask_text(lang, "voice_action_disabled"), {"event": "voice_action_disabled", "action": "cancel"})
        s["deal_status"] = "CANCELLED"
        s["waiting_for"] = None
        s["farmer_confirmed"] = False
        s["buyer_confirmed"] = False
        log_deal_event(s["session_id"], "cancelled", {"by": "farmer_voice"})
        return done(ask_text(lang, "cancelled"), {"event": "cancelled"})

    if s.get("deal_status") == "CANCELLED":
        # A fresh transaction requires a new session ID to retain audit clarity.
        return done(ask_text(lang, "cancelled"), {"event": "cancelled"})

    # Explicit request to re-check official prices (only once all details exist and no offer is on the table).
    if _wants_price_refresh(text) and next_required_step(s) is None and not _offer_active(s):
        s["price_analysis"] = None
        s["price_status"] = "refresh_requested"
        s["waiting_for"] = None

    if _has_sell_intent(text):
         s["selling_started"] = True
         s["mode"] = "selling"
    before_step = next_required_step(s) if s.get("deal_status") == "GATHERING_DETAILS" else None
    prior_wait = s.get("waiting_for")  # what the farmer was answering in THIS turn
 
    ambiguity = _update_entities(s, text, lang, market_form, district_form)

    if ambiguity:
        candidates = [COMMODITIES[x]["name"] for x in ambiguity if x in COMMODITIES]
        reply = ask_text(lang, "ambiguous") + (
            " Options: " + ", ".join(candidates) if ui_lang(lang) == "en" else ""
        )
        s["waiting_for"] = "commodity"
        s["last_question"] = "commodity"
        return done(reply, {"event": "commodity_ambiguous", "candidates": ambiguity})

    # Keep a buyer-reported quote separate from the farmer's target price.
    if prior_wait == "farmer_target" and _is_buyer_quote_statement(text):
        quoted_price = parse_price(text)

        if quoted_price and 100 <= quoted_price <= 1_000_000:
            s["reported_buyer_quote"] = {
                "price_per_quintal": float(quoted_price),
                "quantity_quintals": s.get("quantity_quintals"),
                "source": "farmer_reported_buyer_offer",
                "verified": False,
                "reported_at": datetime.now(timezone.utc).isoformat(),
            }

        return done(
            ask_text(lang, "ask_target"),
            {"event": "buyer_quote_reported"},
        )
    # Farmer counter-offer: show a draft and require explicit confirmation.
    if s.get("waiting_for") == "counter_confirm":
        d = s.get("draft_offer") or {}

        if not d or not d.get("price"):
            s["draft_offer"] = None
            s["waiting_for"] = "farmer_counter"
            s["last_question"] = "farmer_counter"
            return done(ask_text(lang, "ask_counter"), {"event": "asking_counter"})

        p_new = parse_price(text)

        # A changed price creates a new draft; it never submits immediately.
        if p_new and 100 <= p_new <= 1_000_000 and abs(p_new - float(d["price"])) > 0.001:
            return done(
                propose_counter(s, p_new, lang),
                {"event": "counter_drafted", "counter_price": p_new},
            )

        # Only an explicit confirmation can submit the draft.
        if is_explicit_send_confirm(text):
            if s.get("no_offer") or s.get("hold"):
                return done(
                    ask_text(lang, "counter_not_sent"),
                    {"event": "counter_not_sent"},
                )

            # A stale summary must be shown again before submission.
            if not _draft_fresh(d):
                d["summary_shown_at"] = datetime.now(timezone.utc).isoformat()
                return done(
                    counter_summary_text(s, lang),
                    {"event": "counter_drafted", "counter_price": d["price"]},
                )

            try:
                _submit_farmer_counter(s, float(d["price"]))
            except ValueError:
                s["draft_offer"] = None
                s["waiting_for"] = None
                return done(ask_text(lang, "error"), {"event": "lock_refused"})

            submitted_price = float(d["price"])
            s["draft_offer"] = None

            return done(
                _counter_sent_text(s, lang),
                {"event": "counter_submitted", "counter_price": submitted_price},
            )

        # Rejecting the draft returns to the farmer's price question.
        if is_reject(text):
            s["draft_offer"] = None
            s["waiting_for"] = "farmer_counter"
            s["last_question"] = "farmer_counter"
            return done(ask_text(lang, "ask_counter"), {"event": "asking_counter"})

        # Any unclear response repeats the summary without submitting.
        return done(
            counter_summary_text(s, lang),
            {"event": "counter_drafted", "counter_price": d["price"]},
        )
    # An offer is already on the table waiting for the buyer: never lock on the farmer's word alone.
    if s.get("deal_status") in {"PENDING_BUYER_RESPONSE", "PENDING_BUYER_CONFIRMATION"} and _offer_active(s) and not s.get("waiting_for"):
        if _expire_offer_if_needed(s):
            _expire_offer(s)
            return done(_expired_reply(lang), {"event": "offer_expired"})
        cur_price = float(s["buyer_offer"]["price_per_quintal"])
        p_new = parse_price(text)
        if p_new and 100 <= p_new <= 1_000_000 and abs(p_new - cur_price) > 0.001:
            return done(
                propose_counter(s, p_new, lang),
                {"event": "counter_drafted", "counter_price": p_new},
            )
        if is_reject(text):
            _reject_offer(s, "farmer")
            return done(ask_text(lang, "offer_rejected"), {"event": "offer_rejected"})
        if is_negotiate(text) or is_decrease(text):
            s["waiting_for"], s["last_question"] = "farmer_counter", "farmer_counter"
            return done(ask_text(lang, "ask_counter"), {"event": "asking_counter"})
        qty_now = float(s.get("quantity_quintals") or 0)
        return done(ask_text(lang, "counter_pending", price=cur_price, qty=qty_now, total=cur_price * qty_now), {"event": "offer_pending_buyer"})

    # Counter-offer path: farmer states the price they want to ask from the buyer.
    if s.get("waiting_for") == "farmer_counter" and prior_wait == "farmer_counter":
        if s.get("counter_price"):  # extracted from THIS turn's answer, submitted exactly once
            s["counter_unclear"] = 0
            price = float(s["counter_price"])
            return done(
                propose_counter(s, price, lang),
                {"event": "counter_drafted", "counter_price": price},
            )
        s["counter_unclear"] = int(s.get("counter_unclear", 0)) + 1
        if s["counter_unclear"] >= 2 and skip_answer(text):
            return done(ask_text(lang, "counter_skipped"), {"event": "counter_skipped"})
        return done(ask_text(lang, "ask_counter"), {"event": "asking_counter"})

    # Farmer decides on the final read-back.
    if s.get("waiting_for") == "farmer_final_confirm":
        if is_accept(text) and _offer_active(s):
            if _expire_offer_if_needed(s):
                _expire_offer(s)
                return done(_expired_reply(lang), {"event": "offer_expired"})
            if not DEMO_ALLOW_UNAUTHENTICATED_ACTIONS:
                # Final voice confirmation is a deal action. DEMO_SINGLE_PARTY_LOCK cannot bypass this check
                # because it is evaluated before any lock mode is considered. Nothing is modified.
                log_deal_event(s["session_id"], "voice_confirm_blocked", {"reason": "unauthenticated_actions_disabled", "offer_version": s.get("offer_version")})
                return done(ask_text(lang, "voice_action_disabled"), {"event": "voice_action_disabled", "action": "final_confirm"})
            s["farmer_confirmed"] = True
            s["waiting_for"] = None
            s["last_question"] = None
            try:
                if DEMO_SINGLE_PARTY_LOCK:
                    deal = _lock_deal(s, mode="demo_single_party")
                    log_deal_event(s["session_id"], "demo_single_party_locked", deal)
                    return done(ask_text(lang, "locked_demo", voucher=deal["voucher_id"], total=deal["gross_amount_inr"], advance=deal["advance_amount_demo_estimate_inr"]), {"event": "locked_demo", "deal": deal})
                if s.get("buyer_confirmed"):
                    deal = _lock_deal(s, mode="two_party")
                    log_deal_event(s["session_id"], "deal_locked", deal)
                    return done(ask_text(lang, "locked", voucher=deal["voucher_id"], total=deal["gross_amount_inr"], advance=deal["advance_amount_demo_estimate_inr"]) + " " + ask_text(lang, "escrow_simulated", escrow_id=(s.get("escrow") or {}).get("escrow_id", "")), {"event": "locked", "deal": deal})
            except ValueError as exc:
                log.warning("Deal lock refused: %s", exc)
                s["farmer_confirmed"] = False
                return done(ask_text(lang, "error"), {"event": "lock_refused", "reason": str(exc)})
            s["deal_status"] = "PENDING_BUYER_CONFIRMATION"
            log_deal_event(s["session_id"], "farmer_final_terms_confirmed", {"offer_version": s.get("offer_version"), "price": (s.get("buyer_offer") or {}).get("price_per_quintal")})
            return done(ask_text(lang, "farmer_pending"), {"event": "farmer_confirmed_pending_buyer"})
        p_fin = parse_price(text)
        if p_fin and 100 <= p_fin <= 1_000_000:
            return done(
                propose_counter(s, p_fin, lang),
                {"event": "counter_drafted", "counter_price": p_fin},
            )
        if is_reject(text) and _offer_active(s):
            _reject_offer(s, "farmer")
            return done(ask_text(lang, "offer_rejected"), {"event": "offer_rejected"})
        if is_negotiate(text) or is_decrease(text):
            s["waiting_for"] = "farmer_counter"
            s["last_question"] = "farmer_counter"
            return done(ask_text(lang, "ask_counter"), {"event": "asking_counter"})
        return done(ask_text(lang, "clarify_decision"), {"event": "clarify_decision"})

    if s.get("waiting_for") == "counter_decision":
        p_cd = parse_price(text)

        if p_cd and 100 <= p_cd <= 1_000_000:
            return done(
                propose_counter(s, p_cd, lang),
                {"event": "counter_drafted", "counter_price": p_cd},
            )

        if is_accept(text) or is_send_counter(text):
            pa = s.get("price_analysis") or {}
            target, private_higher = _market_counter_target(s, pa)

            if private_higher:
                target = 0.0

            if target < 100:
                s["waiting_for"], s["last_question"] = "farmer_counter", "farmer_counter"
                return done(ask_text(lang, "ask_counter"), {"event": "asking_counter"})

            return done(
                propose_counter(s, target, lang),
                {"event": "counter_drafted", "counter_price": target},
            )

        if is_reject(text) or is_negotiate(text) or is_decrease(text):
            s["waiting_for"] = "farmer_counter"
            s["last_question"] = "farmer_counter"
            return done(ask_text(lang, "ask_counter"), {"event": "asking_counter"})

        return done(ask_text(lang, "clarify_decision"), {"event": "clarify_decision"})
        if is_reject(text) or is_negotiate(text) or is_decrease(text):
            s["waiting_for"] = "farmer_counter"
            s["last_question"] = "farmer_counter"
            return done(ask_text(lang, "ask_counter"), {"event": "asking_counter"})
        return done(ask_text(lang, "clarify_decision"), {"event": "clarify_decision"})

    if s.get("waiting_for") in {"farmer_decision", "farmer_confirm"}:
        if is_negotiate(text):
            s["waiting_for"] = "farmer_counter"
            s["last_question"] = "farmer_counter"
            return done(ask_text(lang, "ask_counter"), {"event": "asking_counter"})
        if is_accept(text) and _offer_active(s):
            s["waiting_for"] = "farmer_final_confirm"
            s["last_question"] = "final_lock_confirmation"
            return done(_confirmation_readback(s, lang), {"event": "final_terms_readback"})
        p = parse_price(text)
        if p and 100 <= p <= 1_000_000:
            return done(
                propose_counter(s, p, lang),
                {"event": "counter_drafted", "counter_price": p},
            )
        if is_reject(text) and _offer_active(s):
            _reject_offer(s, "farmer")
            return done(ask_text(lang, "offer_rejected"), {"event": "offer_rejected"})
        if is_decrease(text):
            s["waiting_for"] = "farmer_counter"
            s["last_question"] = "farmer_counter"
            return done(ask_text(lang, "ask_counter"), {"event": "asking_counter"})
        return done(ask_text(lang, "clarify_decision"), {"event": "clarify_decision"})

    # A buyer offer was just extracted on this turn.
    if s.get("waiting_for") in {"buyer_offer", "buyer_offer_clarify"} and _offer_active(s):
        p = float(s["buyer_offer"]["price_per_quintal"])
        return done(_offer_recommendation(s, lang), {"event": "buyer_offer_evaluated", "price": p, "pricing": s.get("price_analysis")})

    # Private farmer target/minimum are stored separately and never exposed in buyer-facing state.
    if s.get("waiting_for") == "farmer_minimum":
        s["last_question"] = "farmer_minimum"
        return done(ask_text(lang, "ask_minimum"), {"event": "asking_farmer_minimum"})
    if s.get("waiting_for") in {"buyer_offer", "buyer_offer_clarify"} and not _offer_active(s):
        reply_text, plan_dict = _handle_missing_buyer_offer(s, text, lang, prior_wait)
        return done(reply_text, plan_dict)

    # Fill missing commodity, variety, quantity, district, market and crop-specific quality information.
    next_step = next_required_step(s)
    if next_step:
        s["waiting_for"] = next_step
        s["last_question"] = next_step
        s["deal_status"] = "GATHERING_DETAILS"
        if next_step == "quantity" and prior_wait == "quantity" and not info_mode:
            # Quantity was just asked but no amount was understood: never guess an unknown number word, ask in a clearer form.
            return done(ask_text(lang, "quantity_unclear"), {"event": "asking_details", "waiting_for": next_step, "clarify": "quantity"})
        return done(make_question(s, next_step, lang), {"event": "asking_details", "waiting_for": next_step})

    # Price discovery: one official data.gov.in request, no static/demo price fallback.
    if not s.get("price_analysis") or s.get("price_status") in {"not_requested", "refresh_requested"}:
        s["waiting_for"] = "price_lookup"
        s["deal_status"] = "PRICE_DISCOVERY"
        pa = await fetch_mandi_benchmark(s["commodity_id"], s.get("market"), s.get("variety"), s.get("product_form"), s.get("district"))
        s["price_analysis"] = pa
        s["price_status"] = "available" if pa.get("available") else "unavailable"
        s["waiting_for"] = "farmer_target"
        s["last_question"] = "farmer_target"
        if not pa.get("available"):
            s["deal_status"] = "NEGOTIATING_WITHOUT_MARKET_REFERENCE"
            return done(ask_text(lang, "price_unavailable"), {"event": "price_unavailable", "pricing": pa})
        s["deal_status"] = "NEGOTIATING"
        return done(_build_price_guidance(s, pa, lang), {"event": "price_guidance", "pricing": pa})

    reply = await answer_off_topic(text, s, lang)
    return done(reply, {"event": "general_response"})



async def answer_off_topic(text: str, s: dict[str, Any], lang: str) -> str:
    return await _answer_off_topic_impl(
        text,
        s,
        lang,
        groq_client=_groq_client,
        groq_model=GROQ_MODEL,
        offer_active=_offer_active,
        ask_text=ask_text,
        ui_lang=ui_lang,
        logger=log,
    )


# ---------------------------------------------------------------------------
# 7. Speech pipeline (Gnani STT/TTS + FFmpeg browser audio conversion)
# ---------------------------------------------------------------------------


def gnani_headers() -> dict[str, str]:
    return {"X-API-Key-ID": GNANI_API_KEY}


def _decode_with_ffmpeg(audio_bytes: bytes) -> subprocess.CompletedProcess:
    ffmpeg = shutil.which(FFMPEG_BIN) or FFMPEG_BIN
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"]
    return subprocess.run(command, input=audio_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)


async def prepare_audio_for_gnani(audio_bytes: bytes, filename: str, content_type: str) -> tuple[bytes, str, str]:
    """Pass through formats Gnani accepts; convert browser WebM/MP4/Opus to 16 kHz mono WAV in memory
    (pipes only - no temporary files are created, so nothing needs cleaning up)."""
    extension = Path(filename.lower()).suffix
    mime = (content_type or "").split(";", 1)[0].lower()
    supported_ext = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
    supported_mime = {"audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/flac", "audio/ogg"}
    if extension in supported_ext or mime in supported_mime:
        return audio_bytes, filename, content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if extension not in {".webm", ".mp4", ".opus"} and mime not in {"audio/webm", "audio/mp4", "video/webm"}:
        raise HTTPException(415, "Unsupported audio format. Use WAV, MP3, FLAC, OGG, M4A or browser WebM audio.")
    try:
        proc = await asyncio.to_thread(_decode_with_ffmpeg, audio_bytes)  # never block the event loop
    except FileNotFoundError as exc:
        raise HTTPException(503, "FFmpeg was not found. Set FFMPEG_BIN in backend/.env to the full ffmpeg.exe path.") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "Audio conversion timed out. Please record a shorter clip.") from exc
    if proc.returncode != 0 or not proc.stdout:
        log.warning("FFmpeg decode failed: %s", proc.stderr.decode(errors="ignore")[:300])
        raise HTTPException(415, "Could not decode this recording. Please record again.")
    return proc.stdout, "voice.wav", "audio/wav"


async def transcribe_audio_stream(audio_bytes: bytes, filename: str, content_type: str) -> dict[str, Any]:
    if not GNANI_API_KEY:
        raise HTTPException(503, "GNANI_API_KEY is missing. Add it to backend/.env for voice input.")
    audio_bytes, filename, content_type = await prepare_audio_for_gnani(audio_bytes, filename, content_type)
    language_codes = GNANI_STT_LANGUAGE
    if language_codes.lower() in {"indic-auto", "auto", "all-indic"}:
        language_codes = "mr-IN,hi-IN,en-IN"
    data = {
        "model": GNANI_STT_MODEL,
        "language_code": language_codes,
        "format": GNANI_STT_FORMAT,
        "keyterms": json.dumps([  # documented Prisma v3.0 field (JSON array, up to 200); 'keywords' is not in the API contract
            "Soybean", "Wheat", "Jowar", "Moong", "Urad", "Maize", "Onion", "Bajra", "Chana", "Tur", "Cotton", "Paddy",
            "Lokwan", "Sharbati", "Indrayani", "Kolam", "Basmati", "Harbhara", "Kapas", "Quintal", "APMC", "Mandi",
            "Nashik", "Pune", "Lasalgaon", "Latur", "Solapur", "Nagpur", "Jalgaon", "Akola",
        ], ensure_ascii=False),
        "itn_native_numerals": "true",
    }
    try:
        async with httpx.AsyncClient(timeout=75.0, trust_env=False) as client:
            response = await client.post(
                GNANI_STT_URL,
                headers=gnani_headers(),
                files={"audio_file": (filename, audio_bytes, content_type)},
                data=data,
            )
            response.raise_for_status()
        body = response.json()
        if body.get("success") is False:
            raise RuntimeError(str(body.get("message") or body.get("error") or "Gnani rejected audio"))
        transcript = body.get("transcript") or body.get("text") or ""
        if not isinstance(transcript, str) or not transcript.strip():
            raise RuntimeError(f"Gnani returned an empty transcript: {str(body)[:250]}")
        return {
            "text": transcript.strip(),
            "source": "gnani-prisma-v3",
            "detected_language_code": body.get("detected_language_code") or body.get("language_code") or body.get("language"),
            "request_id": body.get("request_id"),
        }
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        log.error("Gnani STT HTTP %s: %s", status, (exc.response.text[:300] if exc.response is not None else ""))
        raise HTTPException(502, f"Gnani STT returned HTTP {status}. Check key, model and audio format.") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "Gnani STT timed out. Please try a shorter recording.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Gnani STT error")
        raise HTTPException(502, f"Gnani STT failed: {str(exc)[:220]}") from exc


def _tts_language_for(text: str, lang: str) -> str:
    """TTS language follows the RESPONSE language, not just the script: Roman-script Hinglish is Hindi speech."""
    if lang == "hinglish":
        return "hi"
    deva = len(re.findall(r"[\u0900-\u097f]", text))
    if lang in {"mr", "hi"}:
        if deva:
            return lang
        detected = detect_language(text, lang)  # Latin text in a Marathi/Hindi session (e.g. an English LLM answer)
        return "en" if detected == "en" else "mr" if detected == "mr" else "hi"
    if deva:  # English session but Devanagari text
        return "mr" if detect_language(text, "mr-IN") == "mr" else "hi"
    return "en"


def _clean_tts_text(text: str, language: str) -> str:
    """Normalise to NFC, drop markdown/control characters and say rupee amounts in words the voice can read."""
    t = unicodedata.normalize("NFC", text or "")
    t = re.sub(r"[\x00-\x08\x0b-\x1f\u200b-\u200d\ufeff*_#`]+", " ", t)
    has_deva = bool(re.search(r"[\u0900-\u097f]", t))
    word = "रुपये" if has_deva else ("rupaye" if language == "hi" else "rupees")
    t = re.sub(r"₹\s*([\d,]+(?:\.\d+)?)", lambda m: f"{m.group(1).replace(',', '')} {word}", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:1200]


def _voice_for(language: str, voice: Optional[str]) -> str:
    """Explicit voice > GNANI_TTS_VOICE_<LANG> > GNANI_TTS_VOICE. No voice names are invented."""
    return voice or os.getenv(f"GNANI_TTS_VOICE_{language.upper()}", "").strip() or GNANI_TTS_VOICE


def _safe_snippet(value: str, limit: int = 300) -> str:
    out = value or ""
    for secret in (GNANI_API_KEY, DATA_GOV_IN_API_KEY, GROQ_API_KEY):
        if secret:
            out = out.replace(secret, "***")
    return re.sub(r"\s+", " ", out)[:limit]


def _tts_failure(error: str, http_status: Optional[int] = None) -> dict[str, Any]:
    return {"status": "failed", "audio_base64": "", "audio_mime_type": "audio/wav", "source": "none", "error": error[:220], "http_status": http_status}


_GNANI_TTS_LANGUAGE_CODES = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN"}  # documented `language` values; "hi-en" = Hinglish


async def synthesize_voice(text: str, language: str, voice: Optional[str] = None, hinglish: bool = False) -> dict[str, Any]:
    if not GNANI_API_KEY:
        return {"status": "unavailable", "audio_base64": "", "audio_mime_type": "audio/wav", "source": "none", "error": "GNANI_API_KEY is not configured"}
    text = _clean_tts_text(text, language)
    if not text:
        return {"status": "unavailable", "audio_base64": "", "audio_mime_type": "audio/wav", "source": "none", "error": "Empty TTS text"}
    voice_name = _voice_for("hinglish" if hinglish else language, voice)
    model = os.getenv(f"GNANI_TTS_MODEL_{'HINGLISH' if hinglish else language.upper()}", "").strip() or GNANI_TTS_MODEL
    payload: dict[str, Any] = {
        "text": text, "voice": voice_name, "model": model,
        "language": "hi-en" if hinglish else _GNANI_TTS_LANGUAGE_CODES.get(language, "auto"),
        # Documented AudioConfig values (the OpenAPI schema lists audio_config as required).
                "audio_config": {"sample_rate": 24000, "num_channels": 1, "sample_width": 2, "encoding": "linear_pcm", "container": "wav"},
    }

    # Slightly faster speech for Gnani Timbre v2.5
    if model == "timbre-v2.5":
        payload["speed"] = 1.05

    try:
        async with httpx.AsyncClient(timeout=45.0, trust_env=False) as client:
            response = await client.post(GNANI_TTS_URL, headers={**gnani_headers(), "Content-Type": "application/json"}, json=payload)
        if response.status_code >= 400:
            log.warning("Gnani TTS HTTP %s (language=%s voice=%s): %s", response.status_code, language, voice_name, _safe_snippet(response.text))
            return _tts_failure(f"Gnani TTS HTTP {response.status_code}: {_safe_snippet(response.text, 160)}", response.status_code)
        content_type = (response.headers.get("content-type") or "").split(";", 1)[0].lower()
        if content_type.startswith("audio/") or "octet-stream" in content_type:
            audio_bytes = response.content
            mime = content_type if content_type.startswith("audio/") else "audio/wav"
        else:
            body = response.json()
            value = body.get("audio_base64") or body.get("audio") or body.get("audio_content") or body.get("data") or ""
            if isinstance(value, dict):
                value = value.get("audio_base64") or value.get("audio") or ""
            if isinstance(value, str) and value.startswith("data:") and "," in value:
                header, value = value.split(",", 1)
                content_type = header[5:].split(";", 1)[0]
            if not (isinstance(value, str) and value):
                raise RuntimeError("Gnani TTS response contained no audio field")
            try:
                audio_bytes = base64.b64decode(re.sub(r"\s+", "", value), validate=True)
            except (ValueError, TypeError) as exc:
                raise RuntimeError("Gnani TTS returned invalid base64 audio") from exc
            mime = body.get("mime_type") or body.get("content_type") or body.get("audio_mime_type") or content_type or "audio/wav"
        if not audio_bytes:
            raise RuntimeError("Gnani TTS returned empty audio")
        return {"status": "success", "audio_base64": base64.b64encode(audio_bytes).decode("ascii"), "audio_mime_type": mime, "source": "gnani",
                "audio_size_bytes": len(audio_bytes), "http_status": response.status_code}
    except Exception as exc:  # a TTS failure must never break the conversation turn
        log.warning("Gnani TTS failed: %s (%s)", type(exc).__name__, _safe_snippet(str(exc), 160))
        return _tts_failure(_safe_snippet(str(exc), 200) or type(exc).__name__)


# ---------------------------------------------------------------------------
# 8. API and WebSocket
# ---------------------------------------------------------------------------

app = FastAPI(title="SaudaVani", version="2.2.0")
_CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()] or ["*"]  # restrict in production
app.add_middleware(CORSMiddleware, allow_origins=_CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def _require_demo_actions() -> None:
    """Fail closed: these endpoints accept a client-supplied `party` with no authentication, so they must not be
    reachable unless the operator explicitly enabled the simulated demo workflow."""
    if not DEMO_ALLOW_UNAUTHENTICATED_ACTIONS:
        raise HTTPException(403, "Unauthenticated deal actions are disabled. Real farmer/buyer authentication is required for production; "
                                 "for the local simulated demo set DEMO_ALLOW_UNAUTHENTICATED_ACTIONS=true.")


def _check_session_id(session_id: str) -> str:
    if not SESSION_ID_RE.match(session_id or ""):
        raise HTTPException(422, "Invalid session_id. Use 1-128 letters, digits, '-', '_', '.' or ':'.")
    return session_id


class BuyerOfferIn(BaseModel):
    buyer_id: str = Field(min_length=1, max_length=100)
    price_per_quintal: float = Field(gt=0, le=1_000_000)
    quantity_quintals: Optional[float] = Field(default=None, gt=0, le=100_000)
    offer_valid_minutes: int = Field(default=30, ge=1, le=1440)
    replaces_offer_version: Optional[int] = Field(default=None, ge=1)


class DealConfirmationIn(BaseModel):
    party: Literal["farmer", "buyer"]
    accepted: bool = True
    offer_version: int = Field(ge=1)


class ManualMarketIn(BaseModel):
    # Optional admin/manual fallback only; never presented as live government data.
    modal_price: float = Field(gt=0, le=1_000_000)
    source_label: str = Field(min_length=3, max_length=120)
    as_of: Optional[str] = None


class ConnectionManager:
    """Rooms are keyed by (role, session_id); role is 'farmer' or 'buyer'."""

    def __init__(self) -> None:
        self.rooms: dict[tuple[str, str], set[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket, role: str = "farmer") -> None:
        await websocket.accept()
        self.rooms.setdefault((role, session_id), set()).add(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket, role: str = "farmer") -> None:
        room = self.rooms.get((role, session_id))
        if room is not None:
            room.discard(websocket)
            if not room:
                self.rooms.pop((role, session_id), None)

    async def broadcast(self, session_id: str, payload: dict[str, Any], role: str = "farmer") -> None:
        for websocket in list(self.rooms.get((role, session_id), set())):
            try:
                await websocket.send_json(payload)
            except Exception:
                self.disconnect(session_id, websocket, role)


manager = ConnectionManager()


async def broadcast_session(session_id: str, s: dict[str, Any], farmer_extra: Optional[dict[str, Any]] = None) -> None:
    """Farmer room: full state plus optional text fields. Buyer room: whitelist state ONLY (no text, no latency)."""
    await manager.broadcast(session_id, {"type": "state_update", "state": public_state(s), **(farmer_extra or {})}, role="farmer")
    await manager.broadcast(session_id, {"type": "state_update", "state": buyer_state(s)}, role="buyer")


_PRIVATE_EVENTS = {"asking_farmer_minimum", "buyer_offer_evaluated", "counter_drafted"}


def _broadcast_text(event: Optional[str], text: str) -> str:
    """WebSocket rooms may include the buyer: never broadcast text that can reveal the farmer's private minimum."""
    return "[private to farmer]" if event in _PRIVATE_EVENTS else text


_BUYER_SOURCE_LABELS = {
    "farmer_counter_offer": "Farmer's counter-offer",
    "buyer_submitted_offer": "Buyer-submitted offer (identity not authenticated)",
    "farmer_reported_buyer_offer": "Farmer-reported, unverified (buyer quote reported by the farmer)",
}
_BUYER_PROPOSED_BY = {
    "farmer_counter_offer": "farmer",
    "buyer_submitted_offer": "buyer",
    "farmer_reported_buyer_offer": "farmer_reported_buyer_quote",
}


def _seconds_left(s: dict[str, Any]) -> int:
    """Whole seconds until the active offer expires. Invalid expiry fails closed to 0."""
    expiry = _parse_offer_expiry(s.get("offer_expires_at"))
    if expiry is None:
        return 0
    return max(0, int((expiry - datetime.now(timezone.utc)).total_seconds()))


def _buyer_action_blocked_reason(s: dict[str, Any]) -> Optional[str]:
    """Explain why the buyer cannot accept the current offer; this is display state, not authorization."""
    status = s.get("deal_status")
    if status in {"LOCKED", "LOCKED_DEMO"}:
        return "deal_already_locked"
    if status == "CANCELLED":
        return "deal_cancelled"
    if not DEMO_ALLOW_UNAUTHENTICATED_ACTIONS:
        return "actions_disabled_on_server"
    if not _offer_active(s):
        return "no_active_offer"
    if _expire_offer_if_needed(s):
        return "offer_expired"
    return None


def _buyer_quality_list(s: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for key, value in (s.get("quality") or {}).items():
        if isinstance(value, dict):
            if value.get("reported_percent") is not None:
                shown = f"{value['reported_percent']:g}%"
            elif value.get("description") == "dry_self_reported":
                shown = "Dry (farmer-reported)"
            elif value.get("description") == "moist_self_reported":
                shown = "Moist (farmer-reported)"
            else:
                shown = str(value.get("answer") or "Not provided")
        else:
            shown = str(value)
        out.append({"label": _QUALITY_LABELS["en"].get(key, key).capitalize(), "value": shown})
    return out


def buyer_state(s: dict[str, Any]) -> dict[str, Any]:
    """Whitelist-only view for the buyer. Never add farmer_name, history, private prices or strong_target_price."""
    qty = s.get("quantity_quintals")
    action_blocked_reason = _buyer_action_blocked_reason(s)
    pa = s.get("price_analysis") or {}
    cur = s.get("buyer_offer")
    active_offer = None
    if cur and cur.get("active", True) is not False:
        src = cur.get("source")
        price = cur.get("price_per_quintal")
        active_offer = {
            "price_per_quintal": price,
            "quantity_quintals": qty,
            "gross_value": round(qty * price, 2) if qty and price else None,
            "proposed_by": _BUYER_PROPOSED_BY.get(src, "farmer_reported_buyer_quote"),
            "source_label": _BUYER_SOURCE_LABELS.get(src, "Farmer-reported, unverified"),
            "status": cur.get("status") or "active",
            "offer_version": s.get("offer_version", 0),
            "expires_at": s.get("offer_expires_at"),
            "seconds_left": _seconds_left(s),
        }
    mandi_reference = None
    if pa.get("available"):
        mandi_reference = {
            "modal_reference": pa.get("modal_reference"),
            "reference_type": pa.get("reference_type"),
            "modal_reference_label": pa.get("modal_reference_label"),
            "as_of": pa.get("as_of"),
            "market_scope": pa.get("market_scope"),
            "stale": pa.get("stale"),
            "variety_fallback": pa.get("variety_fallback"),
            "market_fallback": pa.get("market_fallback"),
        }
    v = s.get("voucher")
    locked_deal = {k: v.get(k) for k in ("status", "voucher_id", "commodity", "variety", "district", "market",
                                         "price_per_quintal", "quantity_quintals", "gross_amount_inr",
                                         "offer_version", "locked_at", "notice")} if v else None
    e = s.get("escrow")
    escrow = {
        "status": e.get("status"),
        "simulated_amount_inr": e.get("simulated_amount_inr"),
        "actual_money_transferred_inr": 0,
        "notice": e.get("notice") or ESCROW_SIM_NOTICE,
    } if e else None
    return {
        "session_id": s["session_id"],
        "crop": s.get("commodity"),
        "variety": s.get("variety"),
        "product_form": s.get("product_form"),
        "quantity_quintals": qty,
        "district": s.get("district"),
        "market": s.get("market") or "District-wide",
        "quality": _buyer_quality_list(s),
        "deal_status": s.get("deal_status"),
        "ready_for_offer": is_price_ready(s) and s.get("deal_status") not in {"LOCKED", "LOCKED_DEMO", "CANCELLED"},
        "is_locked": s.get("deal_status") in {"LOCKED", "LOCKED_DEMO"},
        "offer_version": s.get("offer_version", 0),
        "farmer_confirmed": bool(s.get("farmer_confirmed")),
        "buyer_confirmed": bool(s.get("buyer_confirmed")),
        "buyer_can_accept": action_blocked_reason is None,
        "buyer_action_blocked_reason": action_blocked_reason,
        "active_offer": active_offer,
        "mandi_reference": mandi_reference,
        "locked_deal": locked_deal,
        "escrow": escrow,
    }


def _deal_response(s: dict[str, Any], party: str, message: str) -> dict[str, Any]:
    """Response for confirm: buyer callers get the buyer-safe state, farmer callers the farmer state."""
    state = buyer_state(s) if party == "buyer" else public_state(s)
    out: dict[str, Any] = {"ok": True, "state": state, "message": message}
    if s.get("deal_status") in {"LOCKED", "LOCKED_DEMO"}:
        out["locked_deal"] = state.get("locked_deal")
        out["escrow"] = state.get("escrow") if party == "buyer" else state.get("simulated_escrow")
    return out


def _require_existing_session(session_id: str) -> None:
    if peek_session(session_id) is None:
        raise HTTPException(404, "No deal found for this session ID.")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": app.version,
        "groq": bool(_groq_client),
        "groq_model": GROQ_MODEL if _groq_client else None,
        "groq_status": {
            "last_ok_at": GROQ_STATUS.get("last_ok_at"),
            "last_error": GROQ_STATUS.get("last_error"),
            "last_error_at": GROQ_STATUS.get("last_error_at"),
        },
        "gnani": bool(GNANI_API_KEY),
        "market_data": bool(DATA_GOV_IN_API_KEY),
        "market_source": "data.gov.in / AGMARKNET",
        "market_resource_id": DATA_GOV_RESOURCE_ID,
        "market_transport": "curl" if (DATA_GOV_TRANSPORT in {"auto", "curl"} and _find_curl()) else "httpx",
        "database": str(DB_PATH),
        "active_sessions_in_memory": len(SESSIONS),
        "demo_single_party_lock": DEMO_SINGLE_PARTY_LOCK,
        "unauthenticated_demo_actions_enabled": DEMO_ALLOW_UNAUTHENTICATED_ACTIONS,
        "voice_final_confirm_and_cancel_enabled": DEMO_ALLOW_UNAUTHENTICATED_ACTIONS,
        "production_ready_for_real_trading": False,
        "escrow": "SIMULATED only; actual money transferred is always INR 0",
    }


@app.get("/api/commodities")
async def get_commodities() -> dict[str, Any]:
    return {
        "items": [
            {"id": cid, "name": item["name"], "marathi": item["mr"], "hindi": item["hi"], "aliases": item["aliases"],
             "varieties": item["varieties"], "quality_fields": [q[0] for q in item["questions"]]}
            for cid, item in COMMODITIES.items()
        ]
    }


@app.get("/api/session/{session_id}")
async def get_session_state(session_id: str) -> dict[str, Any]:
    _check_session_id(session_id)
    s = load_session(session_id)
    return {**public_state(s), "language": s.get("lang"), "turns": len([m for m in s.get("history", []) if m.get("role") == "user"])}


@app.get("/api/buyer/session/{session_id}")
async def get_buyer_session(session_id: str) -> dict[str, Any]:
    _check_session_id(session_id)
    s = peek_session(session_id)
    if s is None:
        raise HTTPException(404, "No deal found for this session ID.")
    return buyer_state(s)


@app.get("/api/prices/{commodity_id}")
async def get_prices(commodity_id: str, market: Optional[str] = None, variety: Optional[str] = None,
                     product_form: Optional[str] = None, district: Optional[str] = None) -> dict[str, Any]:
    if commodity_id not in COMMODITIES:
        raise HTTPException(404, "Unsupported commodity ID")
    return await fetch_mandi_benchmark(commodity_id, market, variety, product_form, district)


@app.post("/api/deals/{session_id}/buyer-offer")
async def submit_buyer_offer(session_id: str, data: BuyerOfferIn) -> dict[str, Any]:
    _check_session_id(session_id)
    _require_demo_actions()
    _require_existing_session(session_id)  # unknown ID -> 404, no junk row
    async with session_lock(session_id):
        s = load_session(session_id)
        if s.get("deal_status") in {"LOCKED", "LOCKED_DEMO", "CANCELLED"}:
            raise HTTPException(409, f"Cannot submit an offer while deal status is {s.get('deal_status')}")
        if not is_price_ready(s):
            raise HTTPException(409, "Complete commodity, variety, quantity, district, market and quality details first.")
        offer_quantity = float(data.quantity_quintals or s["quantity_quintals"])
        if abs(offer_quantity - float(s["quantity_quintals"])) > 0.0001:
            raise HTTPException(409, "Buyer offer quantity does not match the farmer's lot quantity.")
        if _offer_active(s):
            if _expire_offer_if_needed(s):
                _expire_offer(s, "expired_before_new_offer")   # dead offer is invalidated once, then a fresh one is allowed
            else:
                cur = s["buyer_offer"]
                # Only supported replacement: the buyer revises THEIR OWN offer, naming its exact current version,
                # and the farmer has not already confirmed it. Farmer counters / farmer-reported quotes are never replaced.
                replaceable = (
                    data.replaces_offer_version is not None
                    and data.replaces_offer_version == int(s.get("offer_version", 0))
                    and cur.get("source") == "buyer_submitted_offer"
                    and not s.get("farmer_confirmed")
                )
                if not replaceable:
                    raise HTTPException(409, "An active offer is already awaiting a response. It cannot be overwritten; "
                                             "wait for it to be answered, rejected or expired.")
                cur["active"] = False
                cur["status"] = "superseded_by_buyer_revision"
                cur["superseded_at"] = datetime.now(timezone.utc).isoformat()
        if not s.get("price_analysis"):
            s["price_analysis"] = await fetch_mandi_benchmark(s["commodity_id"], s.get("market"), s.get("variety"), s.get("product_form"), s.get("district"))
            s["price_status"] = "available" if s["price_analysis"].get("available") else "unavailable"
        s["offer_version"] = int(s.get("offer_version", 0)) + 1
        offer = {
            "price_per_quintal": float(data.price_per_quintal),
            "quantity_quintals": offer_quantity,
            "buyer_id": data.buyer_id,
            "source": "buyer_submitted_offer",
            "verified": True,
            "buyer_confirmed": True,
            "active": True,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
        s["buyer_offer"] = offer
        s["original_buyer_offer"] = None
        s["reported_buyer_quote"] = None
        s["buyer_offer_status"] = "verified"
        s["buyer_confirmed"] = True  # submitting this exact offer is the buyer's confirmation
        s["farmer_confirmed"] = False
        s["counter_price"] = None
        s["offer_expires_at"] = (datetime.now(timezone.utc) + timedelta(minutes=data.offer_valid_minutes)).isoformat()
        s["deal_status"] = "NEGOTIATING"
        lang = s.get("lang") or "mr"
        recommendation = _offer_recommendation(s, lang)
        # Farmer-room only (never sent to the buyer room), so the recommendation text is safe here.
        notice_text = (ask_text(lang, "notice_buyer_offer", price=float(data.price_per_quintal), qty=offer_quantity,
                                total=float(data.price_per_quintal) * offer_quantity) + " " + recommendation)
        _store_history(s, "assistant", notice_text)
        log_deal_event(session_id, "buyer_offer_submitted", {"offer_version": s["offer_version"], **offer})
        log_deal_event(session_id, "buyer_offer_evaluated", {
            "offer_version": s["offer_version"],
            "recommendation_state": s.get("waiting_for"),
            "price_analysis_available": bool((s.get("price_analysis") or {}).get("available")),
        })
        save_session(s)
        state = buyer_state(s)  # the buyer never receives public_state()
    await broadcast_session(session_id, s, {"notice": True, "event": "buyer_offer", "agent_text": notice_text})
    return {"ok": True, "offer_version": s["offer_version"], "state": state,
            "message": f"Offer version {s['offer_version']} recorded. Waiting for the farmer's response."}


@app.post("/api/deals/{session_id}/confirm")
async def confirm_deal(session_id: str, data: DealConfirmationIn) -> dict[str, Any]:
    _check_session_id(session_id)
    _require_demo_actions()
    _require_existing_session(session_id)
    notice: Optional[dict[str, Any]] = None
    async with session_lock(session_id):
        s = load_session(session_id)
        lang = s.get("lang") or "mr"
        if s.get("deal_status") in {"LOCKED", "LOCKED_DEMO"}:
            return _deal_response(s, data.party, "Deal already locked.")
        if s.get("deal_status") == "CANCELLED":
            raise HTTPException(409, "This deal has been cancelled.")
        if data.offer_version != int(s.get("offer_version", 0)) or data.offer_version < 1:
            raise HTTPException(409, "Offer version mismatch. Confirm the latest offer only.")
        if not _offer_active(s):
            raise HTTPException(409, "There is no active buyer offer to confirm (none made, or it was superseded by a counter).")
        if _expire_offer_if_needed(s):
            _expire_offer(s)
            text = ask_text(lang, "notice_offer_expired")
            _store_history(s, "assistant", text)
            save_session(s)
            await broadcast_session(session_id, s, {"notice": True, "event": "offer_expired", "agent_text": text})
            raise HTTPException(409, f"Offer expired after {DEFAULT_OFFER_VALID_MINUTES} minutes and can no longer be confirmed. Submit a new offer.")
        if not data.accepted:
            _reject_offer(s, data.party)
            message = f"{data.party} rejected this offer. It is now inactive and cannot be confirmed; a fresh offer is required."
            if data.party == "buyer":
                text = ask_text(lang, "notice_buyer_rejected")
                _store_history(s, "assistant", text)
                notice = {"notice": True, "event": "buyer_rejected", "agent_text": text}
        else:
            previous_farmer_confirmed = bool(s.get("farmer_confirmed"))
            previous_buyer_confirmed = bool(s.get("buyer_confirmed"))
            previous_deal_status = s.get("deal_status")
            if data.party == "farmer":
                s["farmer_confirmed"] = True
            else:
                s["buyer_confirmed"] = True
            if s.get("farmer_confirmed") and s.get("buyer_confirmed"):
                try:
                    deal = _lock_deal(s, mode="two_party")
                except ValueError as exc:
                    # A failed validation must not leave a new confirmation half-applied.
                    # If expiry was detected inside _lock_deal, preserve the intentional OFFER_EXPIRED state.
                    if s.get("deal_status") == "OFFER_EXPIRED":
                        s["farmer_confirmed"] = False
                        s["buyer_confirmed"] = False
                    else:
                        s["farmer_confirmed"] = previous_farmer_confirmed
                        s["buyer_confirmed"] = previous_buyer_confirmed
                        s["deal_status"] = previous_deal_status
                    save_session(s)
                    raise HTTPException(409, str(exc)) from exc
                log_deal_event(session_id, "deal_locked", deal)
                message = ("Both parties confirmed the same offer version. Deal record locked; no money was transferred. "
                           "SIMULATION ONLY: a simulated escrow record was created and simulated funds are locked; actual money transferred: ₹0.")
                if data.party == "buyer":
                    text = ask_text(lang, "notice_buyer_accepted_locked", voucher=deal["voucher_id"], total=deal["gross_amount_inr"],
                                    escrow_id=(s.get("escrow") or {}).get("escrow_id", ""))
                    _store_history(s, "assistant", text)
                    notice = {"notice": True, "event": "buyer_accepted_locked", "agent_text": text}
            else:
                s["deal_status"] = "PENDING_BUYER_CONFIRMATION" if s.get("farmer_confirmed") else "PENDING_FARMER_CONFIRMATION"
                message = "Confirmation recorded. The other party must confirm the same offer version."
                log_deal_event(session_id, f"{data.party}_confirmed", {"offer_version": data.offer_version})
        save_session(s)
        response = _deal_response(s, data.party, message)
    await broadcast_session(session_id, s, notice)
    return response


class EscrowReleaseIn(BaseModel):
    requested_by: Literal["farmer", "buyer", "system"] = "system"


@app.get("/api/deals/{session_id}/escrow")
async def get_simulated_escrow(session_id: str) -> dict[str, Any]:
    _check_session_id(session_id)
    s = load_session(session_id)
    if not s.get("escrow"):
        raise HTTPException(404, "No simulated escrow exists for this session (both parties must confirm the same offer first).")
    return {"ok": True, "simulation": True, "escrow": s["escrow"], "notice": ESCROW_SIM_NOTICE}


@app.post("/api/deals/{session_id}/escrow/release")
async def release_simulated_escrow(session_id: str, data: Optional[EscrowReleaseIn] = None) -> dict[str, Any]:
    _check_session_id(session_id)
    _require_demo_actions()
    async with session_lock(session_id):
        s = load_session(session_id)
        if not s.get("escrow"):
            raise HTTPException(409, "No simulated escrow exists; both parties must confirm the same offer first.")
        try:
            escrow = _release_simulated_escrow(s, (data.requested_by if data else "system"))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        save_session(s)
        state = public_state(s)
    await broadcast_session(session_id, s)
    return {"ok": True, "simulation": True, "escrow": escrow, "state": state,
            "message": "SIMULATION ONLY: simulated escrow released/cleared. Actual money transferred: ₹0."}


@app.post("/api/deals/{session_id}/cancel")
async def cancel_deal(session_id: str, reason: str = "User requested cancellation") -> dict[str, Any]:
    _check_session_id(session_id)
    _require_demo_actions()
    async with session_lock(session_id):
        s = load_session(session_id)
        if s.get("deal_status") in {"LOCKED", "LOCKED_DEMO"}:
            raise HTTPException(409, "A locked deal cannot be cancelled through this prototype endpoint. Add the agreed cancellation policy/workflow.")
        s["deal_status"] = "CANCELLED"
        s["waiting_for"] = None
        s["farmer_confirmed"] = False
        s["buyer_confirmed"] = False
        log_deal_event(session_id, "cancelled", {"reason": reason[:250]})
        save_session(s)
        state = public_state(s)
    await broadcast_session(session_id, s)
    return {"ok": True, "state": state}


@app.post("/api/voice/process")
async def process_voice(
    session_id: str = Form(...),
    farmer_name: Optional[str] = Form(None),
    transcript: Optional[str] = Form(None, description="Text input skips STT"),
    language: str = Form("mr-IN"),
    voice: Optional[str] = Form(None),
    market: Optional[str] = Form(None),
    district: Optional[str] = Form(None, description="Optional: district chosen in the UI; otherwise collected in conversation"),
    audio: Optional[UploadFile] = File(None),
) -> dict[str, Any]:
    _check_session_id(session_id)
    stt_ms = llm_ms = tts_ms = 0
    stt_source = "text"

    if transcript and transcript.strip():
        user_text = transcript.strip()
    elif audio is not None:
        audio_bytes = await audio.read(MAX_AUDIO_BYTES + 1)  # never load an arbitrarily large upload
        if not audio_bytes:
            raise HTTPException(400, "Empty audio file")
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(413, f"Audio is too large. Maximum allowed size is {MAX_AUDIO_BYTES // (1024 * 1024)} MB.")
        filename = audio.filename or "voice.webm"
        content_type = audio.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        started = time.perf_counter()
        stt = await transcribe_audio_stream(audio_bytes, filename, content_type)
        stt_ms = round((time.perf_counter() - started) * 1000)
        user_text = stt["text"]
        stt_source = stt["source"]
    else:
        raise HTTPException(400, "Provide either 'audio' or 'transcript'.")

    user_text = user_text.translate(DEVA_DIGITS).strip()[:2000]
    if not user_text:
        raise HTTPException(422, "No speech was recognised. Please try again.")

    rotated_from: Optional[str] = None
    async with session_lock(session_id):
        s = load_session(session_id, farmer_name)
        new_cid = _new_commodity_request(s, user_text)
        if new_cid:
            old = s                                   # the old session is NOT modified or saved
            rotated_from = session_id
            session_id = _rotated_session_id(rotated_from, new_cid)
            s = new_session(session_id, farmer_name or old.get("farmer_name"))
            s["farmer_id"] = old.get("farmer_id", s["farmer_id"])   # same farmer, nothing else inherited
            s["previous_session_id"] = rotated_from
            SESSIONS[session_id] = s
            save_session(s)
            log_deal_event(rotated_from, "new_commodity_session_started", {"new_session_id": session_id, "commodity_id": new_cid})
            log_deal_event(session_id, "session_started_from", {"previous_session_id": rotated_from})
        prior_waiting = s.get("waiting_for")
        started = time.perf_counter()
        try:
            agent_text, plan = await process_conversation_turn(s, user_text, language, market, district)
        except Exception:
            # One bad turn must not crash the server or corrupt the session: answer politely and carry on.
            log.exception("Conversation turn failed for session %s", session_id)
            agent_text, plan = ask_text(s.get("lang") or "mr", "error"), {"event": "error"}
        llm_ms = round((time.perf_counter() - started) * 1000)
        save_session(s)
        state = public_state(s)
        lang = s.get("lang", "mr")

    # TTS language is an ISO language code (mr/hi/en) rather than the STT locale (mr-IN/hi-IN).
    tts_lang = _tts_language_for(agent_text, lang)
    started = time.perf_counter()
    tts = await synthesize_voice(agent_text, tts_lang, voice, hinglish=(lang == "hinglish"))
    tts_ms = round((time.perf_counter() - started) * 1000)

    latency = {"stt": stt_ms, "agent": llm_ms, "tts": tts_ms, "total": stt_ms + llm_ms + tts_ms}
    event = plan.get("event")
    response = {
        "session_id": session_id,
        "session_rotated": rotated_from is not None,
        "previous_session_id": rotated_from,
        "user_transcript": user_text,
        "stt_source": stt_source,
        "language": {"key": lang, "label": LANGUAGE_PROFILES.get(lang, LANGUAGE_PROFILES["mr"])["label"], "code": lang},
        "tts_language": tts_lang,
        "intent": event,
        "agent_text": agent_text,
        "agent_source": ("groq" if _groq_client else "offline") if event in {"general_response", "general_response_with_pending"} else "deterministic-core",
        "audio_status": tts.get("status"),
        "audio_source": tts.get("source"),
        "audio_error": tts.get("error"),
        "audio_http_status": tts.get("http_status"),
        "audio_mime_type": tts.get("audio_mime_type", "audio/wav"),
        "audio_base64": tts.get("audio_base64", ""),
        "pricing": state["pricing"],
        "deal_state": {
            "deal_status": state["deal_status"],
            "crop": state["crop"],
            "commodity_id": state["commodity_id"],
            "variety": state["variety"],
            "quantity": state["quantity"],
            "district": state["district"],
            "market": state["market"],
            "buyer_offer": state["buyer_offer"],
            "reported_buyer_quote": state["reported_buyer_quote"],
            "active_offer": state["active_offer"],
            "offer_version": state["offer_version"],
            "negotiation_round": state["negotiation_round"],
            "farmer_confirmed": state["farmer_confirmed"],
            "buyer_confirmed": state["buyer_confirmed"],
            "voucher": state["locked_deal"],
        },
        "next_action": state["waiting_for"],
        "latency_ms": latency,
    }
    if rotated_from:
        await manager.broadcast(rotated_from, {"type": "session_rotated", "previous_session_id": rotated_from,
                                               "new_session_id": session_id}, role="farmer")
    await broadcast_session(session_id, s, {
        "user_transcript": "[private to farmer]" if prior_waiting in {"farmer_target", "farmer_minimum"} else user_text,
        "agent_text": _broadcast_text(event, agent_text), "latency_ms": latency, "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return response


@app.websocket("/ws/trade/{session_id}")
async def trade_ws(websocket: WebSocket, session_id: str) -> None:
    if not SESSION_ID_RE.match(session_id or ""):
        await websocket.close(code=1008)
        return
    await manager.connect(session_id, websocket)
    try:
        await websocket.send_json({"type": "snapshot", "state": public_state(load_session(session_id))})
        while True:
            message = await websocket.receive_text()
            if message.strip().lower() == "ping":
                await websocket.send_json({"type": "pong"})
            elif "get_state" in message:
                await websocket.send_json({"type": "snapshot", "state": public_state(load_session(session_id))})
    except WebSocketDisconnect:
        pass  # a disconnect only removes this socket from the room; session state is untouched
    except Exception as exc:
        log.warning("WebSocket error for %s: %s", session_id, type(exc).__name__)
    finally:
        manager.disconnect(session_id, websocket)


@app.websocket("/ws/buyer/{session_id}")
async def buyer_ws(websocket: WebSocket, session_id: str) -> None:
    if not SESSION_ID_RE.match(session_id or ""):
        await websocket.close(code=1008)
        return
    s = peek_session(session_id)
    if s is None:
        await websocket.accept()
        await websocket.send_json({"type": "not_found"})
        await websocket.close()
        return
    await manager.connect(session_id, websocket, "buyer")
    try:
        await websocket.send_json({"type": "snapshot", "state": buyer_state(s)})
        while True:
            message = await websocket.receive_text()
            if message.strip().lower() == "ping":
                await websocket.send_json({"type": "pong"})
            elif "get_state" in message:
                fresh = peek_session(session_id)
                if fresh is None:
                    await websocket.send_json({"type": "not_found"})
                else:
                    await websocket.send_json({"type": "snapshot", "state": buyer_state(fresh)})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("Buyer WebSocket error for %s: %s", session_id, type(exc).__name__)
    finally:
        manager.disconnect(session_id, websocket, "buyer")


@app.on_event("startup")
async def startup_event() -> None:
    log.info("SaudaVani started. market_data=%s groq=%s gnani=%s db=%s resource=%s",
             bool(DATA_GOV_IN_API_KEY), bool(_groq_client), bool(GNANI_API_KEY), DB_PATH, DATA_GOV_RESOURCE_ID)
    if _RESOURCE_ID_OVERRIDDEN:
        log.warning("DATA_GOV_RESOURCE_ID pointed at the legacy dataset; using the verified variety-wise resource instead. Update .env.")
    if _API_URL_IGNORED:
        log.warning("DATA_GOV_API_URL did not match DATA_GOV_RESOURCE_ID and was ignored. Remove it from .env.")
    if DATA_GOV_TRANSPORT in {"auto", "curl"} and not _find_curl():
        log.warning("curl not found; mandi prices will use httpx (set DATA_GOV_TRANSPORT=httpx to silence this).")
    if not DATA_GOV_IN_API_KEY:
        log.warning("DATA_GOV_IN_API_KEY is missing: live mandi pricing will be unavailable; no mock benchmark is used.")
    if not GNANI_API_KEY:
        log.warning("GNANI_API_KEY is missing: voice STT/TTS unavailable; transcript endpoint remains usable.")
    if DEMO_ALLOW_UNAUTHENTICATED_ACTIONS:
        log.warning("DEMO_ALLOW_UNAUTHENTICATED_ACTIONS is ON: deal actions are unauthenticated and SIMULATED only. Not for real trading.")
    else:
        log.info("Unauthenticated deal actions (buyer offer / confirm / escrow release / cancel, and spoken final confirmation / cancellation) are disabled (fail-closed).")
        if DEMO_SINGLE_PARTY_LOCK:
            log.warning("DEMO_SINGLE_PARTY_LOCK=true has NO effect while DEMO_ALLOW_UNAUTHENTICATED_ACTIONS is false (the safeguard cannot be bypassed).")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)