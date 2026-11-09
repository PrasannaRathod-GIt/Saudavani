"""Contract tests for SaudaVani buyer privacy, deal versioning, expiry and session rotation.
Run from backend/: python -m pytest -q test_backend_deals.py
Provider keys are blanked and the backend uses a temporary SQLite database.
"""
import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix="saudavani_deals_test_")
os.environ["SAUDAVANI_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["DEMO_ALLOW_UNAUTHENTICATED_ACTIONS"] = "true"
for _key in ("GNANI_API_KEY", "GROQ_API_KEY", "DATA_GOV_IN_API_KEY"):
    os.environ[_key] = ""

import pytest  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app)
PRIVATE_NUMBERS = ("98765", "87654")
PRIVATE_MARKERS = ("SECRET-MARKER-123", "SECRET-SOURCE-456")
PRIVATE_KEYS = ("farmer_target_price", "farmer_min_price", "history", "price_analysis", "farmer_id", "farmer_name")


def make_pending(price=3300.0, qty=5.0):
    """Create a wheat deal with a farmer counter awaiting the buyer's response."""
    sid = f"T-{uuid.uuid4().hex[:10]}"
    s = main.load_session(sid, "Private Farmer Name")
    s.update(
        commodity_id="wheat",
        commodity="Wheat",
        variety="Lokwan",
        quantity_quintals=qty,
        district="Nashik",
        market=None,
        market_skipped=True,
        quality={
            "moisture": {
                "reported_percent": 12.0,
                "description": "measured_or_farmer_reported",
                "answer": "SECRET-MARKER-123",
            },
            "cleanliness": {"answer": "clean", "source": "SECRET-SOURCE-456"},
        },
        farmer_target_price=98765.0,
        farmer_min_price=87654.0,
        history=[{"role": "user", "content": "SECRET-MARKER-123"}],
    )
    main._submit_farmer_counter(s, price)
    main.save_session(s)
    return sid, s


def confirm(sid, party="buyer", version=None, accepted=True):
    current_version = version if version is not None else main.SESSIONS[sid]["offer_version"]
    return client.post(
        f"/api/deals/{sid}/confirm",
        json={"party": party, "accepted": accepted, "offer_version": current_version},
    )


def assert_no_private(payload_text: str):
    for item in PRIVATE_NUMBERS + PRIVATE_MARKERS:
        assert item not in payload_text, f"private value leaked: {item}"


# 1. Buyer-facing endpoint: only the current, whitelisted response contract.
def test_buyer_view_exposes_only_allowed_fields():
    sid, s = make_pending()
    assert "98765" in json.dumps(s)  # control: private data exists in the internal session

    response = client.get(f"/api/buyer/session/{sid}")
    assert response.status_code == 200
    body = response.json()
    assert_no_private(response.text)

    for key in PRIVATE_KEYS:
        assert key not in body

    assert body["crop"] == "Wheat"
    assert body["variety"] == "Lokwan"
    assert body["quantity_quintals"] == 5.0
    assert body["active_offer"]["price_per_quintal"] == 3300.0
    assert body["active_offer"]["gross_value"] == 16500.0
    assert body["offer_version"] == 1
    assert {item["label"]: item["value"] for item in body["quality"]} == {
        "Moisture": "12%",
        "Cleanliness": "clean",
    }
    assert body["buyer_can_accept"] is True
    assert body["buyer_action_blocked_reason"] is None


def test_buyer_unknown_session_404_and_not_created():
    sid = f"NOPE-{uuid.uuid4().hex[:8]}"
    assert client.get(f"/api/buyer/session/{sid}").status_code == 404
    assert sid not in main.SESSIONS
    # Use the DB path captured by main at import time. Other test modules may set the env var later.
    with sqlite3.connect(main.DB_PATH) as connection:
        assert connection.execute(
            "SELECT 1 FROM sessions WHERE session_id=?", (sid,)
        ).fetchone() is None


