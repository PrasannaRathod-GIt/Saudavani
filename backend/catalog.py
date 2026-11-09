from typing import Any
COMMODITIES: dict[str, dict[str, Any]] = {
    "soybean": {
        "name": "Soybean", "mr": "सोयाबीन", "hi": "सोयाबीन",
        "aliases": ["soybean", "soyabean", "soya bean", "soya", "soyabin", "soyabeen", "सोयाबीन", "सोयाबिन", "सोया"],
        "market_terms": ["Soybean", "Soyabean", "Soybean seed"],
        "varieties": ["JS-335", "JS 93-05", "JS 80-21", "MAUS-71", "MAUS-158", "MAUS-162", "Local/Gavran", "Other/Not sure"],
        "variety_aliases": {"js335": "JS-335", "js-335": "JS-335", "js 335": "JS-335", "js 93-05": "JS 93-05", "maus 71": "MAUS-71", "maus-71": "MAUS-71", "maus 158": "MAUS-158", "maus 162": "MAUS-162", "gavran": "Local/Gavran", "local": "Local/Gavran"},
        "questions": [
            ("moisture", "moisture", "ओलावा किती आहे? मोजलेला टक्का माहीत नसेल तर माल सुका आहे की ओलसर ते सांगा.", "नमी कितनी है? प्रतिशत पता न हो तो माल सूखा है या नम, बताइए।", "Moisture किती आहे? टक्केवारी माहीत नसेल तर dry आहे की moist ते सांगा."),
            ("cleanliness", "cleanliness", "मालात माती, काडीकचरा किंवा इतर भेसळ आहे का?", "माल में मिट्टी, कचरा या दूसरी मिलावट है क्या?", "मालात dust, कचरा किंवा impurities आहेत का?"),
            ("seed_condition", "seed condition", "दाणे भरलेले आणि एकसारखे आहेत का, की तुटलेले/डागाळलेले दाणे आहेत?", "दाने भरे हुए और एक जैसे हैं या टूटे/दाग वाले भी हैं?", "दाणे uniform आहेत का, की broken किंवा damaged seeds आहेत?"),
        ],
    },
    "wheat": {
        "name": "Wheat", "mr": "गहू", "hi": "गेहूं",
        "aliases": ["wheat", "gehun", "gehu", "gahu", "gavhu", "gavhoo", "gavha", "gavhacha", "sharbati", "lokwan", "गेहूं", "गेंहू", "गहू", "गहु", "गव्ह", "शरबती", "लोकवन"],
        "market_terms": ["Wheat", "Wheat FAQ", "Sharbati Wheat"],
        "varieties": ["Lokwan", "Sharbati", "2189", "MP wheat", "Tukdi/Gujarat", "Local/Gavran", "Other/Not sure"],
        "variety_aliases": {"lokwan": "Lokwan", "lokvan": "Lokwan", "लोकवन": "Lokwan", "लोकवान": "Lokwan", "sharbati": "Sharbati", "2189": "2189", "mp wheat": "MP wheat", "tukdi": "Tukdi/Gujarat", "gujarat": "Tukdi/Gujarat", "gavran": "Local/Gavran"},
        "questions": [
            ("moisture", "moisture", "गव्हामध्ये ओलावा किती आहे? मोजलेला टक्का माहीत नसेल तर सुका की ओलसर ते सांगा.", "गेहूं में नमी कितनी है? प्रतिशत पता न हो तो सूखा या नम बताइए।", "गव्हात moisture किती आहे? मोजलेला टक्का नसेल तर dry की moist ते सांगा."),
            ("cleanliness", "cleanliness", "गहू स्वच्छ आहे का? माती, काडीकचरा किंवा इतर धान्य मिसळले आहे का?", "गेहूं साफ है? मिट्टी, कचरा या दूसरे अनाज मिले हैं क्या?", "गहू clean आहे का? Dust, straw किंवा दुसरे धान्य आहे का?"),
            ("grain_condition", "grain condition", "दाणे भरलेले व एकसारखे आहेत का? किडलेले किंवा तुटलेले दाणे आहेत का?", "दाने भरे और एक जैसे हैं? कीड़े लगे या टूटे दाने हैं क्या?", "दाणे full आणि uniform आहेत का? damaged किंवा insect-affected आहेत का?"),
        ],
    },
    "jowar": {
        "name": "Jowar", "mr": "ज्वारी", "hi": "ज्वार",
        "aliases": ["jowar", "jwari", "jowari", "jwar", "sorghum", "ज्वारी", "ज्वार", "ज्वारी धान्य"],
        "market_terms": ["Jowar", "Sorghum"],
        "varieties": ["Maldandi", "White Jowar", "Yellow Jowar", "Hybrid", "Local/Gavran", "Other/Not sure"],
        "variety_aliases": {"maldandi": "Maldandi", "maldandi jowar": "Maldandi", "white": "White Jowar", "yellow": "Yellow Jowar", "hybrid": "Hybrid", "gavran": "Local/Gavran"},
        "questions": [
            ("moisture", "moisture", "ज्वारीमध्ये ओलावा किती आहे? सुकी आहे की ओलसर?", "ज्वार में नमी कितनी है? सूखा है या नम?", "ज्वारीचा moisture किती आहे? Dry आहे की moist?"),
            ("cleanliness", "cleanliness", "दाण्यांत माती, काडीकचरा किंवा इतर भेसळ आहे का?", "दाने में मिट्टी, कचरा या मिलावट है क्या?", "दाण्यांत dirt किंवा foreign matter आहे का?"),
            ("grain_condition", "grain condition", "दाणे एकसारखे आहेत का? तुटलेले, अपरिपक्व किंवा किडलेले दाणे आहेत का?", "दाने एक जैसे हैं? टूटे, अधपके या कीड़े लगे दाने हैं?", "Grain size uniform आहे का? Broken किंवा insect-damaged दाणे आहेत का?"),
        ],
    },
    "moong": {
        "name": "Moong", "mr": "मूग", "hi": "मूंग",
        "aliases": ["moong", "mung", "green gram", "mung bean", "मूग", "मूंग", "मुग", "मुगा"],
        "market_terms": ["Moong", "Green Gram", "Green Gram Dal"],
        "varieties": ["Bold Green", "Small Green", "Local variety", "Other/Not sure"],
        "variety_aliases": {"bold": "Bold Green", "mota": "Bold Green", "large": "Bold Green", "small": "Small Green", "लहान": "Small Green", "gavran": "Local variety"},
        "questions": [
            ("moisture", "moisture", "मुगामध्ये ओलावा किती आहे? सुका आहे की ओलसर?", "मूंग में नमी कितनी है? सूखा है या नम?", "मुगाचा moisture किती आहे? Dry आहे की moist?"),
            ("cleanliness", "cleanliness", "मुगात माती, काडीकचरा किंवा इतर धान्य मिसळले आहे का?", "मूंग में मिट्टी, कचरा या दूसरा अनाज मिला है क्या?", "Impurities किंवा दुसरे दाणे मिसळले आहेत का?"),
            ("seed_condition", "seed condition", "दाणे हिरवे व एकसारखे आहेत का? तुटलेले, डागाळलेले किंवा किडलेले आहेत का?", "दाने हरे और एक जैसे हैं? टूटे, दागदार या कीड़े लगे हैं?", "दाणे हिरवे आणि uniform आहेत का? Broken किंवा insect-affected आहेत का?"),
        ],
    },
    "urad": {
        "name": "Urad", "mr": "उडीद", "hi": "उड़द",
        "aliases": ["urad", "udad", "udid", "black gram", "blackgram", "उडीद", "उड़द", "उडद", "उडदा"],
        "market_terms": ["Urad", "Black Gram", "Black Gram Dal"],
        "varieties": ["Bold whole Urad", "Small whole Urad", "Local variety", "Split Urad Dal", "Other/Not sure"],
        "variety_aliases": {"bold": "Bold whole Urad", "small": "Small whole Urad", "split": "Split Urad Dal", "dal": "Split Urad Dal", "whole": "Bold whole Urad", "अख्खा": "Bold whole Urad", "साबुत": "Bold whole Urad", "gavran": "Local variety"},
        "questions": [
            ("product_form", "product form", "हा अख्खा उडीद आहे की डाळ/फोडलेला उडीद?", "यह साबुत उड़द है या दाल/टूटा हुआ उड़द?", "हा whole urad आहे की split dal?"),
            ("moisture", "moisture", "उडीदामध्ये ओलावा किती आहे? सुका आहे की ओलसर?", "उड़द में नमी कितनी है? सूखा है या नम?", "उडदाचा moisture किती आहे? Dry की moist?"),
            ("cleanliness", "cleanliness", "माती, कचरा, तुटलेले किंवा किडलेले दाणे किती दिसतात?", "मिट्टी, कचरा, टूटे या कीड़े लगे दाने कितने हैं?", "Impurities, broken किंवा insect-damaged दाणे आहेत का?"),
        ],
    },
    "maize": {
        "name": "Maize", "mr": "मका", "hi": "मक्का",
        "aliases": ["maize", "corn", "makka", "makai", "maka", "मका", "मक्का", "मकई", "मक्या"],
        "market_terms": ["Maize", "Corn"],
        "varieties": ["Yellow maize", "White maize", "Hybrid", "Local variety", "Other/Not sure"],
        "variety_aliases": {"yellow": "Yellow maize", "white": "White maize", "hybrid": "Hybrid", "gavran": "Local variety"},
        "questions": [
            ("moisture", "moisture", "मक्यामध्ये ओलावा किती आहे? मोजलेला टक्का माहीत नसेल तर सुका की ओलसर ते सांगा.", "मक्का में नमी कितनी है? प्रतिशत पता न हो तो सूखा या नम बताइए।", "मक्याचा moisture किती आहे? Dry आहे की moist?"),
            ("cleanliness", "cleanliness", "दाण्यांत धूळ, काडीकचरा किंवा इतर भेसळ आहे का?", "दाने में धूल, कचरा या मिलावट है क्या?", "Dust, trash किंवा foreign matter आहे का?"),
            ("grain_condition", "grain condition", "दाणे तुटलेले, काळे किंवा बुरशी लागलेले आहेत का?", "दाने टूटे, काले या फफूंदी वाले हैं क्या?", "Broken, discoloured किंवा mouldy grains आहेत का?"),
        ],
    },
    "onion": {
        "name": "Onion", "mr": "कांदा", "hi": "प्याज",
        "aliases": ["onion", "kanda", "kande", "kandyacha", "pyaz", "pyaaz", "कांदा", "कांदे", "कांद्या", "प्याज"],
        "market_terms": ["Onion"],
        "varieties": ["Red onion", "White onion", "Pink/local onion", "Kharif", "Late Kharif", "Rabi/Summer", "Other/Not sure"],
        "variety_aliases": {"red": "Red onion", "lal": "Red onion", "white": "White onion", "pink": "Pink/local onion", "kharif": "Kharif", "late kharif": "Late Kharif", "rabi": "Rabi/Summer", "summer": "Rabi/Summer"},
        "questions": [
            ("size", "size", "कांदा लहान, मध्यम की मोठ्या आकाराचा आहे? आकार साधारण एकसारखा आहे का?", "प्याज छोटा, मध्यम या बड़ा है? आकार लगभग एक जैसा है?", "कांदा small, medium की large आहे? Size uniform आहे का?"),
            ("firmness", "firmness", "कांदा घट्ट आणि कोरडा आहे का? मऊ किंवा ओलसर कांदे आहेत का?", "प्याज सख्त और सूखा है? नरम या नम प्याज हैं?", "कांदा firm आणि dry आहे का? Soft bulbs आहेत का?"),
            ("damage", "damage", "कुजलेले, फुटलेले, मोड आलेले किंवा डाग असलेले कांदे आहेत का?", "सड़े, फूटे, अंकुर निकले या दाग वाले प्याज हैं क्या?", "Rot, sprouting, bruising किंवा damaged bulbs आहेत का?"),
        ],
    },
    "bajra": {
        "name": "Bajra", "mr": "बाजरी", "hi": "बाजरा",
        "aliases": ["bajra", "bajri", "pearl millet", "बाजरी", "बाजरा"],
        "market_terms": ["Bajra", "Pearl Millet"],
        "varieties": ["Local/Gavran", "Hybrid", "White/Light", "Grey/Dark", "Other/Not sure"],
        "variety_aliases": {"gavran": "Local/Gavran", "local": "Local/Gavran", "hybrid": "Hybrid", "white": "White/Light", "grey": "Grey/Dark", "dark": "Grey/Dark"},
        "questions": [
            ("moisture", "moisture", "बाजरीमध्ये ओलावा किती आहे? सुकी आहे की ओलसर?", "बाजरे में नमी कितनी है? सूखा है या नम?", "बाजरीचा moisture किती आहे? Dry की moist?"),
            ("cleanliness", "cleanliness", "बाजरीत माती, कचरा किंवा इतर धान्य मिसळले आहे का?", "बाजरे में मिट्टी, कचरा या दूसरा अनाज मिला है?", "Foreign matter किंवा दुसरे दाणे मिसळले आहेत का?"),
            ("grain_condition", "grain condition", "दाणे एकसारखे आहेत का? किडलेले किंवा अपरिपक्व दाणे आहेत का?", "दाने एक जैसे हैं? कीड़े लगे या अधपके दाने हैं?", "Grains uniform आहेत का? Insect-damaged किंवा immature दाणे आहेत का?"),
        ],
    },
    "chana": {
        "name": "Chana / Gram", "mr": "हरभरा", "hi": "चना",
        "aliases": ["chana", "gram", "bengal gram", "chickpea", "harbhara", "harbara", "harbharaa", "चना", "हरभरा", "हरभऱ्या", "हरभरा दाणा", "चणा"],
        "market_terms": ["Gram", "Chana", "Bengal Gram", "Kabuli Chana"],
        "varieties": ["Desi/Brown", "Kala Chana", "Kabuli/White", "Bold", "Medium", "Small", "Other/Not sure"],
        "variety_aliases": {"desi": "Desi/Brown", "brown": "Desi/Brown", "kala": "Kala Chana", "kabuli": "Kabuli/White", "white": "Kabuli/White", "bold": "Bold", "medium": "Medium", "small": "Small"},
        "questions": [
            ("moisture", "moisture", "हरभऱ्यात ओलावा किती आहे? सुका आहे की ओलसर?", "चना में नमी कितनी है? सूखा है या नम?", "हरभऱ्याचा moisture किती आहे? Dry की moist?"),
            ("cleanliness", "cleanliness", "हरभऱ्यात माती, दगड किंवा इतर भेसळ आहे का?", "चना में मिट्टी, पत्थर या मिलावट है क्या?", "माती, दगड किंवा foreign matter आहे का?"),
            ("seed_condition", "seed condition", "दाणे तुटलेले, डागाळलेले किंवा अळी/किडीने खराब झालेले आहेत का?", "दाने टूटे, दागदार या कीड़े से खराब हैं क्या?", "Broken, discoloured किंवा weevil-damaged दाणे आहेत का?"),
        ],
    },
    "tur": {
        "name": "Tur / Arhar", "mr": "तूर", "hi": "अरहर",
        "aliases": ["tur", "toor", "tuvar", "tuwar", "arhar", "red gram", "pigeon pea", "तूर", "तुवर", "अरहर", "तूरदाणा", "तूर दाणा", "तुरी"],
        "market_terms": ["Arhar (Tur/Red Gram)", "Tur", "Arhar", "Pigeon Pea"],
        "varieties": ["Whole Tur", "Bold", "Small", "Local variety", "Tur Dal (processed)", "Other/Not sure"],
        "variety_aliases": {"whole": "Whole Tur", "अख्खा": "Whole Tur", "साबुत": "Whole Tur", "bold": "Bold", "small": "Small", "gavran": "Local variety", "dal": "Tur Dal (processed)", "डाळ": "Tur Dal (processed)", "दाल": "Tur Dal (processed)", "split": "Tur Dal (processed)"},
        "questions": [
            ("product_form", "product form", "हा अख्खा तूरदाणा आहे की प्रक्रिया केलेली तूरडाळ?", "यह साबुत अरहर है या प्रोसेस की हुई तूर दाल?", "हा whole tur आहे की processed tur dal?"),
            ("moisture", "moisture", "तूरदाण्यात ओलावा किती आहे? सुका आहे की ओलसर?", "अरहर में नमी कितनी है? सूखा है या नम?", "तूरदाण्याचा moisture किती आहे? Dry की moist?"),
            ("cleanliness", "cleanliness", "दाण्यांत माती, इतर धान्य, तुटलेले किंवा किडलेले दाणे आहेत का?", "दाने में मिट्टी, दूसरा अनाज, टूटे या कीड़े लगे दाने हैं?", "Foreign matter, admixture किंवा damaged grains आहेत का?"),
        ],
    },
    "cotton": {
        "name": "Cotton", "mr": "कापूस", "hi": "कपास",
        "aliases": ["cotton", "kapas", "kapus", "kapash", "kapsacha", "कापूस", "कपास", "कापशी", "कापाशी", "कापसा"],
        "market_terms": ["Cotton", "Kapas", "Raw Cotton"],
        "varieties": ["Raw Kapas", "Ginned Cotton/Lint", "Desi", "American/Bt", "Other/Not sure"],
        "variety_aliases": {"कच्चा कपास": "Raw Kapas", "kapas": "Raw Kapas", "raw": "Raw Kapas", "कच्चा कापूस": "Raw Kapas", "गाठीचा कापूस": "Ginned Cotton/Lint", "lint": "Ginned Cotton/Lint", "ginned": "Ginned Cotton/Lint", "jinning": "Ginned Cotton/Lint", "desi": "Desi", "bt": "American/Bt", "american": "American/Bt"},
        "questions": [
            ("product_form", "product form", "हा कच्चा शेतातील कापूस/कपास आहे की जिनिंग केलेला कापूस?", "यह खेत का कच्चा कपास है या जिनिंग किया हुआ कॉटन?", "हा raw kapas आहे की ginned cotton lint?"),
            ("moisture", "moisture", "कापसात ओलावा आहे का? माल कोरडा आहे की दमट?", "कपास में नमी है? माल सूखा है या नम?", "कापसात moisture आहे का? Dry आहे की damp?"),
            ("trash", "trash", "कापसात पानं, काडीकचरा, धूळ किंवा डाग किती आहेत?", "कपास में पत्ते, कचरा, धूल या दाग कितने हैं?", "Trash, leaf matter, dust किंवा stains किती आहेत?"),
        ],
    },
    "paddy_rice": {
        "name": "Paddy / Rice", "mr": "भात / तांदूळ", "hi": "धान / चावल",
        "aliases": ["paddy", "rice", "chawal", "chaawal", "tandul", "tandool", "tandula", "dhan", "dhaan", "bhat", "sal", "चावल", "तांदूळ", "तांदुळ", "तांदळा", "धान", "भात", "साळ", "साल", "indrayani", "kolam", "basmati", "ambemohar", "hmt", "sona masuri"],
        "market_terms": ["Paddy", "Rice", "Paddy (Dhan)", "Common Paddy"],
        "varieties": ["Indrayani", "Kolam", "Basmati", "Ambemohar", "HMT", "Sona Masuri", "Regular/Non-basmati", "Other/Local", "Not sure"],
        "variety_aliases": {"indrayani": "Indrayani", "indra": "Indrayani", "इंद्रायणी": "Indrayani", "kolam": "Kolam", "कोलम": "Kolam", "basmati": "Basmati", "बासमती": "Basmati", "ambemohar": "Ambemohar", "आंबेमोहोर": "Ambemohar", "amba mohar": "Ambemohar", "hmt": "HMT", "sona masuri": "Sona Masuri", "sonamasuri": "Sona Masuri", "regular": "Regular/Non-basmati", "non basmati": "Regular/Non-basmati", "local": "Other/Local"},
        "questions": [
            ("moisture", "moisture", "धान/तांदळामध्ये ओलावा किती आहे? मोजलेला टक्का माहीत नसेल तर सुका की ओलसर ते सांगा.", "धान/चावल में नमी कितनी है? प्रतिशत पता न हो तो सूखा या नम बताइए।", "Paddy/rice मध्ये moisture किती आहे? Dry की moist?"),
            ("cleanliness", "cleanliness", "मालात माती, काडीकचरा किंवा दुसऱ्या जातीचे दाणे मिसळले आहेत का?", "माल में मिट्टी, कचरा या दूसरी किस्म के दाने मिले हैं?", "Impurities किंवा mixed variety grains आहेत का?"),
            ("grain_condition", "grain condition", "दाणे तुटलेले, अपरिपक्व, डागाळलेले किंवा किडलेले आहेत का?", "दाने टूटे, अधपके, दागदार या कीड़े लगे हैं?", "Broken, immature, discoloured किंवा insect-affected grains आहेत का?"),
        ],
    },
}

