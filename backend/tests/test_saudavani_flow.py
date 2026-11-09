"""Regression tests: quantity parsing, selling-intent detection and information questions during the selling flow.

Run from the backend folder:   python -m unittest tests.test_saudavani_flow -v      (or: pytest tests/test_saudavani_flow.py)
No network and no API credits: the data.gov.in lookup and Groq are mocked.
"""
import asyncio
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import _stubs  # noqa: E402

_stubs.install_stubs_if_needed()
import main  # noqa: E402
import prices  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def fake_pa(commodity="Wheat", district="Pune", modal=2400.0, **kw):
    pa = {
        "available": True, "status": "ok", "commodity": commodity, "district": district, "market_scope": f"{district} district",
        "as_of": "2026-11-06", "as_of_display": "06/11/2026", "stale": False, "reference_type": "market_actual",
        "official_market_modal": modal, "modal_reference": modal, "lowest_market_min": modal - 100, "highest_market_max": modal + 100,
        "market_count": 1, "varieties_combined": 1, "variety_match": None, "market_matched": None, "market_requested": None,
        "fair_price_low": modal - 100, "fair_price_high": modal + 100, "from_cache": False,
    }
    pa.update(kw)
    return pa


class Base(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.pa_factory = lambda cid, market, variety, form, district: fake_pa(main.COMMODITIES[cid]["name"], district)

        async def fake_fetch(cid, market=None, variety=None, product_form=None, district=None):
            self.calls.append({"cid": cid, "market": market, "variety": variety, "district": district})
            return self.pa_factory(cid, market, variety, product_form, district)

        self._orig_fetch, self._orig_groq = main.fetch_mandi_benchmark, main._groq_client
        main.fetch_mandi_benchmark = fake_fetch
        main._groq_client = None
        self.s = main.new_session("t-" + self.id().split(".")[-1])

    def tearDown(self):
        main.fetch_mandi_benchmark, main._groq_client = self._orig_fetch, self._orig_groq

    def say(self, text, hint="en-IN"):
        reply, plan = run(main.process_conversation_turn(self.s, text, hint))
        self.plan = plan
        return reply

    def selling_snapshot(self):
        keys = ("commodity_id", "variety", "quantity_quintals", "district", "market", "market_skipped", "product_form",
                "waiting_for", "last_question", "deal_status", "price_analysis", "price_status", "buyer_offer",
                "farmer_target_price", "farmer_min_price", "quality")
        return {k: self.s.get(k) for k in keys}


class QuantityTests(unittest.TestCase):
    def test_spec_examples(self):
        cases = {
            "माझ्याकडे 4 किलो मका आहे": 0.04, "माझ्याकडे 4 किलो मका आहे.": 0.04, "दोन quintal माल आहे": 2.0, "दो क्विंटल": 2.0,
            "two quintals": 2.0, "4 kg maize": 0.04, "4 kilo makka": 0.04, "2 qtl": 2.0, "2 quintals": 2.0, "1 tonne": 10.0,
            "एक टन": 10.0, "१० क्विंटल": 10.0, "२ किलो": 0.02, "2.5 quintal": 2.5,
        }
        for text, expected in cases.items():
            self.assertEqual(main.parse_quantity(text), expected, text)

    def test_number_words_all_languages(self):
        words = {
            "एक": 1, "दोन": 2, "तीन": 3, "चार": 4, "पाच": 5, "सहा": 6, "सात": 7, "आठ": 8, "नऊ": 9, "दहा": 10, "अकरा": 11, "बारा": 12,
            "पंधरा": 15, "वीस": 20, "दो": 2, "पांच": 5, "छह": 6, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "पंद्रह": 15, "बीस": 20,
            "ek": 1, "don": 2, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "saat": 7, "aath": 8,
            "nau": 9, "das": 10, "bara": 12, "bees": 20, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20,
        }
        for word, value in words.items():
            self.assertEqual(main.parse_quantity(f"{word} quintal"), float(value), word)
            self.assertEqual(main.parse_bare_quantity(word), float(value), word)

    def test_kilo_and_compound_numbers(self):
        self.assertEqual(main.parse_quantity("पाँच सौ किलो"), 5.0)
        self.assertEqual(main.parse_quantity("do hazaar kilo"), 20.0)
        self.assertEqual(main.parse_quantity("twenty five quintal"), 25.0)
        self.assertEqual(main.parse_quantity("1,200 kg"), 12.0)

    def test_standalone_number_only_when_asked(self):
        self.assertIsNone(main.parse_quantity("दोन"))  # no unit: never a quantity by itself
        self.assertEqual(main.parse_bare_quantity("दोन"), 2.0)
        s = main.new_session("q1")
        s.update(commodity_id="maize", commodity="Maize", variety="Hybrid", waiting_for="quantity")
        main._update_entities(s, "दोन", "mr")
        self.assertEqual(s["quantity_quintals"], 2.0)

    def test_corrected_quantity_replaces(self):
        s = main.new_session("q2")
        s.update(commodity_id="wheat", commodity="Wheat", variety="Lokwan", quantity_quintals=2.0, waiting_for="district")
        main._update_entities(s, "नाही, 3 क्विंटल आहे", "mr")
        self.assertEqual(s["quantity_quintals"], 3.0)
        self.assertEqual(main.parse_quantity("2 quintal nahi 3 quintal"), 3.0)
        self.assertEqual(main.parse_quantity("not 2 quintals, 3 quintals"), 3.0)

    def test_unrelated_numbers_are_not_quantities(self):
        for text in ["my number is 9876543210", "12 percent moisture", "3000 rupees per quintal", "price 2800", "per 100 kg 2500",
                     "5 acres", "दर 3000 रुपये प्रति क्विंटल", "do you buy wheat"]:
            self.assertIsNone(main.parse_quantity(text), text)
        self.assertIsNone(main.parse_bare_quantity("5 acres"))
        self.assertIsNone(main.parse_bare_quantity("3000 rupees"))

    def test_unrecognised_number_word_is_not_guessed(self):
        self.assertIsNone(main.parse_quantity("kuch quintal maal hai"))
        self.assertIsNone(main.parse_quantity("एकवीस क्विंटल"))

    def test_range_validation_and_decimals(self):
        self.assertIsNone(main.parse_quantity("0 quintal"))
        self.assertIsNone(main.parse_quantity("200000 quintal"))
        self.assertEqual(main.parse_quantity("0.5 quintal"), 0.5)

    def test_quantity_not_mistaken_for_price(self):
        self.assertIsNone(main.parse_price("500 kg maize"))
        self.assertIsNone(main.parse_price("400 kilo"))
        self.assertIsNone(main.parse_price("200 क्विंटल"))
        self.assertEqual(main.parse_price("500 kg at 2800"), 2800.0)


class SellingIntentTests(Base):
    def test_marathi_first_sentence(self):
        reply = self.say("माझ्याकडे 4 किलो मका आहे", "mr-IN")
        self.assertEqual(self.s["commodity_id"], "maize")
        self.assertEqual(self.s["quantity_quintals"], 0.04)
        self.assertEqual(self.s["waiting_for"], "variety")
        self.assertTrue(self.s["selling_started"])

    def test_quantity_is_never_asked_again(self):
        self.say("माझ्याकडे 4 किलो मका आहे", "mr-IN")
        self.say("Hybrid", "mr-IN")
        self.say("Pune", "mr-IN")
        self.assertNotEqual(self.s["waiting_for"], "quantity")
        self.assertEqual(self.s["quantity_quintals"], 0.04)

    def test_sell_intent_phrases(self):
        yes = ["मला माल विकायचा आहे.", "मला गहू विकायचा आहे.", "माझ्याकडे दोन क्विंटल माल आहे.", "माझ्याकडे मका विकण्यासाठी आहे.",
               "मी माल विकणार आहे.", "मुझे माल बेचना है।", "मुझे गेहूं बेचना है।", "मेरे पास दो क्विंटल माल है।", "मेरे पास मक्का बेचने के लिए है।",
               "Mujhe maal bechna hai.", "Mere paas do quintal maal hai.", "Mere paas 2 quintal gehun hai.", "Makka sell karna hai.",
               "I want to sell wheat.", "I have two quintals of maize.", "I have produce to sell.", "I want to sell my crop."]
        for t in yes:
            self.assertTrue(main._has_sell_intent(t), t)
        for t in ["What is today's wheat mandi price?", "आज गव्हाचा मंडीभाव किती आहे?", "Lokwan", "Pune"]:
            self.assertFalse(main._has_sell_intent(t), t)

    def test_marathi_sell_wheat(self):
        self.say("मला गहू विकायचा आहे.", "mr-IN")
        self.assertEqual((self.s["commodity_id"], self.s["waiting_for"]), ("wheat", "variety"))

    def test_hindi_quantity_without_crop_asks_crop(self):
        reply = self.say("मेरे पास दो क्विंटल माल है।", "hi-IN")
        self.assertEqual(self.s["quantity_quintals"], 2.0)
        self.assertIsNone(self.s["commodity_id"])
        self.assertEqual(self.s["waiting_for"], "commodity")
        self.assertTrue(self.s["selling_started"])

    def test_hinglish_quantity_without_crop(self):
        self.say("Mere paas do quintal maal hai.", "hi-IN")
        self.assertEqual((self.s["quantity_quintals"], self.s["commodity_id"]), (2.0, None))
        self.say("gehun", "hi-IN")
        self.assertEqual((self.s["commodity_id"], self.s["waiting_for"], self.s["quantity_quintals"]), ("wheat", "variety", 2.0))

    def test_hinglish_with_crop(self):
        self.say("Mere paas 2 quintal gehun hai.", "hi-IN")
        self.assertEqual((self.s["commodity_id"], self.s["quantity_quintals"]), ("wheat", 2.0))

    def test_commodity_quantity_district_together(self):
        reply = self.say("I want to sell wheat, two quintals, in Pune.")
        self.assertEqual((self.s["commodity_id"], self.s["quantity_quintals"], self.s["district"]), ("wheat", 2.0, "Pune"))
        self.assertEqual(self.s["waiting_for"], "variety")
        self.assertNotIn("quintal", reply.lower().replace("which variety", ""))  # no quantity / district question

    def test_i_want_to_sell_wheat(self):
        self.say("I want to sell wheat.")
        self.assertEqual((self.s["commodity_id"], self.s["waiting_for"]), ("wheat", "variety"))

    def test_general_price_question_does_not_start_selling(self):
        reply = self.say("What is today's wheat mandi price?")
        self.assertIsNone(self.s["commodity_id"])
        self.assertFalse(self.s["selling_started"])
        self.assertEqual(self.s["waiting_for"], "commodity")
        self.assertEqual(self.calls, [])  # needs a district first
        self.assertIn("district", reply.lower())

    def test_price_question_with_district_answers_without_selling(self):
        reply = self.say("What is the mandi rate of maize in Pune?")
        self.assertEqual(self.calls[0]["cid"], "maize")
        self.assertIsNone(self.s["commodity_id"])
        self.assertIsNone(self.s["district"])
        self.assertIn("06/11/2026", reply)
        self.assertIn("sell", reply.lower())  # gentle invitation, not a form question

    def test_how_do_i_sell(self):
        reply = self.say("How do I sell my produce?")
        self.assertIn("quantity", reply.lower())
        self.assertIsNone(self.s["commodity_id"])
        self.assertEqual(self.calls, [])
        self.assertIn(main.ask_text("en", "commodity"), reply)  # offers to start: asks for the crop

    def test_session_not_rotated_for_howto(self):
        self.s.update(commodity_id="wheat", commodity="Wheat", variety="Lokwan", waiting_for="quantity")
        self.assertIsNone(main._new_commodity_request(self.s, "How do I sell maize?"))
        self.assertEqual(main._new_commodity_request(self.s, "मला मका विकायचा आहे"), "maize")


class InterruptionTests(Base):
    def start_wheat(self, waiting="variety"):
        self.say("I want to sell wheat.")
        self.assertEqual(self.s["waiting_for"], "variety")

    def test_variety_then_price_question_resumes_variety(self):
        self.start_wheat()
        before = self.selling_snapshot()
        reply = self.say("Before that, what is today's wheat price in Pune?")
        self.assertEqual(self.calls[-1]["district"], "Pune")
        self.assertIn("06/11/2026", reply)
        self.assertIn("not a live auction", reply)
        self.assertIn(main.make_question(self.s, "variety", "en"), reply)  # the exact pending question is asked again
        self.assertEqual(self.selling_snapshot(), before)  # informational query changes nothing

    def test_maize_price_during_maize_variety_question(self):
        self.say("I want to sell maize.")
        reply = self.say("What is the maize price in Pune?")
        self.assertEqual(self.s["waiting_for"], "variety")
        self.assertIsNone(self.s["district"])
        self.assertIn(main.make_question(self.s, "variety", "en"), reply)

    def test_quantity_question_then_price_question(self):
        self.say("I want to sell wheat.")
        self.say("Lokwan")
        self.assertEqual(self.s["waiting_for"], "quantity")
        reply = self.say("Aaj Pune mandi mein gehun kitne ka chal raha hai?", "hi-IN")
        self.assertEqual(self.s["waiting_for"], "quantity")
        self.assertIsNone(self.s["quantity_quintals"])
        self.assertIn(main.make_question(self.s, "quantity", "hinglish"), reply)

    def test_district_question_then_general_question_without_groq(self):
        self.say("I want to sell wheat.")
        self.say("Lokwan")
        self.say("2 quintal")
        self.assertEqual(self.s["waiting_for"], "district")
        reply = self.say("What is the best time to store wheat?")
        self.assertEqual(self.s["waiting_for"], "district")
        self.assertIsNone(self.s["district"])
        self.assertIn(main.ask_text("en", "offline_answer"), reply)  # honest fallback, nothing invented
        self.assertIn(main.make_question(self.s, "district", "en"), reply)

    def test_other_commodity_price_does_not_change_session(self):
        self.say("I want to sell wheat.")
        self.say("Lokwan")
        before = self.selling_snapshot()
        reply = self.say("What is the maize price in Nashik?")
        self.assertEqual(self.calls[-1]["cid"], "maize")
        self.assertIsNone(self.calls[-1]["variety"])  # wheat variety is not applied to maize
        self.assertEqual(self.selling_snapshot(), before)
        self.assertIn(main.make_question(self.s, "quantity", "en"), reply)

    def test_price_without_district_then_district_then_resume(self):
        self.say("I want to sell wheat.")
        before = self.selling_snapshot()
        r1 = self.say("What is the wheat price today?")
        self.assertEqual(self.calls, [])
        self.assertEqual(r1.count("?"), 1)  # one short question only
        self.assertEqual(self.s["info_query"]["awaiting"], "district")
        self.assertEqual(self.selling_snapshot(), before)  # pending selling question preserved
        r2 = self.say("Nashik")
        self.assertEqual(self.calls[-1]["district"], "Nashik")
        self.assertIsNone(self.s["info_query"])
        self.assertIsNone(self.s["district"])  # the info district is NOT the selling district
        self.assertIn("06/11/2026", r2)
        self.assertIn(main.make_question(self.s, "variety", "en"), r2)
        self.assertEqual(self.selling_snapshot(), before)

    def test_price_without_crop_asks_crop(self):
        r1 = self.say("What is the mandi price?")
        self.assertEqual(self.s["info_query"]["awaiting"], "commodity")
        r2 = self.say("onion")
        self.assertEqual(self.s["info_query"]["awaiting"], "district")
        r3 = self.say("Nashik")
        self.assertEqual(self.calls[-1]["cid"], "onion")
        self.assertIsNone(self.s["commodity_id"])

    def test_saved_district_used_when_not_contradicted(self):
        self.say("I want to sell wheat in Pune.")
        self.say("What is the maize price today?")
        self.assertEqual(self.calls[-1]["district"], "Pune")
        self.say("What is the wheat price in Nashik?")
        self.assertEqual(self.calls[-1]["district"], "Nashik")
        self.assertEqual(self.s["district"], "Pune")

    def test_selling_answer_while_info_query_waits_drops_query(self):
        self.say("I want to sell wheat.")
        self.say("What is the wheat price today?")
        reply = self.say("Lokwan")
        self.assertIsNone(self.s["info_query"])
        self.assertEqual(self.s["variety"], "Lokwan")
        self.assertEqual(self.s["waiting_for"], "quantity")

    def test_question_and_selling_detail_in_one_utterance(self):
        self.say("I want to sell wheat.")
        reply = self.say("Lokwan, what is the wheat price in Pune?")
        self.assertEqual(self.s["variety"], "Lokwan")
        self.assertEqual(self.calls[-1]["district"], "Pune")
        self.assertIsNone(self.s["district"])
        self.assertIn("06/11/2026", reply)
        self.assertIn(main.make_question(self.s, "quantity", "en"), reply)

    def test_sell_and_question_without_comma(self):
        reply = self.say("I have 2 quintal wheat and what is the price in Pune")
        self.assertEqual((self.s["commodity_id"], self.s["quantity_quintals"]), ("wheat", 2.0))
        self.assertIn("06/11/2026", reply)

    def test_short_answer_with_question_word_is_still_an_answer(self):
        self.say("I want to sell wheat.")
        self.say("Lokwan kya?", "hi-IN")
        self.assertEqual(self.s["variety"], "Lokwan")

    def test_marathi_and_hindi_price_questions(self):
        for text, hint, cid in [("आज गव्हाचा मंडीभाव किती आहे? पुण्यात", "mr-IN", "wheat"), ("पुण्यात मक्याचा भाव किती आहे?", "mr-IN", "maize"),
                                ("आज सोयाबीनला काय दर आहे? पुणे", "mr-IN", "soybean"),
                                ("Mere district mein gehun ka bhav kya hai? Pune", "hi-IN", "wheat")]:
            self.tearDown()
            self.setUp()
            self.say(text, hint)
            self.assertTrue(self.calls and self.calls[-1]["cid"] == cid, text)

    def test_informational_question_never_triggers_deal_actions(self):
        self.s.update(commodity_id="wheat", commodity="Wheat", variety="Lokwan", quantity_quintals=2.0, district="Pune",
                      market_skipped=True, waiting_for="farmer_decision", deal_status="NEGOTIATING")
        self.s["buyer_offer"] = {"price_per_quintal": 2300.0, "source": "farmer_reported_buyer_offer", "active": True}
        offer_before = dict(self.s["buyer_offer"])
        reply = self.say("What does modal price mean?")
        self.assertEqual(self.s["waiting_for"], "farmer_decision")
        self.assertEqual(self.s["buyer_offer"], offer_before)
        self.assertFalse(self.s["farmer_confirmed"])
        self.assertEqual(self.s["deal_status"], "NEGOTIATING")
        self.assertIn("modal", reply.lower())
        self.assertIn(main.ask_text("en", "pending_decision"), reply)
        self.say("Is this the live auction price?")
        self.assertEqual(self.s["waiting_for"], "farmer_decision")
        self.say("How is modal price calculated?")
        self.assertEqual(self.s["buyer_offer"], offer_before)

    def test_price_answers_do_not_break_price_entry(self):
        self.s.update(commodity_id="wheat", commodity="Wheat", variety="Lokwan", quantity_quintals=2.0, district="Pune",
                      market_skipped=True, waiting_for="farmer_target", deal_status="NEGOTIATING")
        self.say("mandi price jitna")  # existing behaviour: not a question
        self.assertEqual(self.s["waiting_for"], "farmer_minimum")

    def test_private_prices_not_sent_to_groq(self):
        captured = {}

        class Msg:
            content = "ok"

        class Resp:
            choices = [type("C", (), {"message": Msg()})()]

        class Comp:
            async def create(self, **kw):
                captured.update(kw)
                return Resp()

        main._groq_client = type("G", (), {"chat": type("Ch", (), {"completions": Comp()})()})()
        self.s.update(commodity_id="wheat", commodity="Wheat", variety="Lokwan", quantity_quintals=2.0, district="Pune",
                      market_skipped=True, waiting_for="farmer_target", deal_status="NEGOTIATING")
        self.say("I want 3100")
        self.say("my minimum is 2900")
        self.s["waiting_for"] = "buyer_offer"
        self.say("What is a good crop rotation after wheat?")
        blob = str(captured.get("messages"))
        self.assertNotIn("3100", blob)
        self.assertNotIn("2900", blob)
        self.assertIn("private", blob.lower())  # system prompt forbids revealing private prices


class PriceHonestyTests(Base):
    def test_no_groq_price_still_uses_data_gov(self):
        self.assertIsNone(main._groq_client)
        reply = self.say("wheat price in Pune today?")
        self.assertEqual(len(self.calls), 1)
        self.assertIn("2,400", reply)

    def test_groq_never_invents_prices(self):
        class Boom:
            def __getattr__(self, name):
                raise AssertionError("Groq must not be used for a price question")

        main._groq_client = Boom()
        self.say("wheat price in Pune today?")
        self.assertEqual(len(self.calls), 1)

    def test_api_unavailable_is_honest(self):
        self.pa_factory = lambda *a: {"available": False, "status": "timeout", "error": "timeout"}
        reply = self.say("wheat price in Pune today?")
        self.assertNotIn("₹", reply)
        self.assertIn("not guess", reply)

    def test_stale_data_disclosed(self):
        self.pa_factory = lambda cid, m, v, f, d: fake_pa("Wheat", d, stale=True, as_of="2026-10-20", as_of_display="20/10/2026")
        reply = self.say("wheat price in Pune today?")
        self.assertIn("20/10/2026", reply)
        self.assertIn("old", reply)

    def test_fallbacks_and_calculated_median_disclosed(self):
        self.pa_factory = lambda cid, m, v, f, d: fake_pa("Wheat", d, reference_type="calculated_median", variety_match=False,
                                                          market_matched=False, market_requested="Baramati", market_count=3,
                                                          calculated_median_modal=2400.0, modal_spread_low=2300.0, modal_spread_high=2500.0)
        reply = self.say("Baramati mandi Lokwan wheat price today?")
        self.assertIn("calculated", reply)
        self.assertIn("not an official mandi modal", reply)
        self.assertIn("exact variety was not found", reply)
        self.assertIn("no record was found for", reply)

    def test_msp_not_answered_with_modal(self):
        reply = self.say("What is the MSP of wheat?")
        self.assertEqual(self.calls, [])
        self.assertIn("not MSP", reply)
        self.assertNotIn("₹", reply)
        reply = self.say("गव्हाचा हमीभाव किती आहे?", "mr-IN")
        self.assertEqual(self.calls, [])
        self.assertIn("MSP", reply)

    def test_live_auction_question(self):
        reply = self.say("Is this the live auction price?")
        self.assertIn("not a live auction", reply)
        self.assertEqual(self.calls, [])

    def test_real_benchmark_through_mocked_api(self):
        main.fetch_mandi_benchmark = self._orig_fetch
        main.PRICE_CACHE.clear()
        today = main.datetime.now(main.IST).date().strftime("%d/%m/%Y")
        rows = [{"State": "Maharashtra", "District": "Pune", "Market": "Pune", "Commodity": "Wheat", "Variety": "Lokwan",
                 "Grade": "FAQ", "Arrival_Date": today, "Min_Price": "2300", "Max_Price": "2500", "Modal_Price": "2400", "_query_term": "Wheat"}]

        async def fake_rows(cid, form, dist):
            return rows, None, None

        orig_rows, orig_key = prices._fetch_data_gov_rows, prices.DATA_GOV_IN_API_KEY
        prices._fetch_data_gov_rows = fake_rows
        prices.DATA_GOV_IN_API_KEY = "test-api-key"
        try:
            reply = self.say("What is the wheat price in Pune today?")
        finally:
            prices._fetch_data_gov_rows, prices.DATA_GOV_IN_API_KEY = orig_rows, orig_key
            main.PRICE_CACHE.clear()
        self.assertIn("2,400", reply)
        self.assertIn(today, reply)
        self.assertIsNone(self.s["price_analysis"])  # selling-session price analysis untouched


class QuantityFlowTests(Base):
    def test_unclear_quantity_asks_clearer_form(self):
        self.say("I want to sell wheat.")
        self.say("Lokwan")
        reply = self.say("kuch quintal hai")
        self.assertEqual(self.s["waiting_for"], "quantity")
        self.assertIsNone(self.s["quantity_quintals"])
        self.assertIn("2 quintal", reply)
        self.say("two")
        self.assertEqual(self.s["quantity_quintals"], 2.0)

    def test_marathi_flow_spec_example(self):
        self.say("माझ्याकडे 4 किलो मकई आहे.", "mr-IN")
        self.assertEqual(self.s["waiting_for"], "variety")
        self.say("Yellow", "mr-IN")
        self.assertEqual(self.s["quantity_quintals"], 0.04)
        self.say("दोन quintal माल आहे", "mr-IN")  # explicit correction replaces
        self.assertEqual(self.s["quantity_quintals"], 2.0)
        self.assertNotEqual(self.s["waiting_for"], "quantity")

    def test_quality_answer_kilo_does_not_overwrite_quantity(self):
        self.s.update(commodity_id="wheat", commodity="Wheat", variety="Lokwan", quantity_quintals=5.0, district="Pune",
                      market_skipped=True, waiting_for="quality:cleanliness")
        self.say("thoda kachra hai, 10 kilo")
        self.assertEqual(self.s["quantity_quintals"], 5.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)