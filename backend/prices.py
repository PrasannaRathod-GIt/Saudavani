import asyncio
import json
import logging
import os
import re
import shutil
import statistics
import subprocess
import time
from datetime import date, datetime, timezone, time as dtime
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlencode

import httpx

from config import (
    DATA_GOV_API_URL,
    DATA_GOV_CURL_URL_IN_ARGS,
    DATA_GOV_IN_API_KEY,
    DATA_GOV_LIMIT,
    DATA_GOV_MAX_ATTEMPTS,
    DATA_GOV_RESOURCE_ID,  # ADD THIS
    DATA_GOV_STATE,
    DATA_GOV_TIMEOUT,
    DATA_GOV_TRANSPORT,
    IST,
    PRICE_CACHE_SECONDS,
    PRICE_STALE_HOURS,
)
from catalog import COMMODITIES
from state import PRICE_CACHE
from text_utils import normalize_text, canonical_district, district_variants

log = logging.getLogger("saudavani")

_commodity_terms_fn: Optional[Callable[..., list[str]]] = None
_is_any_market_fn: Optional[Callable[[Any], bool]] = None


def configure_price_helpers(
    commodity_terms_fn: Callable[..., list[str]],
    is_any_market_fn: Callable[[Any], bool],
) -> None:
    global _commodity_terms_fn, _is_any_market_fn
    _commodity_terms_fn = commodity_terms_fn
    _is_any_market_fn = is_any_market_fn


def commodity_terms(
    commodity_id: str,
    product_form: Optional[str] = None,
) -> list[str]:
    if _commodity_terms_fn is None:
        raise RuntimeError("Price helpers have not been configured.")
    return _commodity_terms_fn(commodity_id, product_form)


def _is_any_market(value: Any) -> bool:
    if _is_any_market_fn is None:
        raise RuntimeError("Price helpers have not been configured.")
    return _is_any_market_fn(value)

_CURL_MARKER = "__HTTP_STATUS__:"


def _find_curl() -> Optional[str]:
    """curl.exe on Windows, curl on Linux/macOS. CURL_BIN can override."""
    override = os.getenv("CURL_BIN", "").strip()
    if override:
        return shutil.which(override) or (override if Path(override).exists() else None)
    for name in (["curl.exe", "curl"] if os.name == "nt" else ["curl"]):
        found = shutil.which(name)
        if found:
            return found
    return None


def _norm_market_value(value: Any) -> str:
    return normalize_text(str(value or ""))


def _parse_market_date(value: Any) -> Optional[date]:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.split()[0] if " " in raw and "T" not in raw else raw
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%y", "%d-%m-%y", "%d-%b-%Y"):
        for candidate in (raw, raw[:10]):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _record_age_hours(latest: date) -> float:
    """Hours since the START of the record's arrival day (IST). The dataset has dates, not publish
    timestamps, so the age is measured conservatively from 00:00 of that day (never optimistic)."""
    start_of_day = datetime.combine(latest, dtime.min, tzinfo=IST)
    return max(0.0, (datetime.now(IST) - start_of_day).total_seconds() / 3600.0)


def _float_or_none(value: Any) -> Optional[float]:
    try:
        n = float(str(value).replace(",", "").strip())
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _run_curl(curl_bin: str, url: str) -> tuple[int, str, str]:
    """Blocking curl call (run via asyncio.to_thread). By default the URL - which contains the API key -
    is passed on stdin via a curl config so it never appears in the process list."""
    base = [curl_bin, "-sS", "--max-time", str(DATA_GOV_TIMEOUT), "-H", "Accept: application/json",
            "-w", f"\n{_CURL_MARKER}%{{http_code}}"]
    if DATA_GOV_CURL_URL_IN_ARGS:
        cmd, stdin = base + [url], None
    else:
        cmd, stdin = base + ["-K", "-"], f'url = "{url}"\n'.encode("utf-8")
    proc = subprocess.run(cmd, input=stdin, capture_output=True, timeout=DATA_GOV_TIMEOUT + 5, check=False)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