MARKET_COMMODITY_TERMS: dict[str, list[str]] = {
    "soybean": ["Soyabean", "Soybean"],
    "wheat": ["Wheat"],
    "jowar": ["Jowar(Sorghum)", "Jowar", "Sorghum"],
    "moong": ["Green Gram (Moong)(Whole)", "Moong", "Green Gram"],
    "urad": ["Black Gram (Urd Beans)(Whole)", "Urad", "Black Gram"],
    "maize": ["Maize", "Corn"],
    "onion": ["Onion"],
    "bajra": ["Bajra(Pearl Millet/Cumbu)", "Bajra", "Pearl Millet"],
    "chana": ["Bengal Gram(Gram)(Whole)", "Gram", "Chana", "Bengal Gram"],
    "tur": ["Arhar (Tur/Red Gram)(Whole)", "Arhar (Tur/Red Gram)", "Arhar", "Tur", "Pigeon Pea"],
    "cotton": ["Cotton", "Raw Cotton"],
    "paddy_rice": ["Paddy(Dhan)(Common)", "Paddy", "Paddy (Dhan)", "Rice"],
}
DISTRICTS: list[tuple[str, list[str], list[str]]] = [
    ("Ahilyanagar", ["Ahilyanagar", "Ahmednagar"], ["ahilyanagar", "ahmednagar", "ahmadnagar", "अहिल्यानगर", "अहमदनगर", "अहिल्या नगर"]),
    ("Akola", ["Akola"], ["akola", "अकोला"]),
    ("Amravati", ["Amravati"], ["amravati", "amaravati", "अमरावती"]),
    ("Chhatrapati Sambhajinagar", ["Chhatrapati Sambhajinagar", "Aurangabad"], ["chhatrapati sambhajinagar", "sambhajinagar", "aurangabad", "छत्रपती संभाजीनगर", "संभाजीनगर", "औरंगाबाद"]),
    ("Beed", ["Beed"], ["beed", "bid", "बीड"]),
    ("Bhandara", ["Bhandara"], ["bhandara", "भंडारा"]),
    ("Buldhana", ["Buldhana"], ["buldhana", "buldana", "बुलढाणा", "बुलडाणा"]),
    ("Chandrapur", ["Chandrapur"], ["chandrapur", "चंद्रपूर", "चंद्रपुर"]),
    ("Dhule", ["Dhule"], ["dhule", "dhulia", "धुळे"]),
    ("Gadchiroli", ["Gadchiroli"], ["gadchiroli", "गडचिरोली"]),
    ("Gondia", ["Gondia"], ["gondia", "गोंदिया"]),
    ("Hingoli", ["Hingoli"], ["hingoli", "हिंगोली"]),
    ("Jalgaon", ["Jalgaon"], ["jalgaon", "जळगाव", "जलगांव"]),
    ("Jalna", ["Jalna"], ["jalna", "जालना"]),
    ("Kolhapur", ["Kolhapur"], ["kolhapur", "कोल्हापूर", "कोल्हापुर"]),
    ("Latur", ["Latur"], ["latur", "लातूर", "लातुर"]),
    ("Mumbai", ["Mumbai"], ["mumbai", "bombay", "मुंबई"]),
    ("Nagpur", ["Nagpur"], ["nagpur", "नागपूर", "नागपुर"]),
    ("Nanded", ["Nanded"], ["nanded", "नांदेड"]),
    ("Nandurbar", ["Nandurbar"], ["nandurbar", "नंदुरबार"]),
    ("Nashik", ["Nashik"], ["nashik", "nasik", "नाशिक", "नासिक"]),
    ("Dharashiv", ["Dharashiv", "Osmanabad"], ["dharashiv", "osmanabad", "धाराशिव", "उस्मानाबाद"]),
    ("Palghar", ["Palghar"], ["palghar", "पालघर"]),
    ("Parbhani", ["Parbhani"], ["parbhani", "परभणी"]),
    ("Pune", ["Pune"], ["pune", "poona", "पुणे", "पुण्य"]),
    ("Raigad", ["Raigad"], ["raigad", "रायगड"]),
    ("Ratnagiri", ["Ratnagiri"], ["ratnagiri", "रत्नागिरी"]),
    ("Sangli", ["Sangli"], ["sangli", "सांगली"]),
    ("Satara", ["Satara"], ["satara", "सातारा", "सातार"]),
    ("Sindhudurg", ["Sindhudurg"], ["sindhudurg", "सिंधुदुर्ग"]),
    ("Solapur", ["Solapur"], ["solapur", "sholapur", "सोलापूर", "सोलापुर"]),
    ("Thane", ["Thane"], ["thane", "ठाणे", "ठाण्य"]),
    ("Wardha", ["Wardha"], ["wardha", "वर्धा"]),
    ("Washim", ["Washim"], ["washim", "वाशिम"]),
    ("Yavatmal", ["Yavatmal"], ["yavatmal", "यवतमाळ"]),
]


