import logging
from typing import Any

from text_utils import ui_lang

log = logging.getLogger("saudavani")

_MSG: dict[str, dict[str, str]] = {
    "mr": {
        "commodity": "तुमच्याकडे कोणता माल आहे? उदाहरणार्थ सोयाबीन, गहू, ज्वारी, मूग, उडीद, मका, कांदा, बाजरी, हरभरा, तूर, कापूस किंवा भात/तांदूळ.",
        "ambiguous": "तुम्ही कोणत्या पिकाबद्दल बोलत आहात? कृपया नाव पुन्हा सांगा.",
        "product_form": "हा शेतातून आलेला कच्चा भात/धान आहे की सोललेला तयार तांदूळ?",
        "variety": "याचा कोणता वाण आहे? उपलब्ध प्रकार: {options}. माहीत नसेल तर 'माहीत नाही' सांगा.",
        "quantity": "तुमच्याकडे किती क्विंटल माल आहे?",
        "district": "तुम्हाला हा माल कोणत्या जिल्ह्यातील मंडीत विकायचा आहे? जिल्ह्याचे नाव सांगा.",
        "market": "{district} जिल्ह्यातील कोणत्या विशिष्ट मंडी/APMC मध्ये विकायचे आहे? नाव सांगा. विशिष्ट मंडी नसेल तर 'कोणतीही' म्हणा.",
        "quality": "{question}",
        "price_unavailable": "भाव डेटा उपलब्ध नाही (Price data unavailable). सध्या अधिकृत मंडी दर मिळत नाहीत, त्यामुळे मी अंदाजाने भाव सांगणार नाही. तरी तुमचा अपेक्षित दर सांगा; मी तो खरेदीदाराच्या प्रत्यक्ष भावाशी आणि तुमच्या किमान भावाशी तुलना करेन.",
        "price_ready": "{commodity} {market_scope} मधील {as_of} च्या उपलब्ध नोंदींनुसार {price_detail}हा रोजचा बाजार अहवाल आहे, हमीचा खरेदी भाव नाही. तुम्हाला किती भाव अपेक्षित आहे?",
        "ask_minimum": "तुम्हाला यापेक्षा कमी किती भाव मान्य होणार नाही? हा तुमचा खाजगी किमान भाव आहे; खरेदीदाराला सांगितला जाणार नाही. माहीत नसेल तर 'माहित नाही' सांगा.",
        "ask_buyer_offer": "खरेदीदाराने तुम्हाला किती रुपये प्रति क्विंटल भाव दिला आहे?",
        "price_stale": "{commodity} शेवटची उपलब्ध मंडी नोंद {as_of} ची आहे आणि ती जुनी आहे. त्या नोंदीतील संदर्भ दर ₹{modal:,.0f} प्रति क्विंटल होता, पण त्या आधारे आजचा भाव निश्चित सांगता येणार नाही. तुम्हाला किती भाव अपेक्षित आहे?",
        "offer_below": "खरेदीदाराचा ₹{offer:,.0f} भाव उपलब्ध तुलनात्मक मर्यादेपेक्षा कमी आहे. ₹{target:,.0f} प्रति क्विंटल हा तुलनात्मक बाजार नोंदींवर आधारित counter-target असू शकतो; हमी नाही. हा counter खरेदीदाराकडे पाठवू का?",
        "offer_stale": "खरेदीदाराचा भाव ₹{offer:,.0f} आहे, पण उपलब्ध मंडी संदर्भ उपलब्ध नाही किंवा जुना आहे. त्यामुळे हा भाव योग्य आहे की कमी, याची खात्री देता येत नाही. तुम्हाला हा भाव मान्य आहे की स्वतःच्या अपेक्षेनुसार बोलणी करायची आहेत?",
        "offer_in_range": "खरेदीदाराचा ₹{offer:,.0f} भाव उपलब्ध तुलनात्मक मर्यादेत आहे. एकूण रक्कम ₹{total:,.0f} होईल. तुम्हाला हा भाव मान्य आहे, अधिक भावासाठी बोलणी करायची आहेत, की व्यवहार रद्द करायचा आहे?",
        "offer_above": "खरेदीदाराचा ₹{offer:,.0f} भाव सध्याच्या तुलनात्मक संदर्भापेक्षा चांगला आहे. एकूण रक्कम ₹{total:,.0f} होईल. हा भाव आणि बाकी अटी तुम्हाला मान्य आहेत का?",
        "ask_counter": "तुम्हाला प्रति क्विंटल नेमका किती रुपये भाव हवा आहे? (उदा. 3200)",
        "counter_sent": "तुमचा ₹{counter:,.0f} प्रति क्विंटल counter-offer ({qty:g} क्विंटल, एकूण ₹{total:,.0f}) नोंदवला आहे. तुमची संमती नोंदली; खरेदीदाराची पुष्टी बाकी आहे आणि तोपर्यंत सौदा लॉक झालेला नाही.",
        "confirm_summary": "अंतिम तपशील ऐका: {commodity}, वाण {variety}, {qty:g} क्विंटल, बाजार {market}, दर्जाची माहिती {quality_summary}, दर ₹{price:,.0f} प्रति क्विंटल, एकूण रक्कम ₹{total:,.0f}. कपात अजून दिलेली नाही, त्यामुळे निव्वळ रक्कम निश्चित केलेली नाही. आता स्पष्ट सांगा: हो, हाच सौदा लॉक करा; भावावर पुन्हा बोलणी करा; किंवा रद्द करा.",
        "farmer_pending": "तुमची संमती नोंदवली आहे. व्यवहार लॉक होण्यासाठी खरेदीदाराचीही याच अटींवरील संमती बाकी आहे. अजून कोणतेही पैसे हलवलेले नाहीत.",
        "locked": "दोन्ही पक्षांची संमती नोंदली आहे. व्यवहाराच्या अटी लॉक झाल्या आहेत. व्यवहार क्रमांक {voucher}. एकूण व्यवहाराची रक्कम ₹{total:,.0f}. ही नोंद आहे; प्रत्यक्ष पैसे हस्तांतरित झालेले नाहीत.",
        "locked_demo": "डेमोमध्ये व्यवहार लॉक झाला आहे. व्यवहार क्रमांक {voucher}. एकूण रक्कम ₹{total:,.0f}. अंदाजित डेमो अॅडव्हान्स ₹{advance:,.0f}; प्रत्यक्ष पैसे हस्तांतरित झालेले नाहीत.",
        "cancelled": "व्यवहार रद्द केला आहे. कोणताही सौदा लॉक केलेला नाही.",
        "already_locked": "हा व्यवहार आधीच लॉक झाला आहे. व्यवहार क्रमांक {voucher}.",
        "not_offer": "मला सध्याच्या टप्प्यावर स्पष्ट खरेदीदाराचा भाव समजला नाही. कृपया रुपये प्रति क्विंटलमध्ये भाव सांगा.",
        "expired": "या भावाची ऑफर कालबाह्य झाली आहे. नवीन ऑफर घेऊन पुन्हा पुष्टी करावी लागेल.",
        "error": "क्षमा करा, काहीतरी अडचण आली. कृपया पुन्हा सांगा.",
    },
    "hi": {
        "commodity": "आपके पास कौन सी फसल है? जैसे सोयाबीन, गेहूं, ज्वार, मूंग, उड़द, मक्का, प्याज, बाजरा, चना, अरहर, कपास या धान/चावल।",
        "ambiguous": "आप किस फसल की बात कर रहे हैं? कृपया उसका नाम फिर से बताइए।",
        "product_form": "यह खेत से आया कच्चा धान है या मिलिंग के बाद तैयार चावल?",
        "variety": "इसकी कौन सी किस्म है? विकल्प: {options}. पता न हो तो 'पता नहीं' कहें।",
        "quantity": "आपके पास कितने क्विंटल माल है?",
        "district": "आप यह माल किस जिले की मंडी में बेचना चाहते हैं? जिले का नाम बताइए।",
        "market": "{district} जिले की किस खास मंडी/APMC में बेचना है? नाम बताइए। कोई खास मंडी न हो तो 'कोई भी' कहें।",
        "quality": "{question}",
        "price_unavailable": "भाव डेटा उपलब्ध नहीं (Price data unavailable)। अभी आधिकारिक मंडी भाव उपलब्ध नहीं हैं, इसलिए मैं अनुमान से रेट नहीं बताऊँगा। फिर भी अपना अपेक्षित भाव बताइए; मैं उसे खरीदार के वास्तविक ऑफर और आपके न्यूनतम भाव से तुलना करूँगा।",
        "price_ready": "{commodity} के लिए {market_scope} की {as_of} की उपलब्ध मंडी रिपोर्ट के अनुसार {price_detail}यह दैनिक रिपोर्ट है, पक्का खरीद भाव नहीं। आपको कितना भाव चाहिए?",
        "ask_minimum": "आप इससे कम कितना भाव स्वीकार नहीं करेंगे? यह आपका निजी न्यूनतम भाव है; खरीदार को नहीं बताया जाएगा। पता न हो तो 'पता नहीं' कहें।",
        "ask_buyer_offer": "खरीदार ने आपको कितने रुपये प्रति क्विंटल का भाव दिया है?",
        "price_stale": "{commodity} की आखिरी उपलब्ध मंडी रिपोर्ट {as_of} की है और पुरानी है। उसमें संदर्भ भाव ₹{modal:,.0f} प्रति क्विंटल था, पर इसे आज का पक्का भाव नहीं मानना चाहिए। आपको कितना भाव चाहिए?",
        "offer_below": "खरीदार का ₹{offer:,.0f} भाव तुलनात्मक सीमा से कम है। ₹{target:,.0f} प्रति क्विंटल तुलनात्मक बाजार रिकॉर्ड पर आधारित counter-target हो सकता है, गारंटी नहीं। क्या यह counter खरीदार को भेजें?",
        "offer_stale": "खरीदार का भाव ₹{offer:,.0f} है, लेकिन मंडी संदर्भ उपलब्ध नहीं है या पुराना है। इसलिए यह भाव सही है या कम, इसकी पुष्टि नहीं हो सकती। क्या आप यह भाव मानेंगे या अपनी अपेक्षा के अनुसार बात करेंगे?",
        "offer_in_range": "खरीदार का ₹{offer:,.0f} भाव उपलब्ध तुलनात्मक सीमा में है। कुल रकम ₹{total:,.0f} होगी। क्या आप इसे स्वीकार करेंगे, और भाव बढ़वाना चाहेंगे, या सौदा रद्द करेंगे?",
        "offer_above": "खरीदार का ₹{offer:,.0f} भाव मौजूदा तुलनात्मक संदर्भ से बेहतर है। कुल रकम ₹{total:,.0f} होगी। क्या यह भाव और बाकी शर्तें आपको मंजूर हैं?",
        "ask_counter": "आपको प्रति क्विंटल ठीक-ठीक कितने रुपये का भाव चाहिए? (जैसे 3200)",
        "counter_sent": "आपका ₹{counter:,.0f} प्रति क्विंटल का counter-offer ({qty:g} क्विंटल, कुल ₹{total:,.0f}) दर्ज है। आपकी मंजूरी दर्ज है; खरीदार की पुष्टि बाकी है और तब तक सौदा लॉक नहीं हुआ है।",
        "confirm_summary": "अंतिम जानकारी सुनिए: {commodity}, किस्म {variety}, {qty:g} क्विंटल, मंडी {market}, गुणवत्ता जानकारी {quality_summary}, भाव ₹{price:,.0f} प्रति क्विंटल, कुल रकम ₹{total:,.0f}। कटौती की जानकारी नहीं दी गई है, इसलिए शुद्ध रकम तय नहीं है। साफ बताइए: हाँ, इसी सौदे को लॉक करें; भाव पर फिर बात करें; या रद्द करें।",
        "farmer_pending": "आपकी मंजूरी दर्ज है। सौदा लॉक करने के लिए खरीदार की भी इन्हीं शर्तों पर मंजूरी बाकी है। अभी कोई पैसा ट्रांसफर नहीं हुआ है।",
        "locked": "दोनों पक्षों की मंजूरी दर्ज है। सौदे की शर्तें लॉक हो गई हैं। ट्रांजैक्शन नंबर {voucher}। कुल रकम ₹{total:,.0f}। यह केवल सौदे का रिकॉर्ड है; पैसा ट्रांसफर नहीं हुआ है।",
        "locked_demo": "डेमो में सौदा लॉक हो गया है। ट्रांजैक्शन नंबर {voucher}। कुल रकम ₹{total:,.0f}। अनुमानित डेमो एडवांस ₹{advance:,.0f}; असली पैसा ट्रांसफर नहीं हुआ है।",
        "cancelled": "सौदा रद्द कर दिया गया है। कोई सौदा लॉक नहीं हुआ है।",
        "already_locked": "यह सौदा पहले ही लॉक हो चुका है। ट्रांजैक्शन नंबर {voucher}।",
        "not_offer": "मुझे इस चरण में खरीदार का साफ ऑफर समझ नहीं आया। कृपया रुपये प्रति क्विंटल में भाव बताइए।",
        "expired": "यह ऑफर समय समाप्त होने के कारण एक्सपायर हो गया है। नई ऑफर लेकर फिर से पुष्टि करें।",
        "error": "माफ कीजिए, कुछ गड़बड़ हुई। कृपया फिर से बताइए।",
    },
    "en": {
        "commodity": "Which crop do you have? For example soybean, wheat, jowar, moong, urad, maize, onion, bajra, chana, tur, cotton, or paddy/rice.",
        "ambiguous": "Which crop do you mean? Please say the crop name again.",
        "product_form": "Is this raw paddy from the field, or milled/processed rice?",
        "variety": "Which variety is it? Options: {options}. Say 'not sure' if you do not know.",
        "quantity": "How many quintals do you have?",
        "district": "Which district's mandi do you want to sell in? Please tell me the district name.",
        "market": "Which specific mandi/APMC in {district} district do you want to sell in? Say 'any' if you have no specific mandi.",
        "quality": "{question}",
        "price_unavailable": "Price data unavailable. Official mandi prices are unavailable right now, so I will not guess a rate. You can still tell me your expected price; I can compare it with the buyer's actual offer and your private minimum.",
        "price_ready": "For {commodity}, the latest available {market_scope} report dated {as_of}: {price_detail}This is a daily market report, not a guaranteed buyer offer. What price are you expecting?",
        "ask_minimum": "What is the lowest price per quintal you would accept? This is private and will not be shown to the buyer. Say 'not sure' to skip.",
        "ask_buyer_offer": "What price per quintal has the buyer offered you?",
        "price_stale": "The latest available {commodity} market report is dated {as_of} and is stale; it showed a reference price of ₹{modal:,.0f} per quintal, but I cannot present it as today's price. What price are you expecting?",
        "offer_below": "The buyer's ₹{offer:,.0f} offer is below the comparable range. ₹{target:,.0f} per quintal may be a counter-target based on comparable market records, not a guarantee. Should I send this counter?",
        "offer_stale": "The buyer's offer is ₹{offer:,.0f}, but the mandi reference is unavailable or stale. I cannot verify whether it is fair today. Do you accept it, or would you like to negotiate based on your own expected price?",
        "offer_in_range": "The buyer's ₹{offer:,.0f} offer is within the available comparison range. The gross value is ₹{total:,.0f}. Would you accept, negotiate for more, or cancel?",
        "offer_above": "The buyer's ₹{offer:,.0f} offer is above the current comparison reference. The gross value is ₹{total:,.0f}. Do you accept this price and the other terms?",
        "ask_counter": "What exact price per quintal do you want to ask for? (for example 3200)",
        "counter_sent": "Your counter-offer of ₹{counter:,.0f} per quintal ({qty:g} quintals, gross ₹{total:,.0f}) is recorded. Your confirmation is recorded; the buyer's confirmation is pending and the deal is not locked.",
        "confirm_summary": "Please confirm the full terms: {commodity}, variety {variety}, {qty:g} quintals, market {market}, reported quality {quality_summary}, ₹{price:,.0f} per quintal, gross value ₹{total:,.0f}. Deductions have not been provided, so net proceeds are not yet determined. Say clearly: yes, lock these terms; negotiate again; or cancel.",
        "farmer_pending": "Your acceptance is recorded. The buyer must also confirm the exact same terms before the deal is locked. No money has moved.",
        "locked": "Both parties have confirmed the exact terms. The deal record is locked. Transaction ID {voucher}. Gross value ₹{total:,.0f}. This records the agreement only; no money has been transferred.",
        "locked_demo": "The deal is locked in single-party demo mode. Transaction ID {voucher}. Gross value ₹{total:,.0f}. Estimated demo advance ₹{advance:,.0f}; no real funds have been transferred.",
        "cancelled": "The negotiation has been cancelled. No deal was locked.",
        "already_locked": "This deal is already locked. Transaction ID {voucher}.",
        "not_offer": "I could not identify a clear buyer offer at this step. Please state the price in rupees per quintal.",
        "expired": "This offer has expired. A new offer and fresh confirmation are required.",
        "error": "Sorry, something went wrong. Please say that again.",
    },
}