async def _data_gov_request(params: dict[str, str]) -> tuple[Optional[dict[str, Any]], Optional[str], Optional[str]]:
    """One request. Returns (json_body, error_message, error_kind). Never logs the URL or key."""
    transport = DATA_GOV_TRANSPORT
    curl_bin = _find_curl() if transport in {"auto", "curl"} else None
    if transport == "curl" and not curl_bin:
        return None, "curl was not found on this machine. Install curl or set DATA_GOV_TRANSPORT=httpx.", "transport"
    status: Optional[int] = None
    text = ""
    if curl_bin:
        url = f"{DATA_GOV_API_URL}?{urlencode(params)}"
        try:
            rc, out, _err = await asyncio.to_thread(_run_curl, curl_bin, url)
        except subprocess.TimeoutExpired:
            return None, "The mandi-price request timed out.", "timeout"
        except OSError:
            log.warning("Could not start curl for the mandi-price request")
            return None, "Could not start curl for the mandi-price request.", "transport"
        if rc == 28:
            return None, "The mandi-price request timed out.", "timeout"
        if rc != 0 or _CURL_MARKER not in out:
            log.warning("curl mandi-price request failed (exit code %s)", rc)
            return None, "Could not connect to the data.gov.in mandi-price service.", "connection"
        text, status_text = out.rsplit(_CURL_MARKER, 1)
        try:
            status = int(status_text.strip())
        except ValueError:
            return None, "The mandi-price service returned an unreadable status.", "invalid_response"
    else:
        try:
            async with httpx.AsyncClient(timeout=float(DATA_GOV_TIMEOUT)) as client:
                resp = await client.get(DATA_GOV_API_URL, params=params, headers={"Accept": "application/json"})
            status, text = resp.status_code, resp.text
        except httpx.TimeoutException:
            return None, "The mandi-price request timed out.", "timeout"
        except Exception as exc:  # message deliberately not logged: httpx errors can embed the URL
            log.warning("httpx mandi-price request failed (%s)", type(exc).__name__)
            return None, "Could not connect to the data.gov.in mandi-price service.", "connection"

    if status in (401, 403):
        return None, f"data.gov.in rejected the API key or access (HTTP {status}).", "auth"
    if status == 429:
        return None, "data.gov.in rate limit reached (HTTP 429). Try again shortly.", "rate_limit"
    if status != 200:
        return None, f"data.gov.in returned HTTP {status}.", "http_error"
    try:
        body = json.loads(text)
    except ValueError:
        return None, "The mandi API returned invalid JSON.", "invalid_json"
    if not isinstance(body, dict):
        return None, "Unexpected response format from the mandi API.", "invalid_response"
    if str(body.get("status", "")).lower() == "error" or (body.get("error") and not body.get("records")):
        return None, "The mandi API rejected the requested filters.", "api_error"
    return body, None, None


async def _fetch_data_gov_rows(
    commodity_id: str,
    product_form: Optional[str] = None,
    district: Optional[str] = None,
) -> tuple[list[dict[str, Any]], Optional[str], Optional[str]]:
    """Returns (rows, error_message, error_kind). Each row is tagged with the commodity label that was
    queried (`_query_term`). Tries district-name variants x commodity labels until one returns records."""
    if not DATA_GOV_IN_API_KEY:
        return [], "DATA_GOV_IN_API_KEY is not configured.", "not_configured"
    if not district:
        return [], "District is required for the official mandi-price lookup.", "needs_district"

    attempts = 0
    last_error: Optional[str] = None
    last_kind: Optional[str] = None
    for term in commodity_terms(commodity_id, product_form):
        for dist in district_variants(district):
            if attempts >= DATA_GOV_MAX_ATTEMPTS:
                break
            attempts += 1
            params = {
                "api-key": DATA_GOV_IN_API_KEY,
                "format": "json",
                "limit": str(DATA_GOV_LIMIT),
                "offset": "0",
                "filters[State]": DATA_GOV_STATE,
                "filters[District]": dist,
                "filters[Commodity]": term,
                "sort[Arrival_Date]": "desc",
            }
            body, error, kind = await _data_gov_request(params)
            if error:
                last_error, last_kind = error, kind
                if kind in {"auth", "timeout", "connection", "transport", "rate_limit"}:
                    return [], error, kind  # retrying other filters will not help
                continue
            records = body.get("records") or body.get("data") or [] if body else []
            if not isinstance(records, list):
                last_error, last_kind = "The mandi API returned an unexpected records format.", "invalid_response"
                continue
            valid = [{**r, "_query_term": term} for r in records if isinstance(r, dict)]
            if valid:
                unique: dict[tuple[str, ...], dict[str, Any]] = {}
                for row in valid:
                    key = tuple(str(row.get(k) or "") for k in ("Market", "Commodity", "Variety", "Grade", "Arrival_Date", "Min_Price", "Max_Price", "Modal_Price"))
                    unique[key] = row
                return list(unique.values()), None, None
    if last_error:
        return [], last_error, last_kind
    return [], f"No official records were returned for {district}.", "no_records"


