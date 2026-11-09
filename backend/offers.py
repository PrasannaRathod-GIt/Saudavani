import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from config import ADVANCE_PERCENT, DATA_GOV_STATE, DEFAULT_OFFER_VALID_MINUTES
from state import log_deal_event
from replies import ask_text
_skip_answer_fn: Optional[Callable[[str], bool]] = None
_is_no_offer_fn: Optional[Callable[[str, Optional[str]], bool]] = None
_says_buyer_offer_fn: Optional[Callable[[str], bool]] = None
_says_reference_fn: Optional[Callable[[str], bool]] = None
_same_as_reference_fn: Optional[Callable[[str], bool]] = None
_commodity_label_fn: Optional[Callable[[dict[str, Any], str], str]] = None
_quality_summary_fn: Optional[Callable[[dict[str, Any], str], str]] = None


def configure_offer_helpers(
    *,
    skip_answer_fn: Callable[[str], bool],
    is_no_offer_fn: Callable[[str, Optional[str]], bool],
    says_buyer_offer_fn: Callable[[str], bool],
    says_reference_fn: Callable[[str], bool],
    same_as_reference_fn: Callable[[str], bool],
    commodity_label_fn: Callable[[dict[str, Any], str], str],
    quality_summary_fn: Callable[[dict[str, Any], str], str],
) -> None:
    global _skip_answer_fn, _is_no_offer_fn
    global _says_buyer_offer_fn, _says_reference_fn
    global _same_as_reference_fn, _commodity_label_fn
    global _quality_summary_fn

    _skip_answer_fn = skip_answer_fn
    _is_no_offer_fn = is_no_offer_fn
    _says_buyer_offer_fn = says_buyer_offer_fn
    _says_reference_fn = says_reference_fn
    _same_as_reference_fn = same_as_reference_fn
    _commodity_label_fn = commodity_label_fn
    _quality_summary_fn = quality_summary_fn

_PUBLIC_OFFER_FIELDS = (
    "price_per_quintal", "quantity_quintals", "source", "proposed_by",
    "active", "status", "buyer_id", "round", "buyer_confirmed",
    "reported_at", "submitted_at", "proposed_at", "superseded_at",
    "rejected_by", "rejected_at", "expired_at",
)