_MSG["mr"]["escrow_simulated"] = "ही फक्त सिम्युलेशन आहे: सिम्युलेटेड एस्क्रो रेकॉर्ड {escrow_id} तयार झाला, सिम्युलेटेड निधी लॉक केला. प्रत्यक्ष हस्तांतरित झालेली रक्कम ₹0."
_MSG["hi"]["escrow_simulated"] = "यह केवल सिमुलेशन है: सिमुलेटेड एस्क्रो रिकॉर्ड {escrow_id} बना, सिमुलेटेड फंड लॉक किया गया। असल में ट्रांसफर हुई रकम ₹0।"
_MSG["en"]["escrow_simulated"] = "This is a SIMULATION only: simulated escrow record {escrow_id} was created and simulated funds are locked. Actual money transferred: ₹0."
_MSG["mr"]["buyer_offer_clarify"] = "तुम्हाला वर सांगितलेला मंडी संदर्भ भाव{ref} म्हणायचा आहे, की खरेदीदाराने प्रत्यक्ष दिलेला भाव? प्रत्यक्ष भाव असेल तर रुपयांत सांगा; नसेल तर 'खरेदीदाराचा भाव नाही' म्हणा."
_MSG["hi"]["buyer_offer_clarify"] = "आपका मतलब ऊपर बताए मंडी संदर्भ भाव{ref} से है, या खरीदार के असली ऑफर से? असली ऑफर हो तो रुपये में बताइए; न हो तो 'खरीदार का भाव नहीं' कहिए।"
_MSG["en"]["buyer_offer_clarify"] = "Do you mean the mandi reference price shown above{ref}, or an actual price the buyer offered you? If it is a buyer's offer, say the rupee amount; if not, say 'no buyer offer'."
_MSG["mr"]["buyer_offer_unavailable"] = "ठीक आहे, खरेदीदाराचा भाव नोंदवलेला नाही; मंडी संदर्भ भाव हा खरेदीदाराचा प्रस्ताव मानलेला नाही. तुम्ही खरेदीदाराकडे किती रुपये प्रति क्विंटल भाव मागू इच्छिता?"
_MSG["hi"]["buyer_offer_unavailable"] = "ठीक है, खरीदार का भाव दर्ज नहीं किया गया; मंडी संदर्भ भाव को खरीदार का प्रस्ताव नहीं माना गया है। आप खरीदार से कितने रुपये प्रति क्विंटल मांगना चाहेंगे?"
_MSG["en"]["buyer_offer_unavailable"] = "Okay, no buyer offer is recorded; the mandi reference price is not treated as a buyer's offer. What price per quintal would you like to ask the buyer for?"
_MSG["mr"]["counter_pending"] = "तुमचा ₹{price:,.0f} प्रति क्विंटलचा प्रस्ताव ({qty:g} क्विंटल, एकूण ₹{total:,.0f}) सक्रिय आहे. सौदा अजून लॉक झालेला नाही; खरेदीदाराने याच ऑफरची पुष्टी केल्यावरच तो लॉक होईल. कोणतेही पैसे हलवलेले नाहीत."
_MSG["hi"]["counter_pending"] = "आपका ₹{price:,.0f} प्रति क्विंटल का प्रस्ताव ({qty:g} क्विंटल, कुल ₹{total:,.0f}) सक्रिय है। सौदा अभी लॉक नहीं हुआ है; खरीदार के इसी ऑफर की पुष्टि करने पर ही लॉक होगा। कोई पैसा ट्रांसफर नहीं हुआ है।"
_MSG["en"]["counter_pending"] = "Your proposal of ₹{price:,.0f} per quintal ({qty:g} quintals, gross ₹{total:,.0f}) is active. The deal is not locked; it locks only after the buyer confirms this same offer. No money has moved."
_MSG["mr"]["clarify_decision"] = "मला नीट समजले नाही. तुम्हाला हा भाव मान्य आहे, जास्त भाव मागायचा आहे, ऑफर नाकारायची आहे की व्यवहार रद्द करायचा आहे?"
_MSG["hi"]["clarify_decision"] = "मैं ठीक से समझ नहीं पाया। क्या आप यह भाव मानते हैं, ज्यादा भाव मांगना चाहते हैं, ऑफर ठुकराना चाहते हैं, या सौदा रद्द करना चाहते हैं?"
_MSG["en"]["clarify_decision"] = "I did not quite understand. Do you accept this price, want to ask for more, reject the offer, or cancel the deal?"
_MSG["mr"]["offer_rejected"] = "ही ऑफर नाकारली आहे; ती आता पुन्हा पुष्टी करता येणार नाही. खरेदीदाराचा नवीन भाव रुपये प्रति क्विंटलमध्ये सांगा, किंवा माहीत नसेल तर 'माहीत नाही' म्हणा."
_MSG["hi"]["offer_rejected"] = "यह ऑफर ठुकरा दी गई है; अब इसकी पुष्टि नहीं हो सकती। खरीदार का नया भाव रुपये प्रति क्विंटल में बताइए, या पता न हो तो 'पता नहीं' कहिए।"
_MSG["en"]["offer_rejected"] = "This offer is rejected and can no longer be confirmed. Please tell me the buyer's new price per quintal, or say 'not sure'."
_MSG["mr"]["variety_note"] = "टीप: तुमचा नेमका वाण उपलब्ध नोंदींमध्ये सापडला नाही, त्यामुळे ही तुलना त्याच मालाच्या इतर उपलब्ध नोंदींवर आधारित आहे, वाणानुसार नाही."
_MSG["hi"]["variety_note"] = "ध्यान दें: आपकी सटीक किस्म उपलब्ध रिकॉर्ड में नहीं मिली, इसलिए यह तुलना उसी फसल के अन्य उपलब्ध रिकॉर्ड पर आधारित है, किस्म के अनुसार नहीं।"
_MSG["en"]["variety_note"] = "Note: your exact variety was not found in the available records, so this comparison uses other available records for the same commodity, not your variety."
_MSG["mr"]["market_note"] = "टीप: {market} मंडीची नोंद सापडली नाही, त्यामुळे संपूर्ण जिल्ह्यातील नोंदी वापरल्या आहेत."
_MSG["hi"]["market_note"] = "ध्यान दें: {market} मंडी का रिकॉर्ड नहीं मिला, इसलिए पूरे जिले के रिकॉर्ड इस्तेमाल किए गए हैं।"
_MSG["en"]["market_note"] = "Note: no record was found for {market}, so district-wide records were used."


