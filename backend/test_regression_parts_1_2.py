import copy
import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix="saudavani_test_")
os.environ["SAUDAVANI_DB_PATH"] = os.path.join(_TMP, "test.db")  # temp DB, never the demo DB
os.environ["DEMO_ALLOW_UNAUTHENTICATED_ACTIONS"] = "true"
for _k in ("GNANI_API_KEY", "GROQ_API_KEY", "DATA_GOV_IN_API_KEY"):
    os.environ[_k] = ""  # no network calls

import pytest
from fastapi.testclient import TestClient
import main

PRIVATE_FIELDS = [
    "farmer_min_price", "farmer_target_price", "strong_target_price", "farmer_name",
    "history", "private_note", "negotiation_reasoning",
]
PRIVATE_VALUES = ["9187", "6413", "7777", "secret-note-xyz"]


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:  # one event loop: HTTP + WebSocket share it
        yield c


def ready():
    sid = "t-" + uuid.uuid4().hex[:10]
    s = main.load_session(sid)
    s.update(
        commodity_id="soybean", commodity="Soybean", variety="JS-335", quantity_quintals=10.0,
        district="Pune", market_skipped=True, deal_status="NEGOTIATING", waiting_for=None,
        quality={
            "moisture": {"description": "dry_self_reported"},
            "cleanliness": {"answer": "clean"},
            "seed_condition": {"answer": "uniform"},
        },
    )
    main.save_session(s)
    return sid


def offer(c, sid, price=3000.0, **kw):
    return c.post(f"/api/deals/{sid}/buyer-offer", json={"buyer_id": "B1", "price_per_quintal": price, **kw})


def confirm(c, sid, party, version, accepted=True):
    return c.post(f"/api/deals/{sid}/confirm", json={"party": party, "accepted": accepted, "offer_version": version})


def st(sid):
    return main.peek_session(sid)


