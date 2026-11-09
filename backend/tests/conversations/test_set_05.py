
import pytest

from tests.helpers import Convo


@pytest.mark.xfail(
    strict=True,
    reason="Set 5: information-only questions must not start sale intake"
)
def test_set5_info_only_does_not_start_selling():

    c = Convo(lang="mr-IN")

    # Farmer asks for rice prices for information.
    c.say("आज नाशिकमध्ये तांदळाचा भाव किती आहे?")

    # Farmer explicitly says they are not selling.
    c.say("मला फक्त एक अंदाज समजून घ्यायचा आहे. मी आत्ता माल विकत नाही")

    # Further information questions must remain read-only.
    c.say("शेवटचा उपलब्ध record किती जुना आहे?")
    c.say("मोडल भाव आणि जास्तीत जास्त नोंदलेला भाव यात काय फरक आहे?")

    # No sale intake should have started.
    assert c.state["selling_started"] is False
    assert c.state["waiting_for"] is None

    # No sale details should have been collected.
    assert c.state["commodity_id"] is None
    assert c.state["variety"] is None
    assert c.state["quantity_quintals"] is None
    assert c.state["district"] is None

    # No offer should exist.
    assert c.state["buyer_offer"] is None
    assert c.state["offer_version"] == 0