# Maharashtra APMC hints. A user-supplied market/APMC field is preferred.
MARKET_ALIASES = {
    "पुणे": "Pune", "बारामती": "Baramati", "नाशिक": "Nashik", "लासलगाव": "Lasalgaon",
    "सोलापूर": "Solapur", "सांगली": "Sangli", "कोल्हापूर": "Kolhapur", "नागपूर": "Nagpur",
    "अकोला": "Akola", "अमरावती": "Amravati", "लातूर": "Latur", "जळगाव": "Jalgaon",
    "अहमदनगर": "Ahmednagar", "अहिल्यानगर": "Ahilyanagar", "सातारा": "Satara", "बीड": "Beed",
    "धाराशिव": "Dharashiv", "येवला": "Yeola", "मनमाड": "Manmad", "राहुरी": "Rahuri",
    "इंदापूर": "Indapur", "दौंड": "Daund", "खेड": "Khed", "सिन्नर": "Sinner", "सटाणा": "Satana",
    "नांदगाव": "Nandgaon", "पिंपळगाव": "Pimpalgaon", "कळवण": "Kalwan", "चांदवड": "Chandwad",
}

KNOWN_MARKETS = [
    "Pune", "Baramati", "Nashik", "Lasalgaon", "Solapur", "Sangli", "Kolhapur",
    "Nagpur", "Akola", "Amravati", "Latur", "Jalgaon", "Ahmednagar", "Ahilyanagar",
    "Chhatrapati Sambhajinagar", "Aurangabad", "Satara", "Beed", "Dharashiv", "Osmanabad",
    "Yeola", "Manmad", "Rahuri", "Karmala", "Indapur", "Daund", "Khed", "Shrirampur",
    "Sinner", "Satana", "Nandgaon", "Pimpalgaon", "Kalwan", "Chandwad",
]