_MSG["mr"]["offer_below_private"] = "खरेदीदाराचा ₹{offer:,.0f} भाव तुलनात्मक मर्यादेपेक्षा किंवा तुमच्या खाजगी किमान भावापेक्षा कमी आहे. तुमचा खाजगी भाव मी सांगत नाही. खरेदीदाराकडे किती रुपये प्रति क्विंटल मागायचे ते नेमके सांगा."
_MSG["hi"]["offer_below_private"] = "खरीदार का ₹{offer:,.0f} भाव तुलनात्मक सीमा से या आपके निजी न्यूनतम भाव से कम है। मैं आपका निजी भाव नहीं बताता। खरीदार से कितने रुपये प्रति क्विंटल मांगने हैं, ठीक-ठीक बताइए।"
_MSG["en"]["offer_below_private"] = "The buyer's ₹{offer:,.0f} offer is below the comparison range or your private minimum. I do not read your private prices out. Tell me the exact price per quintal you want to ask the buyer for."
_MSG["mr"]["voice_action_disabled"] = "ही सुविधा सध्या बंद आहे: या प्रोटोटाइपमध्ये बोलणारी व्यक्ती कोण आहे हे तपासता येत नाही, म्हणून आवाजाने अंतिम संमती किंवा सौदा रद्द करता येत नाही. काहीही बदललेले नाही; सौदा लॉकही झालेला नाही आणि रद्दही झालेला नाही."
_MSG["hi"]["voice_action_disabled"] = "यह सुविधा अभी बंद है: इस प्रोटोटाइप में बोलने वाले की पहचान जाँची नहीं जा सकती, इसलिए आवाज़ से अंतिम मंजूरी या सौदा रद्द नहीं हो सकता। कुछ भी नहीं बदला है; सौदा न लॉक हुआ है, न रद्द।"
_MSG["en"]["voice_action_disabled"] = "This is switched off: the prototype cannot verify who is speaking, so final confirmation and cancellation by voice are disabled. Nothing was changed; the deal was neither locked nor cancelled."
_MSG["mr"]["counter_skipped"] = "ठीक आहे, अजून कोणताही counter नोंदवलेला नाही. भाव ठरवला की रुपये प्रति क्विंटलमध्ये सांगा."
_MSG["hi"]["counter_skipped"] = "ठीक है, अभी कोई counter दर्ज नहीं किया गया। भाव तय हो जाए तो रुपये प्रति क्विंटल में बता दीजिए।"
_MSG["en"]["counter_skipped"] = "Okay, no counter is recorded yet. Tell me the price per quintal whenever you have decided."
# Hinglish = natural Roman-script Hindi with English trading words. Same state and logic as every other language.
_MSG["hinglish"] = {
    "commodity": "Aapke paas kaunsi fasal hai? Jaise soybean, gehun, jowar, moong, urad, makka, pyaaz, bajra, chana, tur, kapas ya dhan/chawal.",
    "ambiguous": "Aap kis fasal ki baat kar rahe hain? Please naam dobara bataiye.",
    "product_form": "Yeh khet ka kaccha dhan (paddy) hai ya mill kiya hua tayyar chawal?",
    "variety": "Iski kaun si variety hai? Options: {options}. Pata na ho to 'pata nahi' bol dijiye.",
    "quantity": "Aapke paas kitne quintal maal hai?",
    "district": "Aap yeh maal kis district ki mandi mein bechna chahte hain? District ka naam bataiye.",
    "market": "{district} district ki kis specific mandi/APMC mein bechna hai? Naam bataiye. Koi khaas mandi na ho to 'koi bhi mandi' bol dijiye.",
    "quality": "{question}",
    "price_unavailable": "Price data unavailable. Abhi official mandi bhav nahi mil rahe, isliye main andaze se rate nahi bataunga. Phir bhi apna expected bhav bataiye; main use buyer ke asli offer aur aapke minimum bhav se compare karunga.",
    "price_ready": "{commodity} ke liye {market_scope} ki {as_of} ki latest mandi report ke mutabik {price_detail}Yeh daily market report hai, pakka buyer offer nahi. Aap kitna bhav expect kar rahe hain?",
    "ask_minimum": "Aap isse kam kitna bhav kabool nahi karenge? Yeh aapka private minimum hai; buyer ko nahi bataya jayega. Pata na ho to 'pata nahi' bol dijiye.",
    "ask_buyer_offer": "Buyer ne aapko kitne rupaye prati quintal ka offer diya hai?",
    "price_stale": "{commodity} ki sabse latest mandi report {as_of} ki hai aur purani hai. Usme reference bhav ₹{modal:,.0f} prati quintal tha, lekin ise aaj ka pakka bhav nahi maana ja sakta. Aap kitna bhav expect kar rahe hain?",
    "offer_below": "Buyer ka ₹{offer:,.0f} ka offer comparison range se kam hai. ₹{target:,.0f} prati quintal ek counter-target ho sakta hai, guarantee nahi. Kya yeh counter buyer ko bhejun?",
    "offer_stale": "Buyer ka offer ₹{offer:,.0f} hai, lekin mandi reference available nahi hai ya purana hai. Isliye main pakka nahi keh sakta ki yeh bhav theek hai ya kam. Kya aap ise accept karenge ya apne expected bhav par baat karenge?",
    "offer_in_range": "Buyer ka ₹{offer:,.0f} ka offer available range mein hai. Gross value ₹{total:,.0f} hogi. Aap accept karenge, zyada bhav ke liye negotiate karenge, ya deal cancel karenge?",
    "offer_above": "Buyer ka ₹{offer:,.0f} ka offer current reference se achha hai. Gross value ₹{total:,.0f} hogi. Kya aapko yeh bhav aur baaki shartein manzoor hain?",
    "ask_counter": "Aapko prati quintal exact kitne rupaye ka bhav chahiye? (jaise 3200)",
    "counter_sent": "Aapka ₹{counter:,.0f} prati quintal ka counter-offer ({qty:g} quintal, gross ₹{total:,.0f}) record ho gaya hai. Aapki confirmation darj hai, buyer ki confirmation baaki hai; tab tak deal lock nahi hui hai.",
    "confirm_summary": "Final details suniye: {commodity}, variety {variety}, {qty:g} quintal, mandi {market}, quality jaankari {quality_summary}, bhav ₹{price:,.0f} prati quintal, gross value ₹{total:,.0f}. Deductions abhi nahi diye gaye, isliye net amount tay nahi hai. Saaf bataiye: haan, yeh deal lock karo; bhav par phir baat karo; ya cancel karo.",
    "farmer_pending": "Aapki confirmation darj hai. Deal lock hone ke liye buyer ko bhi yehi offer confirm karna hoga. Abhi koi paisa transfer nahi hua hai.",
    "locked": "Dono parties ki confirmation darj hai. Deal ki shartein lock ho gayi hain. Transaction ID {voucher}. Gross value ₹{total:,.0f}. Yeh sirf agreement ka record hai; koi paisa transfer nahi hua.",
    "locked_demo": "Demo mode mein deal lock ho gayi hai. Transaction ID {voucher}. Gross value ₹{total:,.0f}. Estimated demo advance ₹{advance:,.0f}; asli paisa transfer nahi hua.",
    "cancelled": "Deal cancel kar di gayi hai. Koi deal lock nahi hui.",
    "already_locked": "Yeh deal pehle hi lock ho chuki hai. Transaction ID {voucher}.",
    "not_offer": "Mujhe is step par buyer ka saaf offer samajh nahi aaya. Please rupaye prati quintal mein bhav bataiye.",
    "expired": "Yeh offer expire ho gaya hai. Naya offer lekar dobara confirm karna hoga.",
    "error": "Maaf kijiye, kuch gadbad ho gayi. Please phir se bataiye.",
    "escrow_simulated": "Yeh sirf SIMULATION hai: simulated escrow record {escrow_id} bana, simulated funds lock kiye gaye. Asli transfer hui rakam ₹0.",
    "buyer_offer_clarify": "Aapka matlab upar bataye gaye mandi reference bhav{ref} se hai, ya buyer ke asli offer se? Asli offer ho to rupaye mein bataiye; na ho to 'buyer ka offer nahi' bol dijiye.",
    "buyer_offer_unavailable": "Theek hai, buyer ka offer record nahi kiya gaya; mandi reference bhav ko buyer ka offer nahi mana gaya hai. Aap buyer se kitne rupaye prati quintal maangna chahenge?",
    "counter_pending": "Aapka ₹{price:,.0f} prati quintal ka offer ({qty:g} quintal, gross ₹{total:,.0f}) active hai. Deal abhi lock nahi hui; buyer ke yehi offer confirm karne par hi lock hogi. Koi paisa transfer nahi hua.",
    "clarify_decision": "Main theek se samajh nahi paya. Aap yeh bhav accept karte hain, zyada bhav maangna chahte hain, offer reject karna chahte hain, ya deal cancel karna chahte hain?",
    "offer_rejected": "Yeh offer reject ho gaya hai aur ab confirm nahi ho sakta. Buyer ka naya bhav rupaye prati quintal mein bataiye, ya pata na ho to 'pata nahi' bol dijiye.",
    "counter_skipped": "Theek hai, abhi koi counter record nahi hua. Bhav tay ho jaye to rupaye prati quintal mein bata dijiye.",
    "offer_below_private": "Buyer ka ₹{offer:,.0f} ka offer comparison range se ya aapke private minimum se kam hai. Main aapka private bhav nahi bataunga. Buyer se prati quintal kitne rupaye maangne hain, exact bataiye.",
    "voice_action_disabled": "Yeh suvidha abhi band hai: is prototype mein bolne wale ki pehchaan verify nahi ho sakti, isliye awaaz se final confirmation ya deal cancel nahi ho sakta. Kuch bhi nahi badla; deal na lock hui hai, na cancel.",
    "variety_note": "Dhyan dein: aapki exact variety available records mein nahi mili, isliye yeh comparison usi fasal ki doosri varieties ke records par based hai, aapki variety ka nahi.",
    "market_note": "Dhyan dein: {market} mandi ka record nahi mila, isliye poore district ke records use kiye gaye hain.",
}

