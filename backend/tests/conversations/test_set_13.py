
import pytest
from tests.helpers import Convo


FAQ_QUESTIONS = [
    "Buyer ने offer accept केला तर मला पैसे लगेच मिळतील का",
    "SaudaVani माझे पैसे escrow मध्ये ठेवते का",
    "Buyer ने माल घेतला आणि पैसे दिले नाहीत तर तुम्ही पैसे परत मिळवून द्याल का",
    "Buyer खरा आहे की नाही हे तुम्ही verify करता का",
    "मालाचे वजन कोण confirm करतो",
    "मंडीमध्ये transport, hamali, commission किंवा इतर deductions असतील तर मला net किती मिळेल हे तुम्ही सांगू शकता का?",
    "मला कोणतेही पैसे देण्याआधी कोणती माहिती लेखी घ्यावी",
    "तुम्ही कोणत्या गोष्टी करू शकत नाही ते स्पष्ट सांगा",
]


@pytest.mark.parametrize("question", FAQ_QUESTIONS)

def test_set13_safety_faq_does_not_start_sale(question):
    c = Convo(lang="mr-IN")

    reply = c.say(question)

    # An information-only question must not start a sale.
    assert c.state["selling_started"] is False
    assert c.state["commodity_id"] is None
    assert c.state["variety"] is None
    assert c.state["quantity_quintals"] is None
    assert c.state["district"] is None
    assert c.state["buyer_offer"] is None
    assert c.state["offer_version"] == 0

    # The assistant must answer the question, not force crop intake.
    intake_phrases = [
        "कोणता माल",
        "कोणते पीक",
        "किती क्विंटल",
        "फक्त तुमचे पीक सांगा",
        "कृपया तुम्ही कोणता पिकाचा माल",
    ]

    for phrase in intake_phrases:
        assert phrase not in reply, (
            f"FAQ was redirected to crop intake. "
            f"Question: {question!r}; Reply: {reply!r}"
        )
