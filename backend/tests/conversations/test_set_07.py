
import json
import pytest

import main
from tests.helpers import Convo


@pytest.mark.xfail(
    strict=True,
    reason="Set 7: statewide price lookup must not reuse sale district"
)
def test_set7_maharashtra_average_does_not_leak_sale_district():

    c = Convo(
        lang="mr-IN",
        commodity_id="paddy_rice",
        commodity="Paddy / Rice",
        product_form="Processed rice",
        variety="Basmati",
        quantity_quintals=4.0,
        district="Chhatrapati Sambhajinagar",
        market_skipped=True,
        selling_started=True,
        deal_status="NEGOTIATING",
        waiting_for="farmer_target",
        last_question="farmer_target",
    )

    reply = c.say(
        "महाराष्ट्रामध्ये on average किती किंमत चालू आहे आता?"
    )

    # Maharashtra is a state-level request, not a request for the
    # existing Chhatrapati Sambhajinagar sale district.
    assert "Chhatrapati Sambhajinagar" not in reply

    # The existing sale must remain unchanged.
    assert c.state["commodity_id"] == "paddy_rice"
    assert c.state["district"] == "Chhatrapati Sambhajinagar"
    assert c.state["variety"] == "Basmati"
    assert c.state["quantity_quintals"] == 4.0


@pytest.mark.xfail(
    strict=True,
    reason="Set 7: buyer quality view must not expose raw farmer sentences"
)
def test_set7_buyer_quality_does_not_show_raw_sentences():

    c = Convo(
        lang="mr-IN",
        commodity_id="paddy_rice",
        commodity="Paddy / Rice",
        product_form="Processed rice",
        variety="Basmati",
        quantity_quintals=4.0,
        district="Chhatrapati Sambhajinagar",
        quality={
            "moisture": {
                "answer": "Even quality आहे, सगळे सुक्का आहे."
            },
            "cleanliness": {
                "answer": "नाही, साफ आहे."
            },
            "grain_condition": {
                "answer": "नाही, साबूत आहे."
            },
        },
    )

    # Inspect the same whitelist payload used by the buyer endpoint.
    payload = main.buyer_state(c.state)
    buyer_json = json.dumps(payload, ensure_ascii=False)

    raw_sentences = [
        "Even quality आहे, सगळे सुक्का आहे.",
        "नाही, साफ आहे.",
        "नाही, साबूत आहे.",
    ]

    for sentence in raw_sentences:
        assert sentence not in buyer_json
