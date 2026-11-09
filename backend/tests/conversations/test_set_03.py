
import pytest

from tests.helpers import Convo



def test_set3_no_send_then_price_makes_no_offer():

    c = Convo(
        lang="mr-IN",
        commodity_id="soybean",
        commodity="Soybean",
        variety="JS-335",
        quantity_quintals=10.0,
        district="Latur",
        market_skipped=True,
        deal_status="NEGOTIATING",
        waiting_for="farmer_counter",
        quality={
            "moisture": {
                "description": "dry_self_reported"
            },
            "cleanliness": {
                "answer": "clean"
            },
            "seed_condition": {
                "answer": "uniform"
            },
        },
    )

    c.say("offer पाठवू नका")
    c.say("6700")

    assert c.state["buyer_offer"] is None
    assert c.state["offer_version"] == 0