def test_buyer_websocket_snapshot_has_no_private_data():
    sid, _ = make_pending()
    with client.websocket_connect(f"/ws/buyer/{sid}") as websocket:
        snapshot = websocket.receive_json()
    assert snapshot["type"] == "snapshot"
    assert snapshot["state"]["active_offer"]["price_per_quintal"] == 3300.0
    assert_no_private(json.dumps(snapshot))


# 2. Version mismatch must not mutate the deal.
def test_version_mismatch_returns_409_and_changes_nothing():
    sid, s = make_pending()
    response = confirm(sid, "buyer", version=99)
    assert response.status_code == 409
    assert "mismatch" in response.json()["detail"].lower()
    assert s["buyer_confirmed"] is False
    assert s["deal_status"] == "PENDING_BUYER_RESPONSE"


def test_confirm_unknown_session_is_404():
    response = client.post(
        f"/api/deals/NOPE-{uuid.uuid4().hex[:6]}/confirm",
        json={"party": "buyer", "accepted": True, "offer_version": 1},
    )
    assert response.status_code == 404


def test_unauthenticated_actions_stay_off_when_flag_disabled(monkeypatch):
    sid, s = make_pending()
    monkeypatch.setattr(main, "DEMO_ALLOW_UNAUTHENTICATED_ACTIONS", False)
    assert confirm(sid).status_code == 403
    assert s["buyer_confirmed"] is False
    assert s["deal_status"] == "PENDING_BUYER_RESPONSE"
    view = client.get(f"/api/buyer/session/{sid}").json()
    assert view["buyer_can_accept"] is False
    assert view["buyer_action_blocked_reason"] == "actions_disabled_on_server"


# 3. Expiry: missing, malformed, non-string and past values must fail closed.
BAD_EXPIRY = [None, "", "   ", "not-a-date", 12345, "2026-13-45T99:99:99"]


@pytest.mark.parametrize("bad", BAD_EXPIRY)
def test_missing_or_malformed_expiry_never_confirms_or_locks(bad):
    sid, s = make_pending()
    s["offer_expires_at"] = bad

    view = client.get(f"/api/buyer/session/{sid}").json()
    assert view["buyer_can_accept"] is False
    assert view["buyer_action_blocked_reason"] == "offer_expired"

    response = confirm(sid)
    assert response.status_code == 409
    assert s["deal_status"] == "OFFER_EXPIRED"
    assert s["buyer_confirmed"] is False
    assert s.get("voucher") is None


def test_lock_deal_refuses_bad_expiry_directly():
    sid, s = make_pending()
    s["buyer_confirmed"] = True
    s["offer_expires_at"] = "garbage"
    with pytest.raises(ValueError):
        main._lock_deal(s, mode="two_party")
    assert s["deal_status"] != "LOCKED"


def test_past_expiry_is_rejected():
    sid, s = make_pending()
    s["offer_expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert confirm(sid).status_code == 409
    assert s["deal_status"] == "OFFER_EXPIRED"


# 4. Both parties confirm: one consistent locked state.
def assert_locked_consistently(sid, s):
    assert s["deal_status"] == "LOCKED"
    assert s["farmer_confirmed"] is True
    assert s["buyer_confirmed"] is True
    offer = s["buyer_offer"]
    assert offer["status"] == "locked"
    assert offer["active"] is False  # locked offers are no longer actionable
    assert offer["buyer_confirmed"] is True
    assert s["voucher"]["status"] == "LOCKED"
    assert s["escrow"]["actual_money_transferred_inr"] == 0
    assert s["escrow"]["is_simulation"] is True


def test_buyer_accepts_farmer_counter_locks_consistently():
    sid, s = make_pending()
    response = confirm(sid, "buyer")
    assert response.status_code == 200
    assert response.json()["state"]["deal_status"] == "LOCKED"
    assert response.json()["state"]["is_locked"] is True
    assert_locked_consistently(sid, s)

    view = client.get(f"/api/buyer/session/{sid}").json()
    assert view["buyer_can_accept"] is False
    assert view["buyer_action_blocked_reason"] == "deal_already_locked"
    assert view["locked_deal"]["voucher_id"]
    assert_no_private(json.dumps(response.json()) + json.dumps(view))
    assert confirm(sid, "buyer").json()["message"] == "Deal already locked."


def test_farmer_then_buyer_order_also_locks():
    sid, s = make_pending()
    s["farmer_confirmed"], s["buyer_confirmed"], s["deal_status"] = False, False, "NEGOTIATING"
    farmer_response = confirm(sid, "farmer")
    assert farmer_response.json()["state"]["deal_status"] == "PENDING_BUYER_CONFIRMATION"
    assert confirm(sid, "buyer").status_code == 200
    assert_locked_consistently(sid, s)


def test_refused_lock_does_not_leave_half_confirmed_state():
    sid, s = make_pending()
    s["variety"] = None  # incomplete terms make _lock_deal refuse
    response = confirm(sid, "buyer")
    assert response.status_code == 409
    assert s["buyer_confirmed"] is False
    assert s["farmer_confirmed"] is True
    assert s["deal_status"] == "PENDING_BUYER_RESPONSE"


# 5. Buyer WebSocket room receives the buyer-safe update after confirmation.
class FakeSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, payload):
        self.messages.append(payload)