def _public_offer(offer: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Explicit whitelist: nothing private (farmer target/minimum, internal session data) can ride along."""
    if not offer:
        return None
    out = {k: offer[k] for k in _PUBLIC_OFFER_FIELDS if k in offer}
    out["verified"] = offer.get("source") == "buyer_submitted_offer"
    return out


def public_state(s: dict[str, Any]) -> dict[str, Any]:
    pa = s.get("price_analysis") or {}
    qty = s.get("quantity_quintals")
    cur = s.get("buyer_offer") or {}
    active = cur if (cur and cur.get("active", True) is not False) else None
    price = active.get("price_per_quintal") if active else None
    gross = round(qty * price, 2) if qty and price else None
    # The buyer-side quote/offer (farmer-reported or buyer-submitted) stays visible separately from the farmer's counter.
    original = s.get("original_buyer_offer") or (cur if cur and cur.get("source") != "farmer_counter_offer" else None)
    active_offer = None
    if active:
        src_kind = active.get("source")
        active_offer = {
            "price_per_quintal": price, "quantity_quintals": qty, "gross_value": gross, "source": src_kind,
            "proposed_by": "farmer" if src_kind == "farmer_counter_offer" else "buyer" if src_kind == "buyer_submitted_offer" else "buyer_reported_by_farmer",
            "verified": src_kind == "buyer_submitted_offer", "status": active.get("status") or "active",
            "offer_version": s.get("offer_version"), "expires_at": s.get("offer_expires_at"),
        }
    return {
        "session_id": s["session_id"],
        "farmer_name": s.get("farmer_name"),
        "commodity_id": s.get("commodity_id"),
        "crop": s.get("commodity"),
        "product_form": s.get("product_form"),
        "variety": s.get("variety"),
        "quantity": qty,
        "market": s.get("market"),
        "district": s.get("district"),
        "quality": s.get("quality", {}),
        "deal_status": s.get("deal_status"),
        "waiting_for": s.get("waiting_for"),
        "buyer_offer": _public_offer(original),
        "reported_buyer_quote": _public_offer(original) if (original and original.get("source") == "farmer_reported_buyer_offer") else None,
        "buyer_offer_status": s.get("buyer_offer_status"),
        "active_offer": active_offer,
        "offer_version": s.get("offer_version", 0),
        "farmer_counter_price": s.get("counter_price"),
        "negotiation_rounds": s.get("negotiation_rounds", 0),
        "negotiation_round": s.get("negotiation_rounds", 0),
        "farmer_confirmed": s.get("farmer_confirmed", False),
        "buyer_confirmed": s.get("buyer_confirmed", False),
        "pricing": {
            "source": pa.get("source"),
            "as_of": pa.get("as_of"),
            "market_scope": pa.get("market_scope"),
            "modal_reference": pa.get("modal_reference"),
            "reference_type": pa.get("reference_type"),
            "modal_reference_label": pa.get("modal_reference_label"),
            "market_fallback": pa.get("market_fallback"),
            "variety_fallback": pa.get("variety_fallback"),
            "varieties_combined": pa.get("varieties_combined"),
            "fallback_record": pa.get("fallback_record"),
            "from_cache": pa.get("from_cache"),
            "official_market_modal": pa.get("official_market_modal"),
            "calculated_median_modal": pa.get("calculated_median_modal"),
            "district_median_modal": pa.get("district_median_modal"),
            "lowest_market_min": pa.get("lowest_market_min"),
            "highest_market_max": pa.get("highest_market_max"),
            "modal_spread_low": pa.get("modal_spread_low"),
            "modal_spread_high": pa.get("modal_spread_high"),
            "market_count": pa.get("market_count"),
            "fair_price_low": pa.get("fair_price_low"),
            "fair_price_high": pa.get("fair_price_high"),
            "strong_target_price": pa.get("strong_target_price"),
            "stale": pa.get("stale"),
            "status": pa.get("status"),
            "variety_match": pa.get("variety_match"),
            "market_matched": pa.get("market_matched"),
            "record_count": pa.get("record_count"),
            "gross_value_for_offer": gross,
            "price_unit": "INR per quintal",
        },
        "locked_deal": s.get("voucher"),
        "simulated_escrow": s.get("escrow"),
    }
def _offer_active(s: dict[str, Any]) -> bool:
    """True while a buyer offer is on the table (not superseded by a farmer counter)."""
    offer = s.get("buyer_offer")
    return bool(offer) and offer.get("active", True) is not False


def _submit_farmer_counter(s: dict[str, Any], price: float) -> None:
    """Single path for every farmer counter. The farmer's counter becomes THE active proposed offer (it is what
    the deal card shows, what gross value is computed from and what the buyer must confirm); the original
    buyer quote/offer is preserved separately. Any earlier confirmation is invalidated; the farmer's own
    confirmation of the new counter is recorded, the buyer's stays pending."""
    if s.get("deal_status") in {"LOCKED", "LOCKED_DEMO", "CANCELLED"}:
        raise ValueError(f"Cannot submit a counter while the deal is {s.get('deal_status')}.")
    now = datetime.now(timezone.utc)
    prev = s.get("buyer_offer")
    if prev:
        prev["active"] = False
        prev["status"] = "superseded_by_farmer_counter"
        prev["superseded_at"] = now.isoformat()
        if prev.get("source") != "farmer_counter_offer":
            s["original_buyer_offer"] = dict(prev)  # earlier counters never overwrite the original buyer-side quote
    s["counter_price"] = price
    s["negotiation_rounds"] = int(s.get("negotiation_rounds", 0)) + 1
    s["offer_version"] = int(s.get("offer_version", 0)) + 1
    s["buyer_offer"] = {
        "price_per_quintal": price,
        "quantity_quintals": s.get("quantity_quintals"),
        "source": "farmer_counter_offer",
        "proposed_by": "farmer",
        "verified": False,
        "buyer_confirmed": False,
        "active": True,
        "status": "pending_buyer_response",
        "round": s["negotiation_rounds"],
        "proposed_at": now.isoformat(),
    }
    s["buyer_offer_status"] = "farmer_counter_pending"  # never keeps an old "unavailable"/"verified" value
    s["farmer_confirmed"] = True   # the farmer explicitly proposes/approves this counter
    s["buyer_confirmed"] = False   # pending until the buyer confirms this exact offer version
    s["offer_expires_at"] = (now + timedelta(minutes=DEFAULT_OFFER_VALID_MINUTES)).isoformat()
    s["deal_status"] = "PENDING_BUYER_RESPONSE"
    s["waiting_for"] = None
    s["last_question"] = None
    log_deal_event(s["session_id"], "farmer_counter_submitted", {"counter_price": price, "round": s["negotiation_rounds"], "offer_version": s["offer_version"]})


