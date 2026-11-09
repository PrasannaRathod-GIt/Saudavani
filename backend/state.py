import asyncio
import json
import logging
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Optional

from config import DB_PATH, DATA_GOV_STATE

log = logging.getLogger("saudavani")
SESSIONS: dict[str, dict[str, Any]] = {}
SESSION_LOCKS: dict[str, asyncio.Lock] = {}
PRICE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def session_lock(session_id: str) -> asyncio.Lock:
    return SESSION_LOCKS.setdefault(session_id, asyncio.Lock())


def new_session(session_id: str, farmer_name: Optional[str] = None) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "farmer_name": farmer_name or "Farmer",
        "farmer_id": f"F-{uuid.uuid4().hex[:8].upper()}",
        "state": DATA_GOV_STATE,
        "commodity_id": None,
        "commodity": None,
        "product_form": None,
        "variety": None,
        "quantity_quintals": None,
        "market": None,
        "market_skipped": False,
        "district": None,
        "quality": {},
        "waiting_for": "commodity",
        "last_question": "commodity",
        "selling_started": False,
        "mode": "explore",
        "no_offer": False,
        "hold": False,
        "farmer_desired_price": None,
        "reply_lang": None,
        "draft_offer": None,
        "mode": "explore",
        "no_offer": False,
        "hold": False,
        "farmer_desired_price": None,
        "reply_lang": None,
        "draft_offer": None,
        "info_query": None,
        "lang": "mr",
        "lang_hint": None,
        "counter_unclear": 0,
        "price_analysis": None,
        "price_status": "not_requested",
        "buyer_offer": None,
        "farmer_target_price": None,
        "farmer_min_price": None,
        "counter_price": None,
        "negotiation_rounds": 0,
        "offer_version": 0,
        "offer_expires_at": None,
        "farmer_confirmed": False,
        "buyer_confirmed": False,
        "escrow": None,
        "reported_buyer_quote": None,
        "original_buyer_offer": None,
        "buyer_offer_status": None,
        "buyer_offer_clarified": False,
        "buyer_offer_unclear": 0,
        "deal_status": "GATHERING_DETAILS",
        "voucher": None,
        "history": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

def db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(db_connect()) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions "
            "(session_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS deal_events "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, "
            "event TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.commit()


def load_session(session_id: str, farmer_name: Optional[str] = None) -> dict[str, Any]:
    if session_id in SESSIONS:
        s = SESSIONS[session_id]
        if farmer_name:
            s["farmer_name"] = farmer_name
        return s

    row = None
    try:
        with closing(db_connect()) as conn:
            row = conn.execute(
                "SELECT payload FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
    except sqlite3.Error:
        log.exception("Could not read session from SQLite; starting a fresh session")

    if row:
        try:
            s = json.loads(row["payload"])
            if not isinstance(s, dict):
                raise ValueError("payload is not an object")
        except (json.JSONDecodeError, TypeError, ValueError):
            s = new_session(session_id, farmer_name)
    else:
        s = new_session(session_id, farmer_name)

    for key, default in new_session(session_id, farmer_name).items():
        s.setdefault(key, default)

    s["session_id"] = session_id

    if farmer_name:
        s["farmer_name"] = farmer_name

    SESSIONS[session_id] = s
    save_session(s)
    return s


def save_session(s: dict[str, Any]) -> None:
    s["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        payload = json.dumps(
            s,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )

        with closing(db_connect()) as conn:
            conn.execute(
                "INSERT INTO sessions(session_id,payload,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "payload=excluded.payload, updated_at=excluded.updated_at",
                (s["session_id"], payload, s["updated_at"]),
            )
            conn.commit()

    except Exception:
        log.exception("Could not persist session %s", s.get("session_id"))


def peek_session(session_id: str) -> Optional[dict[str, Any]]:
    """Read-only lookup. Never creates or saves a session."""

    cached = SESSIONS.get(session_id)
    if cached is not None:
        return cached

    try:
        with closing(db_connect()) as conn:
            row = conn.execute(
                "SELECT payload FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
    except sqlite3.Error:
        log.exception("Could not read session from SQLite")
        return None

    if not row:
        return None

    try:
        s = json.loads(row["payload"])
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(s, dict):
        return None

    for key, default in new_session(session_id).items():
        s.setdefault(key, default)

    s["session_id"] = session_id
    return s


def log_deal_event(session_id: str, event: str, payload: dict[str, Any]) -> None:
    try:
        with closing(db_connect()) as conn:
            conn.execute(
                "INSERT INTO deal_events(session_id,event,payload,created_at) "
                "VALUES(?,?,?,?)",
                (
                    session_id,
                    event,
                    json.dumps(payload, ensure_ascii=False, default=str),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    except Exception:
        log.exception("Could not log deal event %s", event)


# Initialize the database when the state module is imported.
init_db()