def _normalise_market_row(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    # data.gov.in returns capitalised names (Modal_Price); older feeds use lower-case. Accept both.
    lowered = {str(k).lower(): v for k, v in row.items()}
    get = lambda *keys: next((lowered.get(k.lower()) for k in keys if lowered.get(k.lower()) not in (None, "")), None)
    modal = _float_or_none(get("modal_price", "modal price"))
    minimum = _float_or_none(get("min_price", "minimum_price"))
    maximum = _float_or_none(get("max_price", "maximum_price"))
    if modal is None:  # never invent a modal price
        return None
    raw_date = get("arrival_date", "date")
    return {
        "state": str(get("state") or ""),
        "district": str(get("district") or ""),
        "market": str(get("market") or ""),
        "commodity": str(get("commodity") or ""),
        "variety": str(get("variety") or ""),
        "grade": str(get("grade") or ""),
        "arrival_date": str(raw_date or ""),
        "date_obj": _parse_market_date(raw_date),
        "min_price": minimum,
        "max_price": maximum,
        "modal_price": modal,
        "unit": "INR/quintal",
        "_query_term": row.get("_query_term"),
    }


def percentile(values: list[float], p: float) -> Optional[float]:
    if not values:
        return None
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    idx = (len(vals) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def _price_unavailable(kind: str, error: str, commodity_id: str, district: Optional[str], market: Optional[str]) -> dict[str, Any]:
    return {
        "available": False,
        "status": kind,  # needs_district | not_configured | no_records | timeout | auth | ... (missing data, not stale data)
        "source": "data.gov.in / AGMARKNET",
        "error": error,
        "message": "Price data unavailable",
        "commodity": COMMODITIES[commodity_id]["name"],
        "district": district,
        "market_requested": market,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def _record_key(r: dict[str, Any]) -> tuple[Any, ...]:
    """Identity of a record for de-duplication. A named market is identified by (market, variety). When the market
    name is MISSING it cannot identify the record, so only rows with identical variety AND identical prices are
    treated as duplicates (never an object id, which made duplicates of unnamed rows count twice)."""
    market, variety = normalize_text(r.get("market", "")), normalize_text(r.get("variety", ""))
    if market:
        return (market, variety)
    return ("", variety, r.get("min_price"), r.get("max_price"), r.get("modal_price"))


def _dedupe_market_variety(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One record per (market, variety): duplicate API rows never count twice, also when market/variety are missing.
    FAQ grade is preferred."""
    ordered = sorted(rows, key=lambda r: (0 if normalize_text(r.get("grade", "")) in {"faq", "fair average quality"} else 1,
                                          normalize_text(r.get("market", "")), normalize_text(r.get("variety", ""))))
    out: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in ordered:
        out.setdefault(_record_key(r), r)
    return list(out.values())


def _collapse_per_market(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per market. Only when a market has several varieties (variety fallback / unknown variety):
    median of its modals, lowest min, highest max."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for i, r in enumerate(rows):
        # Rows without a market name stay separate (already de-duplicated); they are never merged under a made-up market.
        groups.setdefault(normalize_text(r["market"]) or f"unknown-market-{i}", []).append(r)
    out: list[dict[str, Any]] = []
    for g in groups.values():
        if len(g) == 1:
            out.append(g[0])
            continue
        mins = [r["min_price"] for r in g if r["min_price"] is not None]
        maxs = [r["max_price"] for r in g if r["max_price"] is not None]
        modals_g = [r["modal_price"] for r in g]
        out.append({**g[0], "modal_price": statistics.median(modals_g),
                    "min_price": min(mins) if mins else None, "max_price": max(maxs) if maxs else None, "variety": "Multiple varieties",
                    "_varieties_combined": len(g), "_modal_low": min(modals_g), "_modal_high": max(modals_g)})
    return out


_VARIETY_UNSPECIFIED = {"other not sure", "other local", "not sure"}
_LOCAL_VARIETY_KEYS = {"local gavran", "local variety"}
_LOCAL_VARIETY_TOKENS = {"local", "gavran", "gavaran", "gavrani"}
_GENERIC_RECORD_VARIETIES = {"", "other", "others", "na", "n a", "not specified", "unknown", "none"}


def _variety_row_matches(requested_norm: str, record_variety: str, commodity_names: set[str]) -> bool:
    """True only when the record's variety is the one the farmer requested. 'Local/Gavran' and 'Local variety'
    are real requested varieties: they match only records that are themselves labelled local/gavran. Word-based,
    so 'maize' never matches 'yellow maize' and a bare 'Local' record never stands in for 'Pink/local onion'."""
    rec = normalize_text(record_variety)
    if rec in _GENERIC_RECORD_VARIETIES or rec in commodity_names:
        return False
    rec_tokens, req_tokens = set(rec.split()), set(requested_norm.split())
    if requested_norm in _LOCAL_VARIETY_KEYS:
        return bool(rec_tokens & _LOCAL_VARIETY_TOKENS)
    if rec_tokens <= (_LOCAL_VARIETY_TOKENS | {"variety"}):
        return False
    compact = lambda t: re.sub(r"[^a-z0-9\u0900-\u097f]", "", t)
    return req_tokens <= rec_tokens or rec_tokens <= req_tokens or compact(requested_norm) == compact(rec)


async def fetch_mandi_benchmark(
    commodity_id: str,
    market: Optional[str] = None,
    variety: Optional[str] = None,
    product_form: Optional[str] = None,
    district: Optional[str] = None,
) -> dict[str, Any]:
    """Fetch and analyse official daily mandi records. Never invent a fallback price."""
    dist = canonical_district(district)
    if not dist:
        return _price_unavailable("needs_district", "District is required for the official mandi-price lookup.", commodity_id, None, market)

    cache_key = "|".join([DATA_GOV_STATE.lower(), normalize_text(dist), commodity_id, normalize_text(product_form or ""),
                          normalize_text(market or ""), normalize_text(variety or "")])
    cached = PRICE_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < PRICE_CACHE_SECONDS:
        return {**cached[1], "from_cache": True, "cache_age_seconds": int(time.monotonic() - cached[0])}  # never passed off as a fresh fetch

    try:
        rows, error, kind = await _fetch_data_gov_rows(commodity_id, product_form, dist)
    except Exception:
        log.exception("Unexpected error during mandi-price lookup")
        return _price_unavailable("internal_error", "Unexpected error while retrieving mandi prices.", commodity_id, dist, market)
    if not rows:
        return _price_unavailable(kind or "no_records", error or f"No matching market-price records for {dist}.", commodity_id, dist, market)

    normalised = [r for raw in rows if (r := _normalise_market_row(raw)) is not None]
    if not normalised:
        return _price_unavailable("no_usable_prices", "The API returned no usable modal-price values.", commodity_id, dist, market)

    # HTTP 200 is not proof the filters worked: verify commodity, state and district on every row.
    used_terms = {normalize_text(t) for t in commodity_terms(commodity_id, product_form)}
    commodity_rows = [r for r in normalised if normalize_text(r["commodity"]) in used_terms]
    if not commodity_rows:
        return _price_unavailable("commodity_mismatch", "The API returned records for a different commodity than requested.", commodity_id, dist, market)
    state_n = normalize_text(DATA_GOV_STATE)
    commodity_rows = [r for r in commodity_rows if not r["state"] or normalize_text(r["state"]) == state_n]
    district_names = {normalize_text(v) for v in district_variants(dist)}
    district_rows = [r for r in commodity_rows if normalize_text(r["district"]) in district_names]
    if not district_rows:
        return _price_unavailable("district_mismatch", f"The API returned no records for district {dist}.", commodity_id, dist, market)

    # Market (mandi) is a separate, optional filter applied AFTER the district query. "Any market" is never
    # searched as a literal APMC name: it means all markets in the district.
    market_req = None if (not market or _is_any_market(market)) else market
    chosen = district_rows
    market_matched: Optional[bool] = None
    scope = f"{dist} district"
    if market_req:
        market_n = normalize_text(market_req)
        # EXACT (normalised) market name only. A partial/substring match (e.g. "Khed" vs "Khed(Chakan)") is never
        # reported as the requested market: it falls back to the district-wide records and is disclosed as such.
        exact = [r for r in district_rows if r["market"] and market_n == normalize_text(r["market"])]
        if exact:
            chosen, market_matched = exact, True
            scope = f"{market_req} market, {dist} district"
        else:
            market_matched = False  # disclosed to the farmer (market_note); other markets of the same district are used

    variety_matched = False
    variety_checked = False
    if variety and normalize_text(variety) not in _VARIETY_UNSPECIFIED:
        variety_checked = True  # includes Local/Gavran and Local variety: they are real requested varieties
        var_n = normalize_text(variety)
        var_rows = [r for r in chosen if _variety_row_matches(var_n, r["variety"], used_terms)]
        if var_rows:
            chosen, variety_matched = var_rows, True
        # else: no variety premium is invented; other varieties of the same commodity are used and the mismatch is flagged.

    dated = [r for r in chosen if r["date_obj"]]
    if not dated:
        return _price_unavailable("no_valid_dates", "The records had no readable arrival dates, so their age cannot be verified.", commodity_id, dist, market)
    today_ist = datetime.now(IST).date()
    future_count = len([r for r in dated if r["date_obj"] > today_ist])
    dated = [r for r in dated if r["date_obj"] <= today_ist]  # future-dated rows are never treated as fresh
    if not dated:
        return _price_unavailable("future_dates", "All records carry arrival dates in the future, so they cannot be trusted.", commodity_id, dist, market)
    chosen = dated
    latest_date = max(r["date_obj"] for r in dated)  # parsed dates, never string order
    # Only records of the same commodity + district + latest report date are compared; no duplicates.
    latest_rows = _dedupe_market_variety([r for r in dated if r["date_obj"] == latest_date])
    per_market = _collapse_per_market(latest_rows)
    n_markets = len(per_market)
    market_modals = [r["modal_price"] for r in per_market]
    market_mins = [r["min_price"] for r in per_market if r["min_price"] is not None]
    market_maxs = [r["max_price"] for r in per_market if r["max_price"] is not None]
    spread_low, spread_high = min(market_modals), max(market_modals)
    lowest_market_min = min(market_mins) if market_mins else None
    highest_market_max = max(market_maxs) if market_maxs else None
    combined = max((r.get("_varieties_combined", 1) for r in per_market), default=1)  # >1: several varieties of one market merged
    variety_fallback = bool(variety_checked and not variety_matched)
    market_fallback = market_matched is False
    official_market_modal: Optional[float] = None
    calculated_median: Optional[float] = None
    fallback_record: Optional[dict[str, Any]] = None
    if n_markets > 1 or combined > 1:
        # A value computed by SaudaVani from several records: never an official mandi modal.
        reference_type = "calculated_median"
        if n_markets > 1:
            modal = statistics.median(market_modals)
        else:
            modal = per_market[0]["modal_price"]  # median of this market's variety modals
            spread_low, spread_high = per_market[0].get("_modal_low", modal), per_market[0].get("_modal_high", modal)
            if per_market[0]["market"]:
                scope = f"{per_market[0]['market']} market, {dist} district"
        calculated_median = modal
        fair_low, fair_high = spread_low, spread_high
        range_method = "modal spread (lowest to highest modal price used)"
    else:
        rec = per_market[0]
        modal = rec["modal_price"]
        fair_low = min(rec["min_price"] if rec["min_price"] is not None else modal, modal)
        fair_high = max(rec["max_price"] if rec["max_price"] is not None else modal, modal)
        range_method = "reported min-max of this record"
        if rec["market"]:
            scope = f"{rec['market']} market, {dist} district"
        if variety_fallback or market_fallback:
            # One real record, but NOT for the farmer's requested variety and/or market.
            reference_type = "fallback_record"
            fallback_record = {"market": rec["market"], "variety": rec["variety"], "modal_price": modal,
                               "min_price": rec["min_price"], "max_price": rec["max_price"]}
        else:
            reference_type = "market_actual"  # exact commodity + variety (+ market): the actual reported modal
            official_market_modal = modal
    strong_target = fair_high

    age_hours = _record_age_hours(latest_date)
    stale = age_hours > PRICE_STALE_HOURS

    # Trend uses the same de-duplicated, one-per-market records as the latest-day comparison (never raw API rows).
    by_date: dict[str, list[float]] = {}
    for day in sorted({r["date_obj"] for r in dated})[-7:]:
        day_rows = _collapse_per_market(_dedupe_market_variety([r for r in dated if r["date_obj"] == day]))
        by_date[day.isoformat()] = [r["modal_price"] for r in day_rows]
    trend = [{"date": d, "modal_median": round(statistics.median(v), 2)} for d, v in sorted(by_date.items())]

    result = {
        "available": True,
        "status": "stale" if stale else "ok",
        "source": "data.gov.in — AGMARKNET variety-wise daily market prices",
        "source_url": f"https://www.data.gov.in/resource/{DATA_GOV_RESOURCE_ID}",
        "commodity": COMMODITIES[commodity_id]["name"],
        "district": dist,
        "market_requested": market_req,
        "market_matched": market_matched,
        "market_scope": scope,
        "matched_markets": sorted(set(r["market"] for r in per_market if r["market"]))[:15],
        "variety_requested": variety,
        "variety_match": variety_matched if variety_checked else None,
        "as_of": latest_date.isoformat(),
        "as_of_display": latest_date.strftime("%d/%m/%Y"),
        "age_hours": round(age_hours, 1),
        "age_days": round(age_hours / 24, 1),
        "stale": stale,
        "stale_after_hours": PRICE_STALE_HOURS,
        "future_dated_records_ignored": future_count,
        "record_count": len(latest_rows),
        "comparison_record_count": n_markets,
        "market_count": n_markets,
        "reference_type": reference_type,
        "modal_reference_label": {"market_actual": "actual_market_modal", "calculated_median": "calculated_median_not_official_modal",
                                  "fallback_record": "fallback_record_not_requested_variety_or_market"}[reference_type],
        "market_fallback": market_fallback,
        "variety_fallback": variety_fallback,
        "varieties_combined": combined,
        "official_market_modal": round(official_market_modal, 2) if official_market_modal is not None else None,
        "calculated_median_modal": round(calculated_median, 2) if calculated_median is not None else None,
        "district_median_modal": round(calculated_median, 2) if (calculated_median is not None and n_markets > 1 and not market_matched) else None,
        "fallback_record": fallback_record,
        "from_cache": False,
        "lowest_market_min": lowest_market_min,
        "highest_market_max": highest_market_max,
        "modal_spread_low": round(spread_low, 2),
        "modal_spread_high": round(spread_high, 2),
        "latest_min_price": lowest_market_min,
        "latest_max_price": highest_market_max,
        "modal_reference": round(modal, 2),
        "fair_price_low": round(fair_low, 2),
        "fair_price_high": round(fair_high, 2),
        "strong_target_price": round(strong_target, 2),
        "range_method": range_method,
        "price_unit": "INR per quintal",
        "trend": trend,
        "quality_premium_applied": False,
        "quality_note": "The farmer's answers are self-reported intake only. DMI/e-NAM publishes commodity-specific quality parameters; no numerical grade or premium is applied without an assay result and comparable grade-specific prices.",
        "quality_standard_source": "https://enam.gov.in/commodity/commodity-quality",
        "quality_assay_required_for_certified_grade": True,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "records": [
            {k: r[k] for k in ("state", "district", "market", "commodity", "variety", "grade", "arrival_date", "min_price", "max_price", "modal_price")}
            for r in sorted(per_market, key=lambda x: normalize_text(x["market"]))
        ],
    }
    if len(PRICE_CACHE) > 200:
        PRICE_CACHE.clear()
    PRICE_CACHE[cache_key] = (time.monotonic(), result)  # only successful lookups are cached
    return result