def _counter_sent_text(s: dict[str, Any], lang: str) -> str:
    price = float(s.get("counter_price") or 0)
    qty = float(s.get("quantity_quintals") or 0)
    return ask_text(lang, "counter_sent", counter=price, qty=qty, total=price * qty)


def _mark_buyer_offer_unavailable(s: dict[str, Any], lang: str, reason: str) -> tuple[str, dict[str, Any]]:
    """Farmer has no buyer offer: store it as unavailable (null), never re-ask, and move on to the farmer's own price."""
    s["buyer_offer"] = None
    s["reported_buyer_quote"] = None
    s["original_buyer_offer"] = None
    s["buyer_offer_status"] = "unavailable"
    s["farmer_confirmed"] = False
    s["buyer_confirmed"] = False
    s["offer_expires_at"] = None
    s["waiting_for"] = "farmer_counter"
    s["last_question"] = "farmer_counter"
    s["deal_status"] = "NEGOTIATING"
    log_deal_event(s["session_id"], "buyer_offer_unavailable", {"reason": reason})
    return ask_text(lang, "buyer_offer_unavailable"), {"event": "buyer_offer_unavailable", "reason": reason}


def _handle_missing_buyer_offer(s: dict[str, Any], text: str, lang: str, prior_wait: Optional[str]) -> tuple[str, dict[str, Any]]:
    """No usable price was given while a buyer offer was requested. Each case is resolved at most once."""
    if prior_wait not in {"buyer_offer", "buyer_offer_clarify"}:  # we only just arrived at this question
        s["last_question"] = "buyer_offer"
        return ask_text(lang, "ask_buyer_offer"), {"event": "asking_buyer_offer"}
    if _skip_answer_fn(text) or _is_no_offer_fn(text, prior_wait):
        return _mark_buyer_offer_unavailable(s, lang, "farmer_does_not_know")
    if prior_wait == "buyer_offer_clarify":
        if _says_buyer_offer_fn(text) and not _says_reference_fn(text):
            s["waiting_for"], s["last_question"] = "buyer_offer", "buyer_offer"
            return ask_text(lang, "ask_buyer_offer"), {"event": "asking_buyer_offer"}
        return _mark_buyer_offer_unavailable(s, lang, "reference_price_only")
    if _same_as_reference_fn(text):
        if s.get("buyer_offer_clarified"):
            return _mark_buyer_offer_unavailable(s, lang, "reference_price_only")
        s["buyer_offer_clarified"] = True
        s["waiting_for"], s["last_question"] = "buyer_offer_clarify", "buyer_offer_clarify"
        ref = (s.get("price_analysis") or {}).get("modal_reference")
        return ask_text(lang, "buyer_offer_clarify", ref=f" (₹{float(ref):,.0f})" if ref else ""), {"event": "buyer_offer_clarify"}
    s["buyer_offer_unclear"] = int(s.get("buyer_offer_unclear", 0)) + 1
    if s["buyer_offer_unclear"] >= 2:
        return _mark_buyer_offer_unavailable(s, lang, "no_clear_offer_given")
    s["last_question"] = "buyer_offer"
    return ask_text(lang, "ask_buyer_offer"), {"event": "asking_buyer_offer"}


def _market_display(s: dict[str, Any]) -> str:
    district = s.get("district") or DATA_GOV_STATE
    return f"{s['market']} ({district})" if s.get("market") else str(district)