_MSG["mr"]["notice_buyer_offer"] = "खरेदीदाराने ₹{price:,.0f} प्रति क्विंटल भाव पाठवला आहे ({qty:g} क्विंटल, एकूण ₹{total:,.0f})."
_MSG["hi"]["notice_buyer_offer"] = "खरीदार ने ₹{price:,.0f} प्रति क्विंटल का भाव भेजा है ({qty:g} क्विंटल, कुल ₹{total:,.0f})।"
_MSG["en"]["notice_buyer_offer"] = "The buyer submitted ₹{price:,.0f} per quintal ({qty:g} quintals, gross ₹{total:,.0f})."
_MSG["hinglish"]["notice_buyer_offer"] = "Buyer ne ₹{price:,.0f} prati quintal ka bhav bheja hai ({qty:g} quintal, gross ₹{total:,.0f})."

_MSG["mr"]["notice_buyer_accepted_locked"] = "खरेदीदाराने तुमची ऑफर मान्य केली. दोन्ही पक्षांची संमती नोंदली आहे; व्यवहाराच्या अटी लॉक झाल्या आहेत. व्यवहार क्रमांक {voucher}. एकूण रक्कम ₹{total:,.0f}. ही फक्त नोंद आहे; प्रत्यक्ष पैसे हस्तांतरित झालेले नाहीत. ही फक्त सिम्युलेशन आहे: सिम्युलेटेड एस्क्रो रेकॉर्ड {escrow_id} तयार झाला, सिम्युलेटेड निधी लॉक केला. प्रत्यक्ष हस्तांतरित झालेली रक्कम ₹0."
_MSG["hi"]["notice_buyer_accepted_locked"] = "खरीदार ने आपकी ऑफर मंजूर कर ली। दोनों पक्षों की मंजूरी दर्ज है; सौदे की शर्तें लॉक हो गई हैं। ट्रांजैक्शन नंबर {voucher}। कुल रकम ₹{total:,.0f}। यह केवल रिकॉर्ड है; पैसा ट्रांसफर नहीं हुआ है। यह केवल सिमुलेशन है: सिमुलेटेड एस्क्रो रिकॉर्ड {escrow_id} बना, सिमुलेटेड फंड लॉक किया गया। असल में ट्रांसफर हुई रकम ₹0।"
_MSG["en"]["notice_buyer_accepted_locked"] = "The buyer accepted your offer. Both parties have confirmed and the deal record is locked. Transaction ID {voucher}. Gross value ₹{total:,.0f}. This records the agreement only; no money has been transferred. This is a SIMULATION only: simulated escrow record {escrow_id} was created and simulated funds are locked. Actual money transferred: ₹0."
_MSG["hinglish"]["notice_buyer_accepted_locked"] = "Buyer ne aapka offer accept kar liya. Dono parties ki confirmation darj hai aur deal lock ho gayi hai. Transaction ID {voucher}. Gross value ₹{total:,.0f}. Yeh sirf agreement ka record hai; koi paisa transfer nahi hua. Yeh sirf SIMULATION hai: simulated escrow record {escrow_id} bana, simulated funds lock kiye gaye. Asli transfer hui rakam ₹0."

