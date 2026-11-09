import json, re, main

PRIVATE_KEYS = ("farmer_target_price", "farmer_min_price", "farmer_desired_price", "draft_offer", "history", "farmer_id")

def check_all(sid, text, reply, before):
    s = main.SESSIONS[sid]
    for payload in (main.public_state(s), main.buyer_state(s)):      # key names, not values: values can legitimately coincide
        dumped = json.dumps(payload)
        for k in PRIVATE_KEYS: assert f'"{k}"' not in dumped, k
    assert len(re.findall(r"[?？]", reply)) <= 1, reply
    o = s.get("buyer_offer") or {}
    if o.get("source") == "farmer_counter_offer" and o.get("active"):
        assert s["farmer_confirmed"] and s.get("draft_offer") is None
    touched = main.match_commodity(text)[0] or main.find_district(text) or main.parse_quantity(text) is not None
    if not touched and s["session_id"] == before["session_id"]:
        assert s["commodity_id"] == before["commodity_id"] and s["district"] == before["district"]