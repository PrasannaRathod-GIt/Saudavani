
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Optional

from config import DEVA_DIGITS
from catalog import (
    COMMODITIES,
    DISTRICTS,
    MARKET_ALIASES,
    KNOWN_MARKETS,
)
# ---------------------------------------------------------------------------
# 3. Language profiles and text normalisation
# ---------------------------------------------------------------------------

LANGUAGE_PROFILES: dict[str, dict[str, str]] = {
    "mr": {"label": "Marathi", "tts": "mr", "script": "deva"},
    "hi": {"label": "Hindi", "tts": "hi", "script": "deva"},
    "en": {"label": "English", "tts": "en", "script": "latin"},
    "hinglish": {"label": "Hinglish", "tts": "hi", "script": "latin"},
}

_MR_MARKERS = set("aahe ahe aahet ahet kiti kay mala majha majhya tumhi tumhala tumcha aamhi aamhala pahije dya kara nako chalel barobar kasa kashi kuthe ani aani sang sanga vikaycha vikaychi viknar ghya naay mhanje thodasa jast jasta".split())
_HI_MARKERS = set("hai hain hoon kya kitna kitne kitni mera meri aap aapka aapko nahin nahi haan chahiye bechna bechunga batao bataiye batayiye kar karo kardo bhejo bhej yahi mujhe hum hamara main hoga hogi rakho theek thik accha achha badhao jyada zyada pata maloom nhi kaun kaunsi kaunsa kahan dijiye kijiye".split())
_EN_MARKERS = set("the is are do does have has want how what where which price sell selling farmer please".split())
# Short acknowledgements ("haan", "theek hai", "nahi") carry no language signal: they keep the session language.
_ACK_TOKENS = set("haan haa ha han haanji hanji haji ji jee theek thik hai accha achha ok okay okk sahi pakka bilkul nahi nahin nhi na yes no".split())
_CODESWITCH_WORDS = set("offer counter price deal lock confirm accept reject rate buyer final ok okay quantity increase decrease cancel send mandi market".split())
_QUESTION_TOKENS = {"काय", "कसा", "कसे", "कशी", "कुठे", "का", "क्या", "कैसे", "कितना", "कब", "kay", "kasa", "kashi", "kuthe", "kya", "kaise", "kitna", "kiti", "what", "why", "how", "which", "when", "where", "can", "should"}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value or "").translate(DEVA_DIGITS).lower().strip()
    value = value.replace("’", "'").replace("–", "-")
    value = re.sub(r"[^\w\u0900-\u097f%.-]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _alias_in(alias: str, norm: str) -> bool:
    """Word-aware alias match. Latin: strict boundaries. Devanagari: not mid-word on the left, and
    not followed by a virama (so 'धान' does not match 'धान्य'); Marathi suffixes on the right are allowed."""
    a = normalize_text(alias)
    if not a:
        return False
    if a.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", norm) is not None
    return re.search(rf"(?<![\u0900-\u097f]){re.escape(a)}(?!\u094d)", norm) is not None


def _lang_from_hint(hint: Optional[str]) -> str:
    """Map the UI/STT language hint (or an internal code) to a session language: mr | hi | hinglish | en."""
    h = (hint or "").strip().lower().replace("_", "-")
    if h in {"mr", "hi", "en", "hinglish"}:
        return h
    if "hinglish" in h or h in {"hi-latn", "hi-en", "hi-in-latn", "hien"}:
        return "hinglish"
    if h.startswith("mr"):
        return "mr"
    if h.startswith("hi"):
        return "hi"
    if h.startswith("en"):
        return "en"
    return "mr"


def detect_language(text: str, hint: str = "mr-IN") -> str:
    """Detect CLEAR language markers only. Short answers, numbers, commodity and market names inherit the
    session language (`hint`: either a UI/STT locale such as hi-IN or an internal code such as hinglish)."""
    fallback = _lang_from_hint(hint)
    deva = len(re.findall(r"[\u0900-\u097f]", text))
    latin_tokens = re.findall(r"[a-z]+", text.lower())
    code_switch = set(latin_tokens) & _CODESWITCH_WORDS
    if deva:
        mr_markers = ("आहे", "आहेत", "तुम्ही", "मला", "माझ्या", "किती", "नाही", "चालेल", "विकायचा", "विकणार", "पाहिजे", "कुठे", "तुमचा", "माहीत", "माहित")
        hi_markers = ("है", "हैं", "आप", "कितने", "कितना", "चाहिए", "बेचेंगे", "बताइए", "नहीं", "कहाँ", "कैसा", "मुझे", "मेरा", "पता")
        if any(w in text for w in mr_markers):
            return "mr"
        hindi = any(w in text for w in hi_markers)
        if fallback == "hinglish":
            return "hinglish"  # ambiguous Devanagari Hindi keeps the Hinglish session
        if (hindi or fallback == "hi") and len(code_switch) >= 2:
            return "hinglish"  # clear Hindi/English code-switching, not one stray English word
        if hindi:
            return "hi"
        return "hi" if fallback == "en" else fallback
    if latin_tokens and len(latin_tokens) <= 3 and all(w in _ACK_TOKENS for w in latin_tokens):
        return fallback  # a Hindi session answering "haan" stays Hindi (it is not a switch to Hinglish)
    mr_score = sum(w in _MR_MARKERS for w in latin_tokens)
    hi_score = sum(w in _HI_MARKERS for w in latin_tokens)
    en_score = sum(w in _EN_MARKERS for w in latin_tokens)
    if mr_score > hi_score and mr_score > en_score:
        return "mr"
    if hi_score > mr_score and hi_score >= en_score:
        return "hinglish"
    if en_score >= 2 or (en_score >= 1 and fallback == "en"):
        return "en"
    return fallback


def ui_lang(lang: str) -> str:
    """Languages we have written copy for. Romanised Hindi is answered in Hindi (Devanagari)."""
    return "hi" if lang == "hinglish" else lang if lang in {"mr", "hi", "en"} else "mr"


def match_commodity(text: str) -> tuple[Optional[str], list[str]]:
    """Match longest aliases first; return (canonical_id, ambiguous_candidates)."""
    norm = normalize_text(text)
    hits: list[tuple[int, str]] = []
    for cid, item in COMMODITIES.items():
        for alias in item["aliases"]:
            if _alias_in(alias, norm):
                hits.append((len(normalize_text(alias)), cid))
    if not hits:
        # Conservative fuzzy rescue for short Roman ASR variants only.
        # Common English words that are close to a crop alias ("what" ~ "wheat") must never be rescued as a crop.
        roman_words = [w for w in re.findall(r"[a-z]{3,}", norm) if w not in {"what", "whats", "when", "where", "which", "white", "whole", "wheel", "weight", "great", "group", "price", "prices", "prize", "rise", "nice", "race", "grain", "grains"}]
        best: tuple[float, str] | None = None
        for word in roman_words:
            for cid, item in COMMODITIES.items():
                for alias in item["aliases"]:
                    a = normalize_text(alias)
                    if a.isascii() and len(a.replace(" ", "")) >= 4:
                        score = SequenceMatcher(None, word, a.replace(" ", "")).ratio()
                        if score >= 0.88 and (best is None or score > best[0]):
                            best = (score, cid)
        return (best[1], []) if best else (None, [])
    max_len = max(n for n, _ in hits)
    best_ids = list(dict.fromkeys(cid for n, cid in hits if n == max_len))
    return (best_ids[0], best_ids[1:]) if len(best_ids) == 1 else (None, best_ids)


def match_variety(commodity_id: str, text: str) -> Optional[str]:
    item = COMMODITIES[commodity_id]
    norm = normalize_text(text)
    aliases = item.get("variety_aliases", {})
    for alias in sorted(aliases, key=len, reverse=True):
        if _alias_in(alias, norm):
            return aliases[alias]
    for option in item["varieties"]:
        key = normalize_text(option)
        if key not in {"other not sure", "other local", "not sure"} and key in norm:
            return option
    return None


def find_district(text: str) -> Optional[str]:
    """Return the canonical district name found in the utterance, if any."""
    norm = normalize_text(text)
    best: tuple[int, str] | None = None
    for canonical, _variants, aliases in DISTRICTS:
        for alias in aliases:
            if _alias_in(alias, norm):
                n = len(normalize_text(alias))
                if best is None or n > best[0]:
                    best = (n, canonical)
    return best[1] if best else None


def canonical_district(value: Optional[str]) -> Optional[str]:
    if not value or not str(value).strip():
        return None
    known = find_district(str(value))
    if known:
        return known
    cleaned = re.sub(r"\s+", " ", str(value)).strip()[:60]
    return cleaned.title() if cleaned else None


def district_variants(district: str) -> list[str]:
    for canonical, variants, _aliases in DISTRICTS:
        if canonical.lower() == district.lower():
            return list(variants)
    return [district]


def find_market(text: str) -> Optional[str]:
    norm = normalize_text(text)
    for alias in sorted(MARKET_ALIASES, key=len, reverse=True):
        if normalize_text(alias) in norm:
            return MARKET_ALIASES[alias]
    for name in sorted(KNOWN_MARKETS, key=len, reverse=True):
        n = normalize_text(name)
        if n and (n in norm):
            return name
    return None


# --- Quantity parsing -------------------------------------------------------------------------------------------
# A quantity is "a number + a unit" where the number is digits (Latin or Devanagari) OR a spoken number word in
# English / Hindi / Marathi / Roman-script Hindi-Marathi. Everything is converted to QUINTALS (1 quintal = 100 kg,
# 1 tonne = 10 quintals). An unrecognised number word is never guessed: parse_quantity() returns None and the
# conversation asks again in a clearer form.
_NUMBER_WORDS: dict[str, float] = {}
for _val, _words in (
    (1, "one ek एक ik"),
    (2, "two do don दो दोन doh"),
    (3, "three teen tin तीन"),
    (4, "four char chaar चार"),
    (5, "five paanch panch paach pach पांच पाँच पाच"),
    (6, "six chhe chhah chah cheh che छह छः छे छ सहा saha sahaa"),
    (7, "seven saat sat सात"),
    (8, "eight aath ath आठ"),
    (9, "nine nau nav नौ नऊ नव"),
    (10, "ten das dah daha दस दहा"),
    (11, "eleven gyarah gyaarah ग्यारह akra akara अकरा"),
    (12, "twelve barah baarah bara baara बारह बारा"),
    (13, "thirteen terah tera तेरह तेरा"),
    (14, "fourteen chaudah chauda चौदह चौदा"),
    (15, "fifteen pandrah pandra pandhra पंद्रह पन्द्रह पंधरा"),
    (16, "sixteen solah sola सोलह सोळा"),
    (17, "seventeen satrah satra सत्रह सतरा"),
    (18, "eighteen atharah athrah athara अठारह अठरा"),
    (19, "nineteen unnis unis ekonis उन्नीस एकोणीस"),
    (20, "twenty bees vees बीस वीस"),
    (25, "pachchis pachis pachees पच्चीस पंचवीस"),
    (30, "thirty tees tis तीस"),
    (40, "forty chalis chaalis चालीस"),
    (50, "fifty pachas pannas पचास पन्नास"),
    (60, "sixty saath साठ"),
    (70, "seventy sattar सत्तर"),
    (80, "eighty assi अस्सी ऐंशी"),
    (90, "ninety nabbe नब्बे नव्वद"),
    (0.5, "half aadha adha ardha आधा अर्धा"),
    (0.75, "paun pauna पौन"),
    (1.25, "sava सवा"),
    (1.5, "dedh deedh dhed डेढ़ डेढ दीड"),
    (2.5, "dhai adhai adeech aadich ढाई अढ़ाई अडीच"),
):
    for _w in _words.split():
        _NUMBER_WORDS[normalize_text(_w)] = float(_val)
del _val, _words, _w
_HUNDRED_WORDS = {normalize_text(w) for w in "hundred sau shambhar शंभर सौ".split()}
_THOUSAND_WORDS = {normalize_text(w) for w in "thousand hazaar hazar hajar हजार हज़ार".split()}
_SADE_WORDS = {normalize_text(w) for w in "sade saadhe sadhe साडे साढ़े साढे".split()}  # "sade teen" = 3.5

_QTY_QUINTAL_WORDS = {"quintal", "quintals", "quintaal", "qtl", "qtls", "kwintal", "kwintals", "kvintal", "quental"}
_QTY_QUINTAL_DEVA = ("क्विंटल", "क्विन्टल", "क्वींटल", "क्विटल", "कुंतल")
_QTY_KG_WORDS = {"kg", "kgs", "kilo", "kilos", "kilogram", "kilograms", "kila"}
_QTY_KG_DEVA = ("किलो", "किग्रा", "केजी")
_QTY_TON_WORDS = {"ton", "tons", "tonne", "tonnes"}
_QTY_TON_DEVA = ("टन",)
_QTY_PER_WORDS = {"per", "prati", "प्रति", "pratek", "प्रत्येक", "each"}   # "per 100 kg" is a price basis, not a quantity
_QTY_NEG_BEFORE = {"not"}                                                  # "not 2 quintal, 3 quintal"
_QTY_NEG_AFTER = {"nahi", "nahin", "nhi", "नाही", "नहीं", "नही", "नको"}      # "2 quintal nahi, 3 quintal"
_QTY_FILLERS = set(
    "hai hain aahe ahe aahet ahet है हैं आहे आहेत maal mal माल only about around approx approximately lagbhag लगभग bas बस "
    "hoga hogi होगा होगी aasel असेल sumare सुमारे kareeb करीब almost nearly i have mere paas mera mere मेरे पास "
    "majhyakade माझ्याकडे ch ही च hi tak".split()
)
_QTY_BLOCK_TOKENS = set(
    "acre acres एकर hectare hectares hector हेक्टर bigha बिघा rs rupees rupee rupaye रुपये रुपए percent per प्रति feet फुट "
    "day days din दिन month months महीने year years साल".split()
)


def _unit_factor(token: str) -> Optional[float]:
    """Quintals per unit for a unit word (quintal / kg / tonne, Latin or Devanagari, Marathi suffixes allowed)."""
    t = token.strip(".")
    if not t:
        return None
    if t in _QTY_QUINTAL_WORDS or t.startswith(_QTY_QUINTAL_DEVA):
        return 1.0
    if t in _QTY_KG_WORDS or t.startswith(_QTY_KG_DEVA):
        return 0.01
    if t in _QTY_TON_WORDS or t.startswith(_QTY_TON_DEVA):
        return 10.0
    return None


def _qty_tokens(text: str) -> list[str]:
    raw = (text or "").translate(DEVA_DIGITS)
    raw = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", raw)  # 1,200 kg -> 1200 kg
    return [t for t in (x.strip(".-") for x in normalize_text(raw).split()) if t]


def _number_value(token: str) -> Optional[float]:
    value = _NUMBER_WORDS.get(token)
    if value is None and len(token) > 2 and token.endswith("च"):  # Marathi emphasis: "दोनच" = just two
        value = _NUMBER_WORDS.get(token[:-1])
    return value


def _number_phrase(tokens: list[str], i: int) -> Optional[tuple[float, int]]:
    """Read a spoken number starting at tokens[i]: 'दो', 'पाँच सौ', 'twenty five', 'साडे तीन', 'दो हजार पाँच सौ'.
    Returns (value, index of the first token after the number) or None when tokens[i] is not a number word."""
    n, j = len(tokens), i
    sade = False
    if tokens[j] in _SADE_WORDS and j + 1 < n:
        sade, j = True, j + 1
    total = cur = 0.0
    got, prev = False, ""
    while j < n:
        t = tokens[j]
        if t in _HUNDRED_WORDS:
            cur, got, prev = (cur or 1.0) * 100.0, True, "mult"
        elif t in _THOUSAND_WORDS:
            total, cur, got, prev = total + (cur or 1.0) * 1000.0, 0.0, True, "mult"
        else:
            v = _number_value(t)
            if v is None:
                break
            whole = v == int(v)
            if not got:
                cur, got = v, True
            elif prev == "tens" and whole and v < 10:
                cur += v
            elif prev == "mult" and v < 100:
                cur += v
            else:
                break
            prev = "tens" if (whole and v >= 20 and v % 10 == 0) else "small"
        j += 1
    if not got:
        return None
    return total + cur + (0.5 if sade else 0.0), j


def _quantity_matches(tokens: list[str], allow_kg: bool = True) -> list[float]:
    """Every 'number + unit' in the utterance, as quintals, in spoken order (negated / per-unit ones dropped)."""
    found: list[float] = []
    n, i = len(tokens), 0
    while i < n:
        value: Optional[float] = None
        unit: Optional[str] = None
        last, nxt = i, i + 1
        m = re.fullmatch(r"(\d+(?:\.\d+)?)(\D*)", tokens[i])
        if m:
            value = float(m.group(1))
            if m.group(2):
                unit = m.group(2)
            elif i + 1 < n:
                unit, last = tokens[i + 1], i + 1
        else:
            phrase = _number_phrase(tokens, i)
            if phrase:
                value, nxt = phrase
                if nxt < n:
                    unit, last = tokens[nxt], nxt
        factor = _unit_factor(unit) if unit else None
        if value is not None and factor is not None and (allow_kg or factor != 0.01):
            before = tokens[i - 1] if i else ""
            after = tokens[last + 1] if last + 1 < n else ""
            if not (before in _QTY_PER_WORDS or before in _QTY_NEG_BEFORE or after in _QTY_NEG_AFTER):
                found.append(round(value * factor, 6))
            i = last + 1
            continue
        i = max(i + 1, nxt) if (value is not None and not m) else i + 1
    return found


def parse_quantity(text: str, allow_kg: bool = True) -> Optional[float]:
    """Quantity in QUINTALS from '2 quintal', '4 kg', 'दोन क्विंटल', 'एक टन', 'do quintal', 'two quintals' ...
    Needs an explicit unit, so unrelated numbers (prices, phone numbers, percentages) are never read as a quantity.
    When several quantities are spoken (a correction) the last non-negated one wins. None when nothing valid."""
    values = [v for v in _quantity_matches(_qty_tokens(text), allow_kg) if 0 < v <= 100000]
    return values[-1] if values else None


def parse_bare_quantity(text: str) -> Optional[float]:
    """Use ONLY right after the quantity question was asked: 'दोन', 'दो', 'two', '50', 'I have two' -> quintals."""
    tokens = _qty_tokens(text)
    core = [t for t in tokens if t not in _QTY_FILLERS]
    value: Optional[float] = None
    if core and len(core) <= 4:
        if len(core) == 1 and re.fullmatch(r"\d+(?:\.\d+)?", core[0]):
            value = float(core[0])
        else:
            phrase = _number_phrase(core, 0)
            if phrase and phrase[1] == len(core):
                value = phrase[0]
    if value is None:
        # Lenient: exactly one digit-number in the sentence and no price / area / duration word around it.
        digits = re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])", " ".join(tokens))
        if len(digits) == 1 and not (set(tokens) & _QTY_BLOCK_TOKENS) and "₹" not in (text or ""):
            value = float(digits[0])
    return value if value is not None and 0 < value <= 100000 else None