_MSG["mr"]["notice_buyer_rejected"] = "खरेदीदाराने तुमची ऑफर नाकारली आहे. ती आता पुन्हा पुष्टी करता येणार नाही; नवीन ऑफर आवश्यक आहे."
_MSG["hi"]["notice_buyer_rejected"] = "खरीदार ने आपकी ऑफर ठुकरा दी है। अब इसकी पुष्टि नहीं हो सकती; नई ऑफर चाहिए।"
_MSG["en"]["notice_buyer_rejected"] = "The buyer rejected your offer. It can no longer be confirmed; a fresh offer is needed."
_MSG["hinglish"]["notice_buyer_rejected"] = "Buyer ne aapka offer reject kar diya hai. Ab yeh confirm nahi ho sakta; naya offer chahiye."

# Messages for information questions, selling-intent help and honest fallbacks (all four spoken languages).
_NEW_MSG: dict[str, dict[str, str]] = {
        "no_send_ack": {
        "mr": "ठीक आहे, कोणताही offer तयार किंवा पाठवला जाणार नाही.",
        "hi": "ठीक है, कोई ऑफर न बनाई जाएगी, न भेजी जाएगी।",
        "en": "Okay, no offer will be created or sent.",
        "hinglish": "Theek hai, koi offer na banega, na bheja jayega.",
    },
    "hold_ack": {
        "mr": "ठीक आहे, मी थांबतो. काहीही पाठवले जाणार नाही.",
        "hi": "ठीक है, मैं रुकता हूँ। कुछ भी नहीं भेजा जाएगा।",
        "en": "Okay, I will wait. Nothing will be sent.",
        "hinglish": "Theek hai, main ruk jata hoon. Kuch nahi bheja jayega.",
    },
    "info_price": {
        "en": "For {commodity}, the latest {market_scope} report is dated {as_of}: {price_detail}This is a daily AGMARKNET mandi report, not a live auction price or a buyer's offer.",
        "hi": "{commodity} के लिए {market_scope} की {as_of} की ताज़ा उपलब्ध रिपोर्ट के अनुसार {price_detail}यह AGMARKNET की दैनिक मंडी रिपोर्ट है, लाइव नीलामी भाव या खरीदार का पक्का भाव नहीं।",
        "mr": "{commodity} {market_scope} मधील {as_of} च्या ताज्या उपलब्ध नोंदींनुसार {price_detail}हा AGMARKNET चा रोजचा मंडी अहवाल आहे; थेट लिलावाचा भाव किंवा खरेदीदाराचा पक्का भाव नाही.",
        "hinglish": "{commodity} ke liye {market_scope} ki {as_of} ki latest mandi report ke mutabik {price_detail}Yeh AGMARKNET ki daily mandi report hai, live auction bhav ya buyer ka pakka offer nahi.",
    },
    "info_price_stale": {
        "en": "The latest available report for {commodity} is dated {as_of}; it is old and may not reflect today's market. For {market_scope}: {price_detail}This is a daily AGMARKNET mandi report, not a live auction price.",
        "hi": "{commodity} की आखिरी उपलब्ध मंडी रिपोर्ट {as_of} की है; वह पुरानी है और आज के बाज़ार को नहीं दिखाती। {market_scope}: {price_detail}यह AGMARKNET की दैनिक रिपोर्ट है, लाइव नीलामी भाव नहीं।",
        "mr": "{commodity} शेवटची उपलब्ध मंडी नोंद {as_of} ची आहे; ती जुनी आहे आणि आजचा बाजार दाखवत नाही. {market_scope}: {price_detail}हा AGMARKNET चा रोजचा अहवाल आहे, थेट लिलावाचा भाव नाही.",
        "hinglish": "{commodity} ki sabse latest mandi report {as_of} ki hai; woh purani hai aur aaj ka bazaar nahi dikhati. {market_scope}: {price_detail}Yeh AGMARKNET ki daily report hai, live auction bhav nahi.",
    },
    "info_price_unavailable": {
        "en": "I could not get an official mandi price for {commodity} in {district} right now (the AGMARKNET data on data.gov.in had no usable record or could not be reached), so I will not guess a rate.",
        "hi": "अभी {district} में {commodity} का आधिकारिक मंडी भाव नहीं मिल पाया (data.gov.in के AGMARKNET डेटा में उपयोगी रिकॉर्ड नहीं मिला या डेटा तक पहुँच नहीं हो सकी), इसलिए मैं अंदाज़े से भाव नहीं बताऊँगा।",
        "mr": "सध्या {district} मधील {commodity} चा अधिकृत मंडी भाव मिळाला नाही (data.gov.in च्या AGMARKNET डेटामध्ये उपयुक्त नोंद नाही किंवा डेटा मिळू शकला नाही), त्यामुळे मी अंदाजाने भाव सांगणार नाही.",
        "hinglish": "Abhi {district} mein {commodity} ka official mandi bhav nahi mil paaya (data.gov.in ke AGMARKNET data mein koi usable record nahi mila ya data tak pahunch nahi hui), isliye main andaze se rate nahi bataunga.",
    },
    "info_ask_district": {
        "en": "Which district's {commodity} mandi price should I check? Please tell me the district name.",
        "hi": "{commodity} का मंडी भाव किस जिले का देखूँ? जिले का नाम बताइए।",
        "mr": "{commodity} चा मंडी भाव कोणत्या जिल्ह्याचा पाहू? जिल्ह्याचे नाव सांगा.",
        "hinglish": "{commodity} ka mandi bhav kis district ka dekhun? District ka naam bataiye.",
    },
    "info_ask_commodity": {
        "en": "Which crop's mandi price do you want to know?",
        "hi": "आप किस फसल का मंडी भाव जानना चाहते हैं?",
        "mr": "तुम्हाला कोणत्या पिकाचा मंडी भाव जाणून घ्यायचा आहे?",
        "hinglish": "Aap kis fasal ka mandi bhav jaanna chahte hain?",
    },
    "info_msp": {
        "en": "I cannot give or verify MSP here. This assistant only reads daily mandi price reports (modal prices) from AGMARKNET, and a mandi modal price is not MSP. Please check the government's official MSP announcement for your crop.",
        "hi": "मैं यहाँ MSP बता या सत्यापित नहीं कर सकता। यह सहायक सिर्फ AGMARKNET की दैनिक मंडी भाव रिपोर्ट (मोडल भाव) देखता है, और मंडी का मोडल भाव MSP नहीं होता। अपनी फसल के लिए सरकार की आधिकारिक MSP घोषणा देखिए।",
        "mr": "मी इथे MSP सांगू किंवा तपासू शकत नाही. हा सहाय्यक फक्त AGMARKNET चे रोजचे मंडी भाव अहवाल (मोडल दर) वाचतो, आणि मंडीचा मोडल दर म्हणजे MSP नव्हे. तुमच्या पिकासाठी सरकारची अधिकृत MSP घोषणा पाहा.",
        "hinglish": "Main yahan MSP bata ya verify nahi kar sakta. Yeh assistant sirf AGMARKNET ki daily mandi bhav report (modal price) padhta hai, aur mandi ka modal price MSP nahi hota. Apni fasal ke liye sarkar ki official MSP ghoshna dekhiye.",
    },
    "info_modal": {
        "en": "Modal price is the price at which most of the quantity traded in a mandi on the reported day. The mandi reports it together with the minimum and maximum price; I do not calculate it. When I combine several markets I call it a calculated median, not an official modal price.",
        "hi": "मोडल भाव वह भाव है जिस पर रिपोर्ट के दिन मंडी में सबसे ज्यादा माल बिका। मंडी इसे न्यूनतम और अधिकतम भाव के साथ दर्ज करती है; मैं इसे खुद नहीं निकालता। कई मंडियों को मिलाकर जो निकालता हूँ उसे मैं गणना किया हुआ मध्यमान कहता हूँ, आधिकारिक मोडल भाव नहीं।",
        "mr": "मोडल दर म्हणजे नोंद झालेल्या दिवशी मंडीत सर्वाधिक माल ज्या भावाने विकला गेला तो भाव. मंडी तो किमान आणि कमाल भावासोबत नोंदवते; मी तो स्वतः काढत नाही. अनेक मंडी मिळवून मी काढलेल्या आकड्याला मी 'काढलेला मध्यक' म्हणतो, अधिकृत मोडल दर नाही.",
        "hinglish": "Modal price woh bhav hai jis par report wale din mandi mein sabse zyada maal bika. Mandi ise minimum aur maximum bhav ke saath darj karti hai; main ise khud calculate nahi karta. Kai mandiyon ko milakar jo nikalta hoon use main calculated median kehta hoon, official modal price nahi.",
    },
    "info_live": {
        "en": "No. The AGMARKNET figures are daily reported mandi prices for trades that already happened, not a live auction bid or a guaranteed buyer offer. I always tell you the report date.",
        "hi": "नहीं। AGMARKNET के आँकड़े पहले हो चुके सौदों के दैनिक दर्ज मंडी भाव हैं, लाइव नीलामी बोली या खरीदार का पक्का ऑफर नहीं। रिपोर्ट की तारीख मैं हमेशा बताता हूँ।",
        "mr": "नाही. AGMARKNET चे आकडे आधीच झालेल्या व्यवहारांचे रोजचे नोंदवलेले मंडी भाव आहेत, थेट लिलावाची बोली किंवा खरेदीदाराचा पक्का भाव नाही. अहवालाची तारीख मी नेहमी सांगतो.",
        "hinglish": "Nahi. AGMARKNET ke figures pehle ho chuke sauda ke daily reported mandi bhav hain, live auction bid ya buyer ka pakka offer nahi. Report ki date main hamesha batata hoon.",
    },
    "howto_sell": {
        "en": "Tell me your crop, variety, quantity and district. I will check the latest official mandi price report, then you can share the buyer's offer and I will help you compare and negotiate. Nothing is locked until both sides confirm.",
        "hi": "आप अपनी फसल, किस्म, मात्रा और जिला बताइए। मैं ताज़ा आधिकारिक मंडी भाव रिपोर्ट देखूँगा, फिर आप खरीदार का ऑफर बता सकते हैं और मैं तुलना व मोलभाव में मदद करूँगा। दोनों पक्षों की पुष्टि से पहले कुछ भी लॉक नहीं होता।",
        "mr": "तुमचे पीक, वाण, प्रमाण आणि जिल्हा सांगा. मी ताजा अधिकृत मंडी भाव अहवाल पाहीन, मग तुम्ही खरेदीदाराचा भाव सांगू शकता आणि मी तुलना व बोलणीत मदत करेन. दोन्ही पक्षांनी पुष्टी करेपर्यंत काहीही लॉक होत नाही.",
        "hinglish": "Aap apni fasal, variety, quantity aur district bataiye. Main latest official mandi bhav report dekhunga, phir aap buyer ka offer bata sakte hain aur main compare aur negotiate karne mein madad karunga. Dono parties ke confirm karne se pehle kuch bhi lock nahi hota.",
    },
    "offer_sell": {
        "en": "If you want to sell something, just tell me your crop.",
        "hi": "अगर आप अपना माल बेचना चाहते हैं तो बस अपनी फसल बताइए।",
        "mr": "तुम्हाला माल विकायचा असेल तर फक्त तुमचे पीक सांगा.",
        "hinglish": "Agar aap apna maal bechna chahte hain to bas apni fasal bataiye.",
    },
    "quantity_unclear": {
        "en": "I could not catch the quantity. Please say it like '2 quintal' or '50 kilo'.",
        "hi": "मैं मात्रा ठीक से नहीं समझ पाया। कृपया 'दो क्विंटल' या '50 किलो' जैसे बताइए।",
        "mr": "मला प्रमाण नीट समजले नाही. कृपया 'दोन क्विंटल' किंवा '50 किलो' असे सांगा.",
        "hinglish": "Main quantity theek se nahi samajh paya. Please '2 quintal' ya '50 kilo' jaise bataiye.",
    },
    "ask_target": {
        "en": "What price per quintal are you expecting?",
        "hi": "आपको प्रति क्विंटल कितना भाव चाहिए?",
        "mr": "तुम्हाला प्रति क्विंटल किती भाव अपेक्षित आहे?",
        "hinglish": "Aap prati quintal kitna bhav expect kar rahe hain?",
    },
    "pending_decision": {
        "en": "Do you accept this price, want to negotiate, or cancel the deal?",
        "hi": "क्या आप यह भाव स्वीकार करते हैं, मोलभाव करना चाहते हैं, या सौदा रद्द करना चाहते हैं?",
        "mr": "तुम्हाला हा भाव मान्य आहे, बोलणी करायची आहेत की व्यवहार रद्द करायचा आहे?",
        "hinglish": "Aap yeh bhav accept karte hain, negotiate karna chahte hain, ya deal cancel karna chahte hain?",
    },
    "offline_answer": {
        "en": "I cannot give a detailed answer to that right now because my question-answering assistant is not available. I can still check official mandi prices and help with your sale.",
        "hi": "अभी मैं इसका विस्तृत जवाब नहीं दे सकता क्योंकि मेरा सवाल-जवाब सहायक उपलब्ध नहीं है। फिर भी मैं आधिकारिक मंडी भाव देख सकता हूँ और आपकी बिक्री में मदद कर सकता हूँ।",
        "mr": "सध्या मी याचे सविस्तर उत्तर देऊ शकत नाही, कारण माझा प्रश्न-उत्तर सहाय्यक उपलब्ध नाही. तरीही मी अधिकृत मंडी भाव पाहू शकतो आणि तुमच्या विक्रीत मदत करू शकतो.",
        "hinglish": "Abhi main iska detailed jawab nahi de sakta kyunki mera question-answer assistant available nahi hai. Phir bhi main official mandi bhav check kar sakta hoon aur aapki bikri mein madad kar sakta hoon.",
    },
        "counter_summary": {
        "mr": "तुमचा प्रस्ताव: {commodity}, {qty:g} क्विंटल, {district}, ₹{price:,.0f} प्रति क्विंटल, एकूण ₹{total:,.0f}. अजून काहीही पाठवलेले नाही. पाठवायचा असल्यास 'हो, पाठवा' म्हणा; दुसरा भावही सांगू शकता.",
        "hi": "आपका प्रस्ताव: {commodity}, {qty:g} क्विंटल, {district}, ₹{price:,.0f} प्रति क्विंटल, कुल ₹{total:,.0f}। अभी कुछ भी नहीं भेजा गया है। भेजना हो तो 'हाँ, भेजो' कहें; दूसरा भाव भी बता सकते हैं।",
        "en": "Your proposal: {commodity}, {qty:g} quintals, {district}, ₹{price:,.0f} per quintal, total ₹{total:,.0f}. Nothing has been sent yet. Say 'yes, send' to send it, or give a different price.",
        "hinglish": "Aapka prastaav: {commodity}, {qty:g} quintal, {district}, ₹{price:,.0f} prati quintal, total ₹{total:,.0f}. Abhi kuch bheja nahi gaya hai. Bhejna ho to 'haan, bhejo' bolein; doosra bhav bhi bata sakte hain."
    },
    "counter_not_sent": {
        "mr": "तुम्ही आधी थांबायला किंवा पाठवू नका असे सांगितले होते, म्हणून काहीही पाठवलेले नाही. पाठवायचे असल्यास 'ऑफर पाठवा' म्हणा.",
        "hi": "आपने पहले रुकने या न भेजने को कहा था, इसलिए कुछ नहीं भेजा गया। भेजना हो तो 'ऑफर भेजो' कहें।",
        "en": "You asked me to wait or not send, so nothing was sent. Say 'send the offer' when you want it sent.",
        "hinglish": "Aapne pehle rukne ya na bhejne ko kaha tha, isliye kuch nahi bheja gaya. Bhejna ho to 'offer bhejo' bolein."
    },
    # --- Step 2E: controlled market clarification (no literal free-text market names) ---
    "market_clarify": {
        "mr": "ती मंडी मला ओळखता आली नाही. कृपया मंडी/APMC चे नाव सांगा (उदा. लासलगाव, बारामती), किंवा कोणतीही मंडी चालत असेल तर 'कोणतीही' म्हणा.",
        "hi": "वह मंडी मैं पहचान नहीं पाया। कृपया मंडी/APMC का नाम बताइए (जैसे लासलगाँव, बारामती), या कोई भी मंडी चलेगी तो 'कोई भी' कहिए।",
        "en": "I could not recognise that mandi. Please tell me a mandi/APMC name (for example Lasalgaon or Baramati), or say 'any market' if any mandi is fine.",
        "hinglish": "Main woh mandi pehchan nahi paya. Please mandi/APMC ka naam bataiye (jaise Lasalgaon ya Baramati), ya koi bhi mandi chalegi to 'koi bhi mandi' bol dijiye.",
    },
    # --- Step 2D: farmer FAQ answers ---
    "faq_escrow": {
        "mr": "येथील एस्क्रो फक्त सिम्युलेशन आहे. कोणतेही खरे पैसे ठेवले किंवा हलवले जात नाहीत; प्रत्यक्ष हस्तांतरित झालेली रक्कम ₹0 आहे.",
        "hi": "यहाँ का एस्क्रो केवल सिमुलेशन है। कोई असली पैसा रखा या ट्रांसफर नहीं किया जाता; असल में ट्रांसफर हुई रकम ₹0 है।",
        "en": "The escrow here is a simulation. No real money is held or moved; actual money transferred is ₹0.",
        "hinglish": "Yahan ka escrow sirf simulation hai. Koi asli paisa rakha ya transfer nahi hota; asli transfer hui rakam ₹0 hai.",
    },
    "faq_payment_timing": {
        "mr": "सौदावाणी पैसे हलवत नाही आणि पेमेंटच्या तारखा ठरवत नाही. माल देण्यापूर्वी पेमेंटची तारीख आणि पद्धत खरेदीदाराशी लेखी ठरवा.",
        "hi": "सौदावाणी पैसे ट्रांसफर नहीं करता और भुगतान की तारीख तय नहीं करता। माल सौंपने से पहले भुगतान की तारीख और तरीका खरीदार से लिखित में तय करें।",
        "en": "SaudaVani does not move money or set payment dates. Agree the payment date and mode with the buyer in writing before you hand over the goods.",
        "hinglish": "SaudaVani paisa transfer nahi karta aur payment ki date tay nahi karta. Maal dene se pehle payment ki date aur tareeka buyer se likhit mein tay kar lijiye.",
    },
    "faq_payment_recovery": {
        "mr": "सौदावाणी पेमेंट वसूल करत नाही किंवा त्याची हमी देत नाही. येथे लॉक झालेला सौदा म्हणजे ठरलेल्या अटींची फक्त नोंद आहे.",
        "hi": "सौदावाणी भुगतान वसूल नहीं करता और उसकी गारंटी नहीं देता। यहाँ लॉक हुआ सौदा केवल तय शर्तों का रिकॉर्ड है।",
        "en": "SaudaVani does not recover or guarantee payment. A locked deal here is only a record of agreed terms.",
        "hinglish": "SaudaVani payment recover nahi karta aur uski guarantee nahi deta. Yahan lock hui deal sirf tay ki gayi shartein ka record hai.",
    },
    "faq_buyer_verification": {
        "mr": "सौदावाणी खरेदीदारांची पडताळणी करत नाही. या प्रोटोटाइपमध्ये खरेदीदाराची ओळख तपासली जात नाही.",
        "hi": "सौदावाणी खरीदारों का सत्यापन नहीं करता। इस प्रोटोटाइप में खरीदार की पहचान की जाँच नहीं होती।",
        "en": "SaudaVani does not verify buyers. Buyer identity is not authenticated in this prototype.",
        "hinglish": "SaudaVani buyers ko verify nahi karta. Is prototype mein buyer ki pehchaan authenticate nahi hoti.",
    },
    "faq_weighing": {
        "mr": "सौदावाणी तुमचा माल तोलत नाही. वजन खरेदीदाराशी लेखी ठरवा.",
        "hi": "सौदावाणी आपका माल तौलता नहीं है। वजन खरीदार से लिखित में तय करें।",
        "en": "SaudaVani does not weigh your produce. Agree the weight in writing with the buyer.",
        "hinglish": "SaudaVani aapka maal tolta nahi hai. Weight buyer se likhit mein tay kar lijiye.",
    },
    "faq_net_amount": {
        "mr": "दाखवलेली रक्कम एकूण (ग्रॉस) आहे, म्हणजे प्रमाण गुणिले भाव. कपात धरलेली नाही, त्यामुळे निव्वळ रक्कम ठरलेली नाही; कपाती लेखी ठरवा.",
        "hi": "दिखाई गई रकम कुल (ग्रॉस) है, यानी मात्रा गुणा भाव। कटौती शामिल नहीं है, इसलिए शुद्ध रकम तय नहीं है; कटौती लिखित में तय करें।",
        "en": "The amount shown is gross, quantity multiplied by price. Deductions are not included, so the net amount is not determined; agree deductions in writing.",
        "hinglish": "Dikhayi gayi rakam gross hai, yani quantity guna bhav. Deductions shamil nahi hain, isliye net amount tay nahi hai; deductions likhit mein tay kar lijiye.",
    },
    "faq_documents": {
        "mr": "हे लेखी घ्या: प्रति क्विंटल भाव, प्रमाण, वजन, कपाती, पेमेंटची तारीख व पद्धत, आणि खरेदीदाराचे नाव व संपर्क.",
        "hi": "ये सब लिखित में लें: प्रति क्विंटल भाव, मात्रा, वजन, कटौती, भुगतान की तारीख और तरीका, और खरीदार का नाम व संपर्क।",
        "en": "Get these in writing: price per quintal, quantity, weight, deductions, payment date and mode, and the buyer's name and contact.",
        "hinglish": "Yeh sab likhit mein lijiye: prati quintal bhav, quantity, weight, deductions, payment ki date aur tareeka, aur buyer ka naam aur contact.",
    },
    "faq_cannot_do": {
        "mr": "सौदावाणी खरेदीदारांची पडताळणी, माल तोलणे, पैसे ठेवणे, किंवा पेमेंटची हमी/वसुली करत नाही. ते रोजचे मंडी अहवाल वाचते आणि ठरलेल्या अटींची नोंद करते.",
        "hi": "सौदावाणी खरीदारों का सत्यापन, माल तौलना, पैसे रखना, या भुगतान की गारंटी/वसूली नहीं करता। यह रोज की मंडी रिपोर्ट पढ़ता है और तय शर्तों का रिकॉर्ड रखता है।",
        "en": "SaudaVani does not verify buyers, weigh produce, hold money, or guarantee or recover payment. It reads daily mandi reports and records agreed terms.",
        "hinglish": "SaudaVani buyers ko verify nahi karta, maal tolta nahi, paisa rakhta nahi, aur payment ki guarantee ya recovery nahi karta. Yeh daily mandi reports padhta hai aur tay ki gayi shartein record karta hai.",
    },
}
for _key, _variants in _NEW_MSG.items():
    for _code, _msg in _variants.items():
        _MSG[_code][_key] = _msg
del _key, _variants, _code, _msg


_MSG["mr"]["notice_offer_expired"] = "या भावाची ऑफर कालबाह्य झाली आहे. नवीन ऑफर घेऊन पुन्हा पुष्टी करावी लागेल."
_MSG["hi"]["notice_offer_expired"] = "यह ऑफर समय समाप्त होने के कारण एक्सपायर हो गया है। नई ऑफर लेकर फिर से पुष्टि करें।"
_MSG["en"]["notice_offer_expired"] = "This offer has expired. A new offer and fresh confirmation are required."
_MSG["hinglish"]["notice_offer_expired"] = "Yeh offer expire ho gaya hai. Naya offer lekar dobara confirm karna hoga."
def ask_text(lang: str, kind: str, **kw: Any) -> str:
    table = _MSG["hinglish"] if lang == "hinglish" else _MSG[ui_lang(lang)]
    try:
        return table[kind].format(**kw)
    except (KeyError, IndexError, ValueError):
        log.exception("Message template error for %s", kind)
        return table["error"]