def test_websocket_receives_locked_state_without_private_data():
    sid, _ = make_pending()
    fake_socket = FakeSocket()
    buyer_room = ("buyer", sid)
    main.manager.rooms.setdefault(buyer_room, set()).add(fake_socket)
    try:
        assert confirm(sid, "buyer").status_code == 200
    finally:
        main.manager.rooms.get(buyer_room, set()).discard(fake_socket)

    assert fake_socket.messages, "no buyer WebSocket update was broadcast"
    message = fake_socket.messages[-1]
    assert message["type"] == "state_update"
    assert message["state"]["deal_status"] == "LOCKED"
    assert message["state"]["buyer_confirmed"] is True
    assert message["state"]["farmer_confirmed"] is True
    assert_no_private(json.dumps(message))


# 6. Separate sessions: a new crop must not overwrite an existing transaction.
def speak(sid, transcript):
    return client.post(
        "/api/voice/process",
        data={"session_id": sid, "transcript": transcript, "language": "mr-IN"},
    )


def test_new_commodity_starts_separate_session_and_keeps_pending_deal():
    sid, _ = make_pending()
    response = speak(sid, "mala soybean vikaycha aahe")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_rotated"] is True
    assert body["session_id"] != sid
    assert body["previous_session_id"] == sid

    old = main.SESSIONS[sid]
    assert old["commodity_id"] == "wheat"
    assert old["deal_status"] == "PENDING_BUYER_RESPONSE"
    assert old["buyer_offer"]["price_per_quintal"] == 3300.0
    assert old["offer_version"] == 1
    assert main.SESSIONS[body["session_id"]]["commodity_id"] == "soybean"


def test_price_question_about_other_crop_does_not_split_or_overwrite():
    sid, s = make_pending()
    response = speak(sid, "soybean cha bhav kay aahe?")
    assert response.status_code == 200
    body = response.json()
    assert body["session_rotated"] is False
    assert body["session_id"] == sid
    assert main.SESSIONS[sid]["commodity_id"] == "wheat"
    assert s["buyer_offer"]["price_per_quintal"] == 3300.0


def test_locked_deal_is_never_reused_for_a_new_crop():
    sid, s = make_pending()
    assert confirm(sid).status_code == 200
    response = speak(sid, "mala soybean vikaycha aahe")
    assert response.status_code == 200
    body = response.json()
    assert body["session_rotated"] is True
    assert main.SESSIONS[sid]["deal_status"] == "LOCKED"
    assert main.SESSIONS[sid]["commodity_id"] == "wheat"
    same = speak(sid, "mala wheat vikaycha aahe")
    assert same.status_code == 200
    assert same.json()["session_rotated"] is False
    assert same.json()["session_id"] == sid