def _confirmation_readback(s: dict[str, Any], lang: str) -> str:
    offer = s.get("buyer_offer") or {}
    price = float(offer.get("price_per_quintal") or 0)
    qty = float(s.get("quantity_quintals") or 0)
    return ask_text(
        lang, "confirm_summary", commodity=_commodity_label_fn(s, lang), variety=s.get("variety") or "Not specified",
        qty=qty, market=_market_display(s), quality_summary=_quality_summary_fn(s, lang), price=price, total=qty * price,
    )


def _market_counter_target(s: dict[str, Any], pa: dict[str, Any]) -> tuple[float, bool]:
    """(market-based counter target, whether the farmer's PRIVATE target/minimum is higher than it).
    Only the market-based value may be shown or auto-sent; private values are never revealed or auto-submitted."""
    market_target = float(pa.get("strong_target_price") or pa.get("fair_price_high") or 0)
    private_peak = max(float(s.get("farmer_target_price") or 0), float(s.get("farmer_min_price") or 0))
    return market_target, private_peak > market_target


def _offer_recommendation(s: dict[str, Any], lang: str) -> str:
    offer = (s.get("buyer_offer") or {}).get("price_per_quintal")
    pa = s.get("price_analysis") or {}
    qty = float(s.get("quantity_quintals") or 0)
    if not offer:
        return ask_text(lang, "not_offer")
    total = qty * offer
    if not pa.get("available") or pa.get("stale"):
        # Never claims the offer is fair; the farmer may still accept or counter on their own judgement.
        s["waiting_for"] = "farmer_decision"
        s["last_question"] = "counter_or_accept"
        s["deal_status"] = "NEGOTIATING"
        return ask_text(lang, "offer_stale", offer=offer)
    low = float(pa.get("fair_price_low") or pa.get("modal_reference") or offer)
    high = float(pa.get("fair_price_high") or pa.get("modal_reference") or offer)
    private_minimum = s.get("farmer_min_price")
    market_target, private_higher = _market_counter_target(s, pa)
    if offer < low or (private_minimum is not None and offer < float(private_minimum)):
        s["deal_status"] = "NEGOTIATING"
        if private_higher or not market_target:
            # The farmer's private target/minimum is above the market-based target: it is NEVER spoken or returned here
            # (this text is returned by the unauthenticated voice endpoint). The farmer states the exact counter price.
            s["waiting_for"] = "farmer_counter"
            s["last_question"] = "farmer_counter"
            return ask_text(lang, "offer_below_private", offer=offer)
        s["waiting_for"] = "counter_decision"
        s["last_question"] = "send_counter"
        return ask_text(lang, "offer_below", offer=offer, target=market_target)
    if offer > high:
        s["waiting_for"] = "farmer_confirm"
        s["last_question"] = "confirm_offer"
        s["deal_status"] = "PENDING_FARMER_CONFIRMATION"
        return ask_text(lang, "offer_above", offer=offer, total=total)
    s["waiting_for"] = "farmer_decision"
    s["last_question"] = "counter_or_accept"
    s["deal_status"] = "NEGOTIATING"
    return ask_text(lang, "offer_in_range", offer=offer, total=total)
