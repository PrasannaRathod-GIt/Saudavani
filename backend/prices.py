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
    DATA_GOV_RESOURCE_ID,
    DATA_GOV_STATE,
    DATA_GOV_TIMEOUT,
    DATA_GOV_TRANSPORT,
    IST,
    PRICE_CACHE_SECONDS,
    PRICE_FRESH_DAYS,
    PRICE_MAX_DAYS,
    PRICE_MIN_MANDIS,
    PRICE_STALE_HOURS,  # kept so existing imports never break
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
    """Hours since the START of the record's arrival day (IST). Kept for compatibility and reporting;
    freshness decisions now use whole calendar days."""
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
    """Returns (rows, error_message, error_kind).

    CHANGED: queries EVERY commodity label x district-name variant (capped at DATA_GOV_MAX_ATTEMPTS) and MERGES
    the rows. It no longer stops at the first query that returns anything, because the first hit can be years old
    (e.g. Paddy(Dhan)(Common)) while another label / district spelling (Rice, Aurangabad) holds the recent rows.
    Each row is tagged with the commodity label that was queried (`_query_term`)."""
    if not DATA_GOV_IN_API_KEY:
        return [], "DATA_GOV_IN_API_KEY is not configured.", "not_configured"
    if not district:
        return [], "District is required for the official mandi-price lookup.", "needs_district"

    combos = [(t, d) for t in commodity_terms(commodity_id, product_form) for d in district_variants(district)]
    combos = combos[:max(1, DATA_GOV_MAX_ATTEMPTS)]
    sem = asyncio.Semaphore(3)  # polite to the API; avoids 429s

    async def one(term: str, dist: str) -> tuple[list[dict[str, Any]], Optional[str], Optional[str]]:
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
        async with sem:
            body, error, kind = await _data_gov_request(params)
        if error:
            return [], error, kind
        records = (body or {}).get("records") or (body or {}).get("data") or []
        if not isinstance(records, list):
            return [], "The mandi API returned an unexpected records format.", "invalid_response"
        return [{**r, "_query_term": term} for r in records if isinstance(r, dict)], None, None

    results = await asyncio.gather(*[one(t, d) for t, d in combos])
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    last_error: Optional[str] = None
    last_kind: Optional[str] = None
    for rows, error, kind in results:
        if error:
            last_error, last_kind = error, kind
            continue
        for row in rows:
            key = tuple(str(row.get(k) or "") for k in ("Market", "Commodity", "Variety", "Grade", "Arrival_Date", "Min_Price", "Max_Price", "Modal_Price"))
            merged[key] = row
    if merged:
        return list(merged.values()), None, None
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
        "status": kind,  # needs_district | not_configured | no_records | too_old | too_few_mandis | timeout | auth | ...
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
    treated as duplicates."""
    market, variety = normalize_text(r.get("market", "")), normalize_text(r.get("variety", ""))
    if market:
        return (market, variety)
    return ("", variety, r.get("min_price"), r.get("max_price"), r.get("modal_price"))


def _dedupe_market_variety(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One record per (market, variety). FAQ grade is preferred."""
    ordered = sorted(rows, key=lambda r: (0 if normalize_text(r.get("grade", "")) in {"faq", "fair average quality"} else 1,
                                          normalize_text(r.get("market", "")), normalize_text(r.get("variety", ""))))
    out: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in ordered:
        out.setdefault(_record_key(r), r)
    return list(out.values())


