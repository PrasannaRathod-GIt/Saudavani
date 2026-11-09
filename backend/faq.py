"""Farmer FAQ detection (Step 2D).

Pure, read-only helpers: detecting an FAQ topic never touches session state. The caller (main.py) answers the
FAQ and, when a selling conversation is active, appends the existing pending question.

Matching is word-boundary based on normalised text (so "bilkul" never matches a "bill" phrase and the buyer word
"आडतिया" never matches the deduction word "आडत"). Common spelling/suffix variants are listed explicitly.
"""
from __future__ import annotations

from typing import Optional

from replies import ask_text
from text_utils import normalize_text

# Order matters: the more specific topics are checked first.
FAQ_TOPICS: tuple[str, ...] = (
    "escrow",
    "payment_recovery",
    "payment_timing",
    "buyer_verification",
    "weighing",
    "net_amount",
    "documents",
    "cannot_do",
)

_RAW_PHRASES: dict[str, list[str]] = {
    "escrow": [
        "escrow", "escro", "एस्क्रो", "एस्क्रॉ", "एस्क्रू",
        "paisa lock", "paise lock", "पैसा लॉक", "पैसे लॉक", "पैसे कुठे ठेवले", "पैसे कहाँ रखे", "पैसा कहाँ रखा",
        "paisa kahan rakha", "paise kahan rakhe", "money held", "money is held", "who holds the money", "who holds my money",
        "is my money safe", "mera paisa safe", "माझे पैसे सुरक्षित", "मेरा पैसा सुरक्षित",
    ],
    "payment_recovery": [
        "if buyer does not pay", "if the buyer does not pay", "if buyer doesn't pay", "if the buyer doesn't pay", "buyer will not pay",
        "buyer won't pay", "buyer does not pay", "buyer doesn't pay", "buyer didn't pay", "buyer did not pay", "buyer runs away",
        "not paid", "recover payment", "recover my money", "get my money back", "guarantee payment", "payment guarantee",
        "guarantee my payment", "will i get my money", "cheat", "cheated", "fraud", "scam",
        "buyer paisa nahi de", "buyer paise nahi de", "paisa nahi diya", "paise nahi diye", "paisa nahi mila", "paise nahi mile",
        "paisa doob", "paise doob", "dhoka", "dhokha", "payment ki guarantee", "paise ki guarantee", "paisa wapas",
        "पैसे नाही दिले", "पैसे नाही मिळाले", "पैसे बुडवले", "पैसे बुडाले", "पैसे बुडतील", "पेमेंट गॅरंटी", "पेमेंटची हमी",
        "पैसे मिळण्याची हमी", "पैसे परत", "फसवणूक", "फसवले", "फसवला", "धोका",
        "पैसे नहीं दिए", "पैसे नहीं दिये", "पैसा नहीं दिया", "पैसे नहीं मिले", "पैसा नहीं मिला", "पैसे डूब", "पैसा डूब",
        "भुगतान की गारंटी", "पेमेंट की गारंटी", "पैसे की गारंटी", "पैसों की गारंटी", "पैसे वापस", "पैसा वापस", "धोखा", "ठगी", "ठगा",
        "खरीदार पैसे नहीं", "खरेदीदाराने पैसे नाही",
    ],
    "payment_timing": [
        "when will i get paid", "when do i get paid", "when will i be paid", "when will i get my money", "when will i receive",
        "when will payment", "when is payment", "when is the payment", "payment date", "payment timing", "how soon will i be paid",
        "payment kab", "paisa kab", "paise kab", "kab milega paisa", "kab milenge paise", "payment kadhi", "paisa kadhi", "paise kadhi",
        "paise kadhi miltil", "paise kadhi milnar", "payment kab milega", "payment kab tak",
        "पैसे कब", "पैसा कब", "पेमेंट कब", "भुगतान कब", "कब मिलेंगे", "कब मिलेगा पैसा", "पैसे कधी", "पैसा कधी", "पेमेंट कधी",
        "कधी मिळतील", "कधी मिळणार", "कधी मिळेल", "पेमेंट केव्हा", "पैसे केव्हा",
            "पैसे लगेच मिळतील",
        "लगेच पैसे मिळतील",
        "offer accept केला तर पैसे",
        "offer accept केला तर मला पैसे",
        "paise lagech miltil",
    ],
    "buyer_verification": [
        "is the buyer genuine", "is buyer genuine", "buyer genuine", "is the buyer real", "is buyer real", "buyer verified",
        "is the buyer verified", "is buyer verified", "verify the buyer", "verify buyer", "can i trust the buyer", "can i trust buyer",
        "trust the buyer", "trust buyer", "is the buyer safe", "is buyer safe", "is this buyer safe", "who is the buyer",
        "fake buyer", "buyer fake", "buyer check", "check the buyer", "buyer kaun hai", "buyer asli", "buyer sahi hai", "buyer verified hai",
        "buyer pe bharosa", "buyer par bharosa", "kharidar asli", "kharidar bharosemand", "kharidar par bharosa", "buyer ki jaanch",
        "buyer ki verification", "kharedidar khara", "kharedidar kharach", "kharedidar vishwasu", "kharedidar kon", "kharidar kaun",
        "खरीदार असली", "खरीदार भरोसेमंद", "खरीदार पर भरोसा", "खरीदार सही है", "खरीदार की जाँच", "खरीदार की जांच", "खरीदार का सत्यापन",
        "खरीदार कौन", "खरेदीदार खरा", "खरेदीदार खराच", "खरेदीदार विश्वासू", "खरेदीदारावर विश्वास", "खरेदीदाराची पडताळणी", "खरेदीदार कोण",
        "व्यापारी खरा", "व्यापारी असली", "व्यापारी कौन", "व्यापारी कोण",
            "buyer खरा आहे",
        "buyer खरा आहे की नाही",
        "buyer verify करता",
        "verify करता का",
    ],
    "weighing": [
        "who will weigh", "who weighs", "who is weighing", "weigh my", "weighing", "weighbridge", "weigh bridge", "weight machine",
        "dharmakata", "dharam kata", "dharam kanta", "vajan kaun", "vajan kon", "vajan kaise", "vajan kase", "wajan kaun",
        "tola kaun", "tolna kaun",
        "धर्मकाटा", "धर्मकांटा", "तराजू", "काटा कोण", "कांटा कौन", "काटा कौन", "वजन कोण", "वजन कौन", "वजन कसे", "वजन कैसे",
        "वज़न कौन", "वज़न कैसे", "कोण तोलणार", "कौन तौलेगा", "कौन तोलेगा", "तोलणार कोण", "माल कोण तोलणार",
    ],
    "net_amount": [
        "net amount", "net payment", "net proceeds", "net value", "deduction", "deductions", "gross", "hamali", "commission",
        "final amount", "adat", "hath mein kitna", "haath mein kitna", "hath me kitna", "hatat kiti", "kapat", "kapati", "katauti",
        "कपात", "कपाती", "कपातीचे", "कपातीबद्दल", "कटौती", "कटौतियां", "कटौतियाँ", "हमाली", "हमाल", "आडत", "कमीशन", "कमिशन",
        "निव्वळ रक्कम", "निव्वळ", "शुद्ध रकम", "हातात किती", "हाथ में कितना", "नेट अमाउंट", "ग्रॉस",
    ],
    "documents": [
        "documents", "document", "paperwork", "paper work", "written agreement", "in writing", "get in writing", "receipt",
        "bill pavti", "which papers", "what papers", "kagaz", "kagzat", "kagdpatra", "kagadpatre", "dastavej", "dastavez", "likhit",
        "lekhi", "pavti", "raseed", "rasid",
        "कागदपत्र", "कागदपत्रे", "कागज", "कागज़", "कागजात", "दस्तावेज", "दस्तावेज़", "लिखित", "लेखी", "पावती", "रसीद", "रसीदें",
        "बिल पावती",
    ],
    "cannot_do": [
        "what can you do", "what can't you do", "what cant you do", "what you can't do", "what you cannot do", "what can you not do",
        "what are your limits", "your limitations", "limitations", "what do you do", "can you guarantee",
        "tum kya kar sakte", "aap kya kar sakte", "aap kya nahi kar sakte", "tum kya nahi kar sakte", "kya nahi kar sakte",
        "kya kar sakte ho", "kya kar sakta hai", "tu kya karto", "tumhi kay karu shakta", "tumhi kay karu shakat nahi",
        "तुम्ही काय करू शकता", "तुम्ही काय करू शकत नाही", "तू काय करू शकतो", "काय करू शकत नाही", "आप क्या कर सकते", "आप क्या नहीं कर सकते",
        "क्या कर सकते हो", "क्या नहीं कर सकते", "तुम क्या कर सकते", "तुम क्या नहीं कर सकते", "मर्यादा काय", "सीमाएं क्या", "सीमाएँ क्या",
        "कोणत्या गोष्टी करू शकत नाही",
        "तुम्ही कोणत्या गोष्टी करू शकत नाही",
        "करू शकत नाही ते स्पष्ट सांगा",
    ],
}

_PHRASES: dict[str, list[str]] = {
    topic: list(dict.fromkeys(p for p in (normalize_text(x) for x in raw) if p))
    for topic, raw in _RAW_PHRASES.items()
}


def detect_faq(text: str) -> Optional[str]:
    """Return the FAQ topic named in the utterance, or None. Read-only: never changes any session state."""
    norm = normalize_text(text)
    if not norm:
        return None
    padded = f" {norm} "
    for topic in FAQ_TOPICS:
        for phrase in _PHRASES[topic]:
            if f" {phrase} " in padded:
                return topic
    return None


def faq_answer(topic: str, lang: str) -> str:
    """Localised answer (mr / hi / en / hinglish) from replies.py."""
    return ask_text(lang, f"faq_{topic}")