MARKET_WORDS = ("apmc", "mandi", "market", "मंडी", "मंडई", "बाजार", "बाज़ार")
_MARKET_SKIP_TOKENS = {"any", "anywhere", "skip", "none", "kontihi", "kuthlihi", "कोणतीही", "कोणतेही", "कुठलीही", "कोणतीच", "कोई", "नाही", "नहीं", "नको", "नही"}
_OTHER_VARIETY_TOKENS = {"other", "others", "इतर", "दुसरा", "दूसरा", "अन्य"}
# "Any market" in English / Hindi / Marathi / Hinglish. These must never be searched as a literal APMC name.
# Step 2E additions: कोणती, कोणता, पण, चालते, चालेल, कुठली, कुठलीही, kontihi (already present) plus the Hindi "कोई भी" family,
# the Hinglish/English helper words used in "chalel / chalega / is fine" phrasings.
_ANY_MARKET_TOKENS = {"any", "anywhere", "all", "skip", "none", "koi", "koyi", "kuch", "kuchh", "bhi", "sab", "sabhi", "sarv", "sarva", "saglya",
                      "kuthlyahi", "kuthalyahi", "konatyahi", "konti", "kunti", "kuthli", "kuthlya", "kontya",
                      "kontihi", "kontihee", "kuthlihi", "kontyahi", "कोणतीही", "कोणतेही", "कोणत्याही", "कुठलीही", "कुठल्याही", "कोणतीच",
                      "कोई", "कुछ", "भी", "सब", "सभी", "सर्व", "सगळ्या", "सगळ्याच", "ही",
                      "कोणती", "कोणता", "पण", "चालते", "चालेल", "कुठली",
                      "pan", "chalel", "chalte", "chalta", "chalega", "chalegi", "चलेगा", "चलेगी", "चलता", "चलते",
                      "fine", "ok", "okay", "works", "anything"}
_MARKET_FILLER_TOKENS = {"market", "markets", "mandi", "mandis", "apmc", "मंडी", "मंडई", "बाजार", "बाज़ार", "मंडीत", "में", "मे", "madhe", "मध्ये",
                         "बाजारात", "बाज़ारात", "मंडीमध्ये", "मंडीमधे", "bazar", "bazaar", "bazarat", "mandit", "mandimadhe", "bajar", "bajarat", "mandi", "mandiyon",
                         "की", "ki", "ka", "का", "किसी", "kisi",
                         "is", "are", "hai", "hain", "है", "हैं", "aahe", "ahe", "आहे"}