# ---- 1/2/3: missing, malformed, past expiry -------------------------------------------------
@pytest.mark.parametrize(
    "bad",
    [None, "not-a-timestamp", (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()],
    ids=["missing", "malformed", "past"],
)
def test_expiry_fails_closed(client, bad):
    sid = ready()
    assert offer(client, sid).status_code == 200
    s = st(sid)
    version = s["offer_version"]
    s["offer_expires_at"] = bad
    main.save_session(s)
    assert confirm(client, sid, "farmer", version).status_code == 409
    s = st(sid)
    assert s["buyer_offer"]["active"] is False and s["buyer_offer"]["status"] == "expired"
    assert s["farmer_confirmed"] is False and s["buyer_confirmed"] is False
    assert s["deal_status"] == "OFFER_EXPIRED" and s["offer_version"] == version + 1
    assert s["deal_status"] != "LOCKED" and not s.get("voucher")
    # no double expiry / no extra version bump
    assert confirm(client, sid, "farmer", version + 1).status_code == 409
    assert st(sid)["offer_version"] == version + 1


# ---- 4/5: consistent lock + buyer view ---------------------------------------------------------
def test_lock_state_consistent_and_buyer_view(client):
    sid = ready()
    assert offer(client, sid).status_code == 200  # buyer submission = buyer confirmation
    response = confirm(client, sid, "farmer", 1)
    assert response.status_code == 200
    s = st(sid)
    assert s["deal_status"] == "LOCKED"
    assert s["buyer_offer"]["active"] is False and s["buyer_offer"]["status"] == "locked"
    assert s["buyer_offer"]["buyer_confirmed"] is True and s["buyer_offer_status"] == "locked"
    assert s["farmer_confirmed"] is True and s["buyer_confirmed"] is True
    assert s["voucher"]["price_per_quintal"] == 3000.0
    buyer = client.get(f"/api/buyer/session/{sid}").json()
    assert buyer["deal_status"] == "LOCKED" and buyer["is_locked"] is True
    assert buyer["active_offer"] is None and buyer["locked_deal"]["gross_amount_inr"] == 30000.0
    assert buyer["ready_for_offer"] is False
    assert buyer["escrow"]["actual_money_transferred_inr"] == 0


# ---- 6: stale version ----------------------------------------------------------------------------
def test_stale_version_409_changes_nothing(client):
    sid = ready()
    assert offer(client, sid).status_code == 200
    s = st(sid)
    s["farmer_confirmed"] = False
    main.save_session(s)
    main._submit_farmer_counter(s, 3500.0)  # version 2
    main.save_session(s)
    before = copy.deepcopy(st(sid))
    assert confirm(client, sid, "buyer", 1).status_code == 409
    after = st(sid)
    for key in ("offer_version", "farmer_confirmed", "buyer_confirmed", "deal_status", "buyer_offer"):
        assert after[key] == before[key]


# ---- 7: new commodity -> separate session -------------------------------------------------------
def test_new_commodity_uses_new_session(client):
    sid = ready()
    assert offer(client, sid).status_code == 200
    before = copy.deepcopy(st(sid))
    before.pop("updated_at", None)
    response = client.post(
        "/api/voice/process",
        data={"session_id": sid, "transcript": "I want to sell wheat", "language": "en-IN"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session_rotated"] is True
    assert body["session_id"] != sid and body["previous_session_id"] == sid
    old = copy.deepcopy(st(sid))
    old.pop("updated_at", None)
    assert old == before  # previous session + pending offer intact
    new = st(body["session_id"])
    assert new["commodity_id"] == "wheat"
    for key in (
        "quantity_quintals", "district", "market", "variety", "buyer_offer", "voucher", "escrow",
        "price_analysis", "farmer_target_price", "farmer_min_price",
    ):
        assert new[key] is None
    assert new["quality"] == {}
    assert new["farmer_confirmed"] is False and new["buyer_confirmed"] is False
    assert new["offer_version"] == 0
    assert new["history"][0]["content"] == "I want to sell wheat"


# ---- 8: no overwrite of active offers --------------------------------------------------------------
def test_duplicate_offer_does_not_overwrite_buyer_offer(client):
    sid = ready()
    assert offer(client, sid, 3000).status_code == 200
    assert offer(client, sid, 3100).status_code == 409
    s = st(sid)
    assert s["buyer_offer"]["price_per_quintal"] == 3000 and s["offer_version"] == 1


def test_duplicate_offer_does_not_overwrite_farmer_counter(client):
    sid = ready()
    assert offer(client, sid, 3000).status_code == 200
    s = st(sid)
    main._submit_farmer_counter(s, 3500.0)
    main.save_session(s)
    assert offer(client, sid, 3100, replaces_offer_version=2).status_code == 409  # even a "versioned" replace
    s = st(sid)
    assert s["buyer_offer"]["source"] == "farmer_counter_offer"
    assert s["buyer_offer"]["price_per_quintal"] == 3500.0
    assert s["offer_version"] == 2 and s["farmer_confirmed"] is True


def test_supported_versioned_replacement(client):
    sid = ready()
    assert offer(client, sid, 3000).status_code == 200
    assert offer(client, sid, 3100, replaces_offer_version=1).status_code == 200
    assert st(sid)["offer_version"] == 2
    assert st(sid)["buyer_offer"]["price_per_quintal"] == 3100


# ---- flows ----------------------------------------------------------------------------------------------
def test_counter_then_buyer_acceptance_locks(client):
    sid = ready()
    assert offer(client, sid).status_code == 200
    s = st(sid)
    main._submit_farmer_counter(s, 3500.0)
    main.save_session(s)
    assert confirm(client, sid, "buyer", 2).status_code == 200
    s = st(sid)
    assert s["deal_status"] == "LOCKED" and s["voucher"]["price_per_quintal"] == 3500.0


def test_rejected_offer_cannot_be_reused(client):
    sid = ready()
    assert offer(client, sid).status_code == 200
    assert confirm(client, sid, "buyer", 1, accepted=False).status_code == 200
    assert st(sid)["deal_status"] == "OFFER_REJECTED"
    assert confirm(client, sid, "farmer", 1).status_code == 409
    assert confirm(client, sid, "farmer", 2).status_code == 409
    assert offer(client, sid, 3200).status_code == 200  # a fresh offer is allowed


# ---- Part 2: privacy ---------------------------------------------------------------------------------------
def test_buyer_privacy_and_404(client):
    sid = ready()
    s = st(sid)
    s.update(
        farmer_min_price=9187.0,
        farmer_target_price=6413.0,
        private_note="secret-note-xyz",
        price_analysis={
            "available": True,
            "modal_reference": 3000,
            "strong_target_price": 7777,
            "fair_price_low": 2800,
            "fair_price_high": 3200,
            "as_of": "2026-11-05",
        },
    )
    main._store_history(s, "user", "my minimum is 9187 secret-note-xyz")
    main.save_session(s)
    payloads = [client.get(f"/api/buyer/session/{sid}").json(), offer(client, sid).json()]
    with client.websocket_connect(f"/ws/buyer/{sid}") as ws:
        payloads.append(ws.receive_json())
    for payload in payloads:
        dumped = json.dumps(payload)
        assert not any(field in dumped for field in PRIVATE_FIELDS), dumped
        assert not any(value in dumped for value in PRIVATE_VALUES), dumped
    assert client.get("/api/buyer/session/does-not-exist").status_code == 404
    with client.websocket_connect("/ws/buyer/does-not-exist") as ws:
        assert ws.receive_json()["type"] == "not_found"


def test_farmer_reported_label(client):
    sid = ready()
    s = st(sid)
    s.update(
        buyer_offer={
            "price_per_quintal": 2800.0,
            "source": "farmer_reported_buyer_offer",
            "active": True,
        },
        offer_version=1,
        offer_expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    )
    main.save_session(s)
    buyer = client.get(f"/api/buyer/session/{sid}").json()
    assert "Farmer-reported, unverified" in buyer["active_offer"]["source_label"]


# ---- WebSockets ---------------------------------------------------------------------------------------------------
def test_ws_both_roles_get_locked_state_and_reconnect_gets_latest(client):
    sid = ready()
    assert offer(client, sid).status_code == 200
    with client.websocket_connect(f"/ws/buyer/{sid}") as buyer_ws, client.websocket_connect(f"/ws/trade/{sid}") as farmer_ws:
        assert buyer_ws.receive_json()["type"] == "snapshot"
        assert farmer_ws.receive_json()["type"] == "snapshot"
        assert confirm(client, sid, "farmer", 1).status_code == 200
        buyer_message = buyer_ws.receive_json()
        farmer_message = farmer_ws.receive_json()
        assert buyer_message["state"]["deal_status"] == "LOCKED"
        assert buyer_message["state"]["active_offer"] is None
        assert farmer_message["state"]["deal_status"] == "LOCKED"
        assert not any(field in json.dumps(buyer_message) for field in PRIVATE_FIELDS)
    with client.websocket_connect(f"/ws/buyer/{sid}") as again:  # reconnect = latest snapshot
        snapshot = again.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["state"]["locked_deal"]["price_per_quintal"] == 3000.0