def _collapse_per_market(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per market. Only when a market has several varieties: median of its modals, lowest min, highest max."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for i, r in enumerate(rows):
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
    """True only when the record's variety is the one the farmer requested."""
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


# ---------------------------------------------------------------------------
# NEW: canonical mandi names, per-mandi latest record, nearby districts
# ---------------------------------------------------------------------------

_MANDI_NOISE = {"apmc", "aprmc", "market", "mandi", "samiti", "bazar", "bajar"}


def _mandi_key(name: Any) -> str:
    """Canonical mandi identity: 'APMC Sinner ', 'Sinner APMC' and 'Sinner' are one mandi, and a bracketed
    sub-market such as 'Lasalgaon(Niphad)' / 'Lasalgaon(Vinchur)' is the base mandi 'lasalgaon'."""
    raw = re.sub(r"\(.*?\)", " ", str(name or "")).lower()
    raw = re.sub(r"[^a-z0-9\u0900-\u097f ]+", " ", raw)
    return " ".join(t for t in raw.split() if t not in _MANDI_NOISE)


def _latest_per_mandi(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One record per distinct mandi: that mandi's NEWEST report date; several varieties on that day are collapsed
    to their median. Rows without a mandi name cannot prove a distinct mandi and are skipped."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        key = _mandi_key(r.get("market"))
        if key and r.get("date_obj"):
            groups.setdefault(key, []).append(r)
    out: list[dict[str, Any]] = []
    for key, g in groups.items():
        newest = max(r["date_obj"] for r in g)
        display = key.title()
        day_rows = [{**r, "market": display} for r in g if r["date_obj"] == newest]
        rec = _collapse_per_market(_dedupe_market_variety(day_rows))[0]
        out.append({**rec, "_mandi_key": key, "date_obj": newest})
    return out


_NEARBY: dict[str, list[str]] = {
    "Nashik": ["Ahilyanagar", "Dhule", "Jalgaon"],
    "Pune": ["Ahilyanagar", "Satara", "Solapur"],
    "Chhatrapati Sambhajinagar": ["Jalna", "Jalgaon", "Ahilyanagar"],
    "Ahilyanagar": ["Nashik", "Pune", "Chhatrapati Sambhajinagar"],
    "Jalna": ["Chhatrapati Sambhajinagar", "Beed", "Parbhani"],
    "Beed": ["Chhatrapati Sambhajinagar", "Jalna", "Latur"],
    "Latur": ["Dharashiv", "Beed", "Nanded"],
    "Dharashiv": ["Latur", "Solapur", "Beed"],
    "Solapur": ["Pune", "Dharashiv", "Satara"],
    "Jalgaon": ["Chhatrapati Sambhajinagar", "Dhule", "Nashik"],
    "Dhule": ["Nashik", "Jalgaon", "Nandurbar"],
    "Satara": ["Pune", "Sangli", "Kolhapur"],
    "Sangli": ["Satara", "Kolhapur", "Solapur"],
    "Kolhapur": ["Sangli", "Satara"],
    "Akola": ["Washim", "Buldhana", "Amravati"],
    "Amravati": ["Akola", "Wardha", "Yavatmal"],
    "Nagpur": ["Wardha", "Bhandara", "Amravati"],
    "Parbhani": ["Jalna", "Hingoli", "Nanded"],
    "Nanded": ["Parbhani", "Latur", "Hingoli"],
}


def _prepare_rows(raw_rows: list[dict[str, Any]], commodity_id: str, product_form: Optional[str],
                  district: str) -> tuple[list[dict[str, Any]], Optional[str], Optional[str]]:
    """Normalise and verify commodity, state and district on every row (HTTP 200 proves nothing).
    Returns (rows, fail_kind, fail_message)."""
    normalised = [r for raw in raw_rows if (r := _normalise_market_row(raw)) is not None]
    if not normalised:
        return [], "no_usable_prices", "The API returned no usable modal-price values."
    used_terms = {normalize_text(t) for t in commodity_terms(commodity_id, product_form)}
    rows = [r for r in normalised if normalize_text(r["commodity"]) in used_terms]
    if not rows:
        return [], "commodity_mismatch", "The API returned records for a different commodity than requested."
    state_n = normalize_text(DATA_GOV_STATE)
    rows = [r for r in rows if not r["state"] or normalize_text(r["state"]) == state_n]
    names = {normalize_text(v) for v in district_variants(district)}
    rows = [r for r in rows if normalize_text(r["district"]) in names]
    if not rows:
        return [], "district_mismatch", f"The API returned no records for district {district}."
    return rows, None, None


async def _fetch_nearby_rows(commodity_id: str, product_form: Optional[str], dist: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Rows from neighbouring districts, tagged `_nearby`. Failures are ignored: nearby data only ever adds to an estimate."""
    neighbours = _NEARBY.get(dist, [])[:3]
    if not neighbours:
        return [], []

    async def one(nb: str) -> list[dict[str, Any]]:
        try:
            raw, err, _kind = await _fetch_data_gov_rows(commodity_id, product_form, nb)
            if err or not raw:
                return []
            rows, _k, _m = _prepare_rows(raw, commodity_id, product_form, nb)
            return [{**r, "_nearby": True} for r in rows]
        except Exception:
            log.warning("Nearby-district price fetch failed for %s", nb)
            return []

    parts = await asyncio.gather(*[one(nb) for nb in neighbours])
    return [r for part in parts for r in part], neighbours


async def fetch_mandi_benchmark(
    commodity_id: str,
    market: Optional[str] = None,
    variety: Optional[str] = None,
    product_form: Optional[str] = None,
    district: Optional[str] = None,
) -> dict[str, Any]:
    """Fetch and analyse official daily mandi records. Never invent a price.

    Freshness (calendar days, IST):  0..PRICE_FRESH_DAYS  recent | ..PRICE_MAX_DAYS  shown with age warning
    (stale=True) | older  never a current price.
    Three outcomes: exact recent official record -> actual price; no exact record but >= PRICE_MIN_MANDIS distinct
    mandis -> calculated median ESTIMATE (nearby districts may add mandis, labelled); otherwise unavailable."""
    dist = canonical_district(district)
    if not dist:
        return _price_unavailable("needs_district", "District is required for the official mandi-price lookup.", commodity_id, None, market)

    cache_key = "|".join([DATA_GOV_STATE.lower(), normalize_text(dist), commodity_id, normalize_text(product_form or ""),
                          normalize_text(market or ""), normalize_text(variety or "")])
    cached = PRICE_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < PRICE_CACHE_SECONDS:
        return {**cached[1], "from_cache": True, "cache_age_seconds": int(time.monotonic() - cached[0])}

    try:
        raw_rows, error, kind = await _fetch_data_gov_rows(commodity_id, product_form, dist)
    except Exception:
        log.exception("Unexpected error during mandi-price lookup")
        return _price_unavailable("internal_error", "Unexpected error while retrieving mandi prices.", commodity_id, dist, market)
    if not raw_rows:
        return _price_unavailable(kind or "no_records", error or f"No matching market-price records for {dist}.", commodity_id, dist, market)

    rows, fail_kind, fail_msg = _prepare_rows(raw_rows, commodity_id, product_form, dist)
    if fail_kind:
        return _price_unavailable(fail_kind, fail_msg or "", commodity_id, dist, market)

    used_terms = {normalize_text(t) for t in commodity_terms(commodity_id, product_form)}
    today = datetime.now(IST).date()
    dated = [r for r in rows if r["date_obj"]]
    if not dated:
        return _price_unavailable("no_valid_dates", "The records had no readable arrival dates, so their age cannot be verified.", commodity_id, dist, market)
    future_count = len([r for r in dated if r["date_obj"] > today])
    dated = [r for r in dated if r["date_obj"] <= today]  # future-dated rows are never treated as fresh
    if not dated:
        return _price_unavailable("future_dates", "All records carry arrival dates in the future, so they cannot be trusted.", commodity_id, dist, market)

    newest_any = max(r["date_obj"] for r in dated)
    local = [r for r in dated if (today - r["date_obj"]).days <= PRICE_MAX_DAYS]
    if not local:
        un = _price_unavailable("too_old", f"The newest official record for {dist} is dated {newest_any.strftime('%d/%m/%Y')}, "
                                           f"more than {PRICE_MAX_DAYS} days old, so it is not used as a current price.", commodity_id, dist, market)
        un["newest_record_date"] = newest_any.isoformat()
        un["age_days"] = (today - newest_any).days
        return un

    market_req = None if (not market or _is_any_market(market)) else market
    variety_checked = bool(variety and normalize_text(variety) not in _VARIETY_UNSPECIFIED)
    var_n = normalize_text(variety) if variety_checked else ""

    def pick(pool: list[dict[str, Any]], min_n: int) -> Optional[tuple[list[dict[str, Any]], bool]]:
        """(per-mandi records, variety_matched). Prefers requested-variety rows, then all varieties; prefers
        records within PRICE_FRESH_DAYS, then widens to PRICE_MAX_DAYS (age warning)."""
        attempts: list[tuple[list[dict[str, Any]], bool]] = []
        if variety_checked:
            attempts.append(([r for r in pool if _variety_row_matches(var_n, r["variety"], used_terms)], True))
        attempts.append((pool, False))
        for rows_, vm in attempts:
            if not rows_:
                continue
            recs = _latest_per_mandi(rows_)
            fresh = [r for r in recs if (today - r["date_obj"]).days <= PRICE_FRESH_DAYS]
            if len(fresh) >= min_n:
                return fresh, vm
            if len(recs) >= min_n:
                return recs, vm
        return None

    market_matched: Optional[bool] = None
    chosen: Optional[tuple[list[dict[str, Any]], bool]] = None
    nearby_tried: list[str] = []

    if market_req:
        mk = _mandi_key(market_req)
        exact = [r for r in local if _mandi_key(r["market"]) == mk]
        if exact:
            chosen = pick(exact, 1)
            market_matched = True if chosen else None
        if not chosen:
            market_matched = False  # disclosed to the farmer; other mandis of the district are used

    if not chosen:
        pool = local
        chosen = pick(pool, PRICE_MIN_MANDIS)
        if not chosen:
            nearby_rows, nearby_tried = await _fetch_nearby_rows(commodity_id, product_form, dist)
            nearby_window = [r for r in nearby_rows if r["date_obj"] and r["date_obj"] <= today
                             and (today - r["date_obj"]).days <= PRICE_MAX_DAYS]
            if nearby_window:
                chosen = pick(local + nearby_window, PRICE_MIN_MANDIS)
        if not chosen and len(_latest_per_mandi(local)) == 1:
            chosen = pick(local, 1)  # a district with exactly one reporting mandi: that real record, labelled as such
        if not chosen:
            n_found = len(_latest_per_mandi(local))
            un = _price_unavailable("too_few_mandis",
                                    f"Only {n_found} recent mandi record(s) found for {dist}; at least {PRICE_MIN_MANDIS} "
                                    f"distinct mandis are needed for an estimate.", commodity_id, dist, market)
            un["newest_record_date"] = newest_any.isoformat()
            return un

    per_market, variety_matched = chosen
    n_markets = len(per_market)
    market_modals = [r["modal_price"] for r in per_market]
    market_mins = [r["min_price"] for r in per_market if r["min_price"] is not None]
    market_maxs = [r["max_price"] for r in per_market if r["max_price"] is not None]
    spread_low, spread_high = min(market_modals), max(market_modals)
    lowest_market_min = min(market_mins) if market_mins else None
    highest_market_max = max(market_maxs) if market_maxs else None
    combined = max((r.get("_varieties_combined", 1) for r in per_market), default=1)
    variety_fallback = bool(variety_checked and not variety_matched)
    market_fallback = market_matched is False
    nearby_districts = sorted({r["district"] for r in per_market if r.get("_nearby") and r.get("district")})

    newest_date = max(r["date_obj"] for r in per_market)
    oldest_date = min(r["date_obj"] for r in per_market)
    age_days = (today - oldest_date).days  # conservative: the OLDEST record used decides freshness
    stale = age_days > PRICE_FRESH_DAYS
    age_hours = _record_age_hours(oldest_date)

    scope = f"{dist} district"
    if market_matched:
        scope = f"{per_market[0]['market']} market, {dist} district"
    official_market_modal: Optional[float] = None
    calculated_median: Optional[float] = None
    fallback_record: Optional[dict[str, Any]] = None

    if n_markets > 1 or combined > 1:
        reference_type = "calculated_median"  # computed by SaudaVani: an estimate, never an official mandi modal
        if n_markets > 1:
            modal = statistics.median(market_modals)
            if nearby_districts:
                scope = f"{dist} district and nearby ({', '.join(nearby_districts)}) - estimate"
        else:
            modal = per_market[0]["modal_price"]
            spread_low, spread_high = per_market[0].get("_modal_low", modal), per_market[0].get("_modal_high", modal)
            scope = f"{per_market[0]['market']} market, {per_market[0]['district'] or dist} district"
        calculated_median = modal
        fair_low, fair_high = spread_low, spread_high
        range_method = "modal spread (lowest to highest modal price used)"
    else:
        rec = per_market[0]
        modal = rec["modal_price"]
        fair_low = min(rec["min_price"] if rec["min_price"] is not None else modal, modal)
        fair_high = max(rec["max_price"] if rec["max_price"] is not None else modal, modal)
        range_method = "reported min-max of this record"
        scope = f"{rec['market']} market, {rec['district'] or dist} district"
        if variety_fallback or market_fallback or rec.get("_nearby"):
            reference_type = "fallback_record"
            fallback_record = {"market": rec["market"], "variety": rec["variety"], "modal_price": modal,
                               "min_price": rec["min_price"], "max_price": rec["max_price"]}
        else:
            reference_type = "market_actual"
            official_market_modal = modal
    strong_target = fair_high

    by_date: dict[str, list[float]] = {}
    for day in sorted({r["date_obj"] for r in local})[-7:]:
        day_rows = _collapse_per_market(_dedupe_market_variety(
            [{**r, "market": _mandi_key(r["market"]).title() or r["market"]} for r in local if r["date_obj"] == day]))
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
        "as_of": oldest_date.isoformat(),
        "as_of_display": oldest_date.strftime("%d/%m/%Y"),
        "newest_record_date": newest_date.isoformat(),
        "oldest_record_date": oldest_date.isoformat(),
        "age_hours": round(age_hours, 1),
        "age_days": age_days,
        "freshness": "age_warning" if stale else "recent",
        "stale": stale,
        "stale_after_hours": PRICE_FRESH_DAYS * 24,
        "fresh_days_limit": PRICE_FRESH_DAYS,
        "max_days_limit": PRICE_MAX_DAYS,
        "future_dated_records_ignored": future_count,
        "record_count": n_markets,
        "comparison_record_count": n_markets,
        "market_count": n_markets,
        "nearby_used": bool(nearby_districts),
        "nearby_districts": nearby_districts,
        "is_estimate": reference_type == "calculated_median",
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