# Quantities and percentages are removed before a bare 3-6 digit number can be read as a price.
_DEVA = r"[\u0900-\u097f]*"
_QTY_STRIP = re.compile(
    r"\d+(?:\.\d+)?\s*(?:quintals?|quintaal|qtls?|kwintals?|kvintals?|क्विंटल" + _DEVA + r"|क्विन्टल" + _DEVA + r"|क्वींटल" + _DEVA
    + r"|कुंतल" + _DEVA + r"|टन" + _DEVA + r"|tonnes?|tons?|kgs?|kilograms?|kilos?|kila|किलो" + _DEVA + r"|किग्रा|केजी|%|percent|प्रतिशत|टक्के)",
    re.I,
)


def parse_price(text: str) -> Optional[float]:
    t = text.translate(DEVA_DIGITS).replace(",", "")
    explicit = re.search(
        r"(?:₹|rs\.?|rupees?|rupaye|रुपये|रुपए|रु\.?)\s*(\d{3,6})|"
        r"(\d{3,6})\s*(?:₹|rs\.?|rupees?|rupaye|रुपये|रुपए|रु\.?|per\s*quintal|प्रति\s*क्विंटल)",
        t, re.I,
    )
    if explicit:
        return float(explicit.group(1) or explicit.group(2))
    # A bare 3-6 digit amount is acceptable only after quantities/percentages are removed.
    stripped = _QTY_STRIP.sub(" ", t)
    bare = re.search(r"(?<![\d.])(\d{3,6})(?![\d.])", stripped)
    return float(bare.group(1)) if bare else None


def parse_moisture_answer(text: str) -> dict[str, Any]:
    t = normalize_text(text)
    pct = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent|प्रतिशत|टक्के)", t, re.I)
    if pct:
        n = float(pct.group(1))
        if 0 <= n <= 100:
            return {"reported_percent": n, "description": "measured_or_farmer_reported"}
    if any(x in t for x in ["sukha", "sokha", "sookha", "dry", "कोरडा", "सुका", "सूखा", "सुखा"]):
        return {"reported_percent": None, "description": "dry_self_reported"}
    if any(x in t for x in ["nami", "geela", "gila", "wet", "moist", "ओला", "ओलसर", "नमी", "गीला", "दमट"]):
        return {"reported_percent": None, "description": "moist_self_reported"}
    return {"reported_percent": None, "description": "self_reported", "answer": text.strip()[:200]}

