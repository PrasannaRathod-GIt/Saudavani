
import pytest

from tests.helpers import Convo


@pytest.mark.xfail(
    strict=True,
    reason="Set 8: corrections must replace previous sale details"
)
def test_set8_sale_detail_corrections():

    c = Convo(lang="mr-IN")

    # Original sale details.
    c.say("I want to sell 5 quintals of wheat in Akola.")

    assert c.state["commodity_id"] == "wheat"
    assert c.state["quantity_quintals"] == 5.0
    assert c.state["district"] == "Akola"

    # Correction 1: quantity must replace 5 with 7.
    c.say("Actually, the quantity is 7 quintals, not 5")

    assert c.state["quantity_quintals"] == 7.0

    # Correction 2: district must replace Akola with Nashik.
    c.say(
        "Sorry, I said Akola by mistake. The sale district is Nashik."
    )

    assert c.state["district"] == "Nashik"

    # Provide the variety.
    c.say("The variety is Lokwan")

    assert c.state["variety"] == "Lokwan"

    # Any mandi in Nashik; do not change the sale district.
    c.say("Any mandi in Nashik is fine")

    assert c.state["district"] == "Nashik"
    assert c.state["market_skipped"] is True

    # Correction 3: remove the previously supplied variety.
    c.say("No, I am not sure about the variety. Remove that assumption.")

    assert c.state["variety"] is None

    # Correction 4: explicitly retain wheat, not rice.
    c.say(
        "I said wheat, not rice. Please repeat the corrected trade details."
    )

    assert c.state["commodity_id"] == "wheat"

    # Final corrected sale details.
    assert c.state["quantity_quintals"] == 7.0
    assert c.state["district"] == "Nashik"
    assert c.state["variety"] is None

    # No offer should have been created during these corrections.
    assert c.state["buyer_offer"] is None
    assert c.state["offer_version"] == 0
