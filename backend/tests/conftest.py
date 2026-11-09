import os, tempfile
_TMP = tempfile.mkdtemp(prefix="sv_")
os.environ["SAUDAVANI_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["DEMO_ALLOW_UNAUTHENTICATED_ACTIONS"] = "true"
for k in ("GNANI_API_KEY", "GROQ_API_KEY", "DATA_GOV_IN_API_KEY"):
    os.environ[k] = ""

import pytest, main
from datetime import date, timedelta

FAKE = {  # (commodity_id, district) -> (modal, min, max, age_days)
    ("soybean", "Latur"): (4200, 3900, 4600, 1),
    ("wheat", "Nashik"): (2800, 2600, 3000, 1),
    ("tur", "Latur"): (7000, 6600, 7400, 45),   # stale-case
}

@pytest.fixture
def fake_prices(monkeypatch):
    async def fake(commodity_id, market=None, variety=None, product_form=None, district=None):
        dist = main.canonical_district(district)
        row = FAKE.get((commodity_id, dist))
        if not row:  # same behaviour as today's offline run
            return main._price_unavailable("no_records", "no data", commodity_id, dist, market)
        modal, lo, hi, age = row
        d = date.today() - timedelta(days=age)
        return {"available": True, "status": "ok" if age <= 3 else "stale", "stale": age > 3,
                "source": "fake", "commodity": main.COMMODITIES[commodity_id]["name"], "district": dist,
                "market_scope": f"{dist} district", "matched_markets": [], "as_of": d.isoformat(),
                "as_of_display": d.strftime("%d/%m/%Y"), "age_days": age, "reference_type": "market_actual",
                "official_market_modal": modal, "calculated_median_modal": None, "modal_reference": modal,
                "fair_price_low": lo, "fair_price_high": hi, "strong_target_price": hi,
                "lowest_market_min": lo, "highest_market_max": hi, "market_count": 1, "varieties_combined": 1,
                "variety_match": None, "market_matched": None, "market_fallback": False, "variety_fallback": False}
    monkeypatch.setattr(main, "fetch_mandi_benchmark", fake)   # after Step 1, also patch `prices`