def _parse_offer_expiry(raw: Any) -> Optional[datetime]:
    """Parse an offer expiry safely. Non-string, blank and malformed values are invalid."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        expiry = datetime.fromisoformat(raw.strip())
    except (TypeError, ValueError, OverflowError):
        return None
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry


def _expire_offer_if_needed(s: dict[str, Any]) -> bool:
    """True when an ACTIVE offer must be invalidated. Fails closed for missing, malformed or past expiry."""
    if not _offer_active(s):
        return False
    expiry = _parse_offer_expiry(s.get("offer_expires_at"))
    return expiry is None or datetime.now(timezone.utc) > expiry


def _reject_offer(s: dict[str, Any], party: str) -> None:
    """Either party rejecting an offer makes it permanently inactive: expiry cleared, both confirmations
    reset, version bumped, and a fresh offer is required. A rejected offer can never be confirmed again."""
    now = datetime.now(timezone.utc).isoformat()
    offer = s.get("buyer_offer")
    if offer:
        offer["active"] = False
        offer["status"] = "rejected"
        offer["rejected_by"] = party
        offer["rejected_at"] = now
        offer["buyer_confirmed"] = False
    s["offer_expires_at"] = None
    s["farmer_confirmed"] = False
    s["buyer_confirmed"] = False
    s["offer_version"] = int(s.get("offer_version", 0)) + 1
    s["buyer_offer_status"] = "rejected"
    s["deal_status"] = "OFFER_REJECTED"
    s["waiting_for"] = "buyer_offer"  # a fresh offer is required
    s["last_question"] = "buyer_offer"
    log_deal_event(s["session_id"], "offer_rejected", {"by": party, "offer_version": s["offer_version"]})


def _expire_offer(s: dict[str, Any], reason: str = "expired") -> None:
    """Invalidate a dead offer exactly once: inactive, status expired, both confirmations reset,
    version +1, fresh offer required. Calling it again on an already-inactive offer does nothing."""
    if s.get("deal_status") in {"LOCKED", "LOCKED_DEMO", "CANCELLED"}:
        return
    offer = s.get("buyer_offer")
    if not offer or offer.get("active", True) is False:
        return  # already inactive: never double-expire / double-increment
    now = datetime.now(timezone.utc).isoformat()
    offer["active"] = False
    offer["status"] = "expired"
    offer["expired_at"] = now
    offer["buyer_confirmed"] = False
    s["offer_expires_at"] = None
    s["farmer_confirmed"] = False
    s["buyer_confirmed"] = False
    s["offer_version"] = int(s.get("offer_version", 0)) + 1
    s["buyer_offer_status"] = "expired"
    s["deal_status"] = "OFFER_EXPIRED"
    s["waiting_for"] = "buyer_offer"
    s["last_question"] = "buyer_offer"
    log_deal_event(s["session_id"], "offer_expired", {"offer_version": s["offer_version"], "reason": reason})


def _expired_reply(lang: str) -> str:
    """Clear expiry message plus the next step (a fresh offer is needed)."""
    return f"{ask_text(lang, 'expired')} {ask_text(lang, 'ask_buyer_offer')}"

ESCROW_SIM_NOTICE = ("SIMULATION ONLY: no real payment service is integrated. Escrow funds are simulated ledger entries; "
                     "actual money transferred is INR 0.")


def _escrow_event(escrow: dict[str, Any], event: str, detail: str) -> None:
    escrow.setdefault("audit_events", []).append({"event": event, "at": datetime.now(timezone.utc).isoformat(), "detail": detail})


def _create_simulated_escrow(s: dict[str, Any], deal: dict[str, Any]) -> dict[str, Any]:
    """Simulated escrow ledger entry created once both parties confirmed the same valid offer."""
    now = datetime.now(timezone.utc).isoformat()
    escrow: dict[str, Any] = {
        "escrow_id": f"SV-ESCROW-{uuid.uuid4().hex[:8].upper()}",
        "is_simulation": True,
        "status": "FUNDS_LOCKED_SIMULATED",
        "simulated_funds_locked": True,
        "simulated_amount_inr": deal.get("gross_amount_inr"),
        "actual_money_transferred_inr": 0,
        "currency": "INR",
        "voucher_id": deal.get("voucher_id"),
        "offer_version": deal.get("offer_version"),
        "created_at": now,
        "funds_locked_at": now,
        "released_at": None,
        "cleared_at": None,
        "notice": ESCROW_SIM_NOTICE,
        "audit_events": [],
    }
    _escrow_event(escrow, "simulated_escrow_created", "Both parties confirmed the same offer version; simulated escrow record created.")
    _escrow_event(escrow, "simulated_funds_locked", f"Simulated funds INR {deal.get('gross_amount_inr')} marked locked. Actual money transferred: INR 0.")
    s["escrow"] = escrow
    log_deal_event(s["session_id"], "simulated_escrow_created", {k: v for k, v in escrow.items() if k != "audit_events"})
    log_deal_event(s["session_id"], "simulated_escrow_funds_locked", {"escrow_id": escrow["escrow_id"], "actual_money_transferred_inr": 0})
    return escrow


def _release_simulated_escrow(s: dict[str, Any], requested_by: str = "system") -> dict[str, Any]:
    escrow = s.get("escrow")
    if not escrow:
        raise ValueError("No simulated escrow exists for this deal.")
    if escrow.get("status") == "RELEASED_SIMULATED":
        return escrow
    if escrow.get("status") != "FUNDS_LOCKED_SIMULATED":
        raise ValueError(f"Simulated escrow cannot be released from status {escrow.get('status')}.")
    now = datetime.now(timezone.utc).isoformat()
    escrow["status"] = "RELEASED_SIMULATED"
    escrow["simulated_funds_locked"] = False
    escrow["released_at"] = now
    escrow["cleared_at"] = now
    escrow["actual_money_transferred_inr"] = 0
    _escrow_event(escrow, "simulated_escrow_released", f"Simulated release/clearance requested by {requested_by}. Actual money transferred: INR 0.")
    log_deal_event(s["session_id"], "simulated_escrow_released", {"escrow_id": escrow["escrow_id"], "requested_by": requested_by, "released_at": now, "actual_money_transferred_inr": 0})
    return escrow


def _lock_deal(s: dict[str, Any], mode: str = "two_party") -> dict[str, Any]:
    if s.get("deal_status") in {"LOCKED", "LOCKED_DEMO"}:
        return s.get("voucher") or {}
    if not s.get("farmer_confirmed"):
        raise ValueError("Farmer has not confirmed the offer.")
    if mode == "two_party" and not s.get("buyer_confirmed"):
        raise ValueError("Buyer confirmation is still pending.")
    offer = s.get("buyer_offer") or {}
    if not offer or offer.get("active", True) is False:
        raise ValueError("There is no active buyer offer (it may have been superseded by a counter).")
    if _expire_offer_if_needed(s):
        _expire_offer(s, "expired_at_lock")   # invalidate, then refuse
        raise ValueError("The buyer offer has expired; a fresh offer is required.")
    price = float(offer.get("price_per_quintal") or 0)
    qty = float(s.get("quantity_quintals") or 0)
    if not s.get("commodity_id") or not s.get("variety") or not s.get("district") or qty <= 0 or price <= 0:
        raise ValueError("Required deal terms are incomplete.")
    gross = round(qty * price, 2)
    advance = round(gross * ADVANCE_PERCENT / 100, 2)
    voucher_id = f"SV-DEAL-{uuid.uuid4().hex[:8].upper()}"
    status = "LOCKED" if mode == "two_party" else "LOCKED_DEMO"
    deal = {
        "status": status,
        "agreement_status": status,
        "voucher_id": voucher_id,
        "commodity_id": s["commodity_id"],
        "commodity": s["commodity"],
        "product_form": s.get("product_form"),
        "variety": s["variety"],
        "quality": s.get("quality", {}),
        "quantity_quintals": qty,
        "unit": "quintal",
        "price_per_quintal": price,
        "gross_amount_inr": gross,
        "deductions_inr": None,
        "net_amount_inr": None,
        "advance_percent_demo_calculation": ADVANCE_PERCENT,
        "advance_amount_demo_estimate_inr": advance,
        "remaining_amount_demo_estimate_inr": round(gross - advance, 2),
        "advance_is_simulated": True,
        "district": s["district"],
        "market": s.get("market") or "District-wide (no specific mandi)",
        "buyer_id": offer.get("buyer_id"),
        "offer_version": s.get("offer_version"),
        "price_reference_date": (s.get("price_analysis") or {}).get("as_of"),
        "price_source": (s.get("price_analysis") or {}).get("source"),
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "money_moved": False,
        "notice": "This is a prototype deal record. No payment or escrow transfer has occurred; advance and remaining amounts are simulated demo calculations.",
    }
    s["voucher"] = deal
    s["deal_status"] = status
    s["waiting_for"] = None
    s["last_question"] = None
    # Consistent final state: the locked offer is no longer "active"; the agreed terms live in the voucher.
    offer["active"] = False
    offer["status"] = "locked" if mode == "two_party" else "locked_demo"
    s["farmer_confirmed"] = True
    if mode == "two_party":
        offer["buyer_confirmed"] = True
        s["buyer_confirmed"] = True
        s["buyer_offer_status"] = "locked"
        _create_simulated_escrow(s, deal)
    else:
        s["buyer_offer_status"] = "locked_demo"
    return deal

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
