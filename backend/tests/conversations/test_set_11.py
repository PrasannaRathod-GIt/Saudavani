
import pytest

from tests.helpers import Convo


def make_negotiation(waiting_for):
    return Convo(
        lang="mr-IN",
        commodity_id="wheat",
        commodity="Wheat",
        variety="Lokwan",
        quantity_quintals=5.0,
        district="Nashik",
        market_skipped=True,
        selling_started=True,
        deal_status="NEGOTIATING",
        waiting_for=waiting_for,
        farmer_target_price=None,
        farmer_min_price=None,
        farmer_desired_price=None,
        reported_buyer_quote=None,
        draft_offer=None,
        buyer_offer=None,
        offer_version=0,
        quality={
            "moisture": {"reported_percent": 10.0},
            "cleanliness": {"answer": "clean"},
            "grain_condition": {"answer": "whole"},
        },
    )


def test_set11_buyer_quote_and_farmer_asking_price_are_separate():
    c = make_negotiation("farmer_target")

    # This is what the buyer told the farmer, not the farmer's target.
    c.say("एका buyer ने मला 2800 रुपये प्रति क्विंटल सांगितले.")

    quote = c.state.get("reported_buyer_quote")

    if isinstance(quote, dict):
        quote = quote.get("price_per_quintal")

    assert float(quote or 0) == 2800.0
    assert c.state.get("farmer_desired_price") is None

    # This is the price the farmer wants to ask.
    c.say("मला 3200 रुपये मागायचे आहेत.")

    assert c.state["farmer_desired_price"] == 3200.0
    assert float(
        (c.state.get("reported_buyer_quote") or {}).get(
            "price_per_quintal", 0
        )
    ) == 2800.0


def test_set11_hold_does_not_submit_offer():
    c = make_negotiation("counter_decision")

    # An unverified buyer quote already exists.
    c.state["buyer_offer"] = {
        "price_per_quintal": 2800.0,
        "quantity_quintals": 5.0,
        "source": "farmer_reported_buyer_offer",
        "verified": False,
        "buyer_confirmed": False,
        "active": True,
    }

    c.state["reported_buyer_quote"] = dict(c.state["buyer_offer"])
    c.state["offer_version"] = 1

    c.say("अजून पाठवू नका. मला आधी विचार करायचा आहे.")

    assert c.state["hold"] is True

    # The original reported quote remains unchanged.
    assert c.state["buyer_offer"]["price_per_quintal"] == 2800.0
    assert c.state["buyer_offer"]["source"] == "farmer_reported_buyer_offer"
    assert c.state["offer_version"] == 1


def test_set11_counter_summary_before_submission():
    c = make_negotiation("counter_decision")

    c.state["buyer_offer"] = {
        "price_per_quintal": 2800.0,
        "quantity_quintals": 5.0,
        "source": "farmer_reported_buyer_offer",
        "verified": False,
        "buyer_confirmed": False,
        "active": True,
    }

    c.state["reported_buyer_quote"] = dict(c.state["buyer_offer"])
    c.state["offer_version"] = 1

    # Asking for a summary must only create a draft.
    c.say(
        "आता मला 3100 रुपये प्रति क्विंटलचा counter-offer पाठवायचा आहे. "
        "आधी summary दाखवा."
    )

    draft = c.state.get("draft_offer")

    assert draft is not None
    assert float(draft["price"]) == 3100.0

    # No actual offer submission yet.
    assert c.state["buyer_offer"]["price_per_quintal"] == 2800.0
    assert c.state["offer_version"] == 1
    assert c.state["farmer_confirmed"] is False

    # Explicit farmer confirmation is required to submit.
    c.say(
        "हो, crop, quantity, location आणि 3100 रुपये प्रति क्विंटल "
        "बरोबर आहेत. हा offer पाठवा."
    )

    assert c.state["buyer_offer"]["price_per_quintal"] == 3100.0
    assert c.state["buyer_offer"]["source"] == "farmer_counter_offer"
    assert c.state["offer_version"] == 2
    assert c.state["farmer_confirmed"] is True
    assert c.state.get("draft_offer") is None
