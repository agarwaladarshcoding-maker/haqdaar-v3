"""haqdaar/contracts/vocab.py

UNOWNED. Closed vocabulary lists, keypad order, trilingual labels, and forbidden phrases
(D6, 05-DATA-CONTRACT.md §1C, §3 Gate 4). One file, so the pipeline (which validates a
facet value against a list) and the engine (which reads a keypad menu aloud) can never
drift apart.

Plain module, no imports from pipeline/engine. The order of each list IS the keypad
order (key 1 = first item).
"""
from __future__ import annotations

import re
import unicodedata

from haqdaar.contracts.types import ANY, FACT_NAMES  # re-use the existing ANY constant

CATEGORY = ("farming", "business_loans", "jobs_skills", "health", "housing",
            "pension", "education", "women_children", "welfare_disability")
OLD_CATEGORY_MAP = {  # old 11 values -> new 9 groups (reference + fixture migration)
    "agriculture": "farming", "business": "business_loans", "handloom": "business_loans",
    "employment": "jobs_skills", "skills": "jobs_skills", "livelihood": "jobs_skills",
    "health": "health", "housing": "housing", "pension": "pension",
    "education": "education", "social_welfare": "welfare_disability",
}
CATEGORY_GLOSS = {  # for the facets prompt only (English, what each group covers)
    "farming": "farmers, crops, land, farm machines, crop insurance, farm credit",
    "business_loans": "loans or support to start or grow a small business, handloom, crafts",
    "jobs_skills": "jobs, wage work, livelihood groups, skill training, apprenticeships",
    "health": "hospital treatment, health insurance, medicines",
    "housing": "building or repairing a house, house sites",
    "pension": "pensions, old age, savings for old age",
    "education": "school, college, scholarships",
    "women_children": "schemes mainly for women, girls, mothers, or children",
    "welfare_disability": "disability support, destitute people, other social welfare",
}
STATE = ("MAHARASHTRA", "OTHER")     # asked as a yes/no question (D7); OTHER mask = central schemes
GENDER = ("female", "male", "other")
SOCIAL_CATEGORY = ("GEN", "OBC", "SC", "ST")
OCCUPATION = ("farmer", "street_vendor", "apprentice", "entrepreneur", "artisan", "weaver", "worker")

KEYPAD_LISTS = {"category": CATEGORY, "state": STATE, "gender": GENDER,
                "social_category": SOCIAL_CATEGORY, "occupation": OCCUPATION}
# age and income_band are ranges {"min","max"}; their keypad bands are built per snapshot (step 1.5)

# --- N6: the boxes only the talk asks (types.TALK_BOXES). Not in KEYPAD_LISTS: no keypad menu, no chip clip. ---
# What a scheme gives. Codes with an underscore, or not an everyday word of their own, so a code said aloud is caught.
GIVES = ("cash_aid", "loan", "subsidy", "insurance", "monthly_pension", "training", "job", "house",
         "health_cover", "scholarship", "equipment", "food", "other")
# sub_kind has NO closed list: a short code per kind inside a kind (farming: crops, animals, fish, machines, water,
# land). The values are whatever the rows hold; the snapshot writer collects them.
# Every state and union territory. `state` stays the keypad's two values (the keys menu and its clips read it), so the
# talk's whole list is its own box, `home_state`. OTHER is kept for old rows.
HOME_STATE = (
    "ANDAMAN_AND_NICOBAR_ISLANDS", "ANDHRA_PRADESH", "ARUNACHAL_PRADESH", "ASSAM", "BIHAR", "CHANDIGARH",
    "CHHATTISGARH", "DADRA_AND_NAGAR_HAVELI_AND_DAMAN_AND_DIU", "DELHI", "GOA", "GUJARAT", "HARYANA",
    "HIMACHAL_PRADESH", "JAMMU_AND_KASHMIR", "JHARKHAND", "KARNATAKA", "KERALA", "LADAKH", "LAKSHADWEEP",
    "MADHYA_PRADESH", "MAHARASHTRA", "MANIPUR", "MEGHALAYA", "MIZORAM", "NAGALAND", "ODISHA", "PUDUCHERRY",
    "PUNJAB", "RAJASTHAN", "SIKKIM", "TAMIL_NADU", "TELANGANA", "TRIPURA", "UTTAR_PRADESH", "UTTARAKHAND",
    "WEST_BENGAL", "OTHER")
YES_NO = ("yes", "no")

# The yes / no facts: `f_<fact>` boxes. yes / no = the plain words for each answer (what the talk says back);
# ask = the question in en / hi / mr (the Hindi and Marathi are drafts, not checked by a speaker);
# change = can a person change it (a card can be got; being a widow can not).
FACTS = {
  "bpl_card": {"yes": "has a BPL card", "no": "has no BPL card", "change": True,
      "ask": {"en": "Do you have a BPL card?", "hi": "क्या आपके पास बीपीएल कार्ड है?", "mr": "तुमच्याकडे बीपीएल कार्ड आहे का?"}},
  "ration_card": {"yes": "has a ration card", "no": "has no ration card", "change": True,
      "ask": {"en": "Do you have a ration card?", "hi": "क्या आपके पास राशन कार्ड है?", "mr": "तुमच्याकडे रेशन कार्ड आहे का?"}},
  "widow": {"yes": "is a widow", "no": "is not a widow", "change": False,
      "ask": {"en": "Are you a widow?", "hi": "क्या आप विधवा हैं?", "mr": "तुम्ही विधवा आहात का?"}},
  "disability": {"yes": "has a disability", "no": "has no disability", "change": False,
      "ask": {"en": "Do you have a disability?", "hi": "क्या आपको कोई दिव्यांगता है?", "mr": "तुम्हाला दिव्यांगत्व आहे का?"}},
  "owns_farm_land": {"yes": "owns farm land", "no": "owns no farm land", "change": True,
      "ask": {"en": "Do you own farm land?", "hi": "क्या आपके पास खेती की ज़मीन है?", "mr": "तुमच्या नावावर शेतजमीन आहे का?"}},
  "rural": {"yes": "lives in a village", "no": "lives in a town or city", "change": True,
      "ask": {"en": "Do you live in a village?", "hi": "क्या आप गाँव में रहते हैं?", "mr": "तुम्ही गावात राहता का?"}},
  "pregnant": {"yes": "is pregnant", "no": "is not pregnant", "change": True,
      "ask": {"en": "Is the woman pregnant?", "hi": "क्या महिला गर्भवती है?", "mr": "महिला गर्भवती आहे का?"}},
  "student": {"yes": "is a student", "no": "is not a student", "change": True,
      "ask": {"en": "Are you studying now?", "hi": "क्या आप अभी पढ़ाई कर रहे हैं?", "mr": "तुम्ही सध्या शिकत आहात का?"}},
  "girl_child": {"yes": "has a daughter", "no": "has no daughter", "change": False,
      "ask": {"en": "Do you have a daughter?", "hi": "क्या आपकी बेटी है?", "mr": "तुम्हाला मुलगी आहे का?"}},
  "senior_alone": {"yes": "is an old person living alone", "no": "is not an old person living alone", "change": True,
      "ask": {"en": "Do you live alone, with no one to look after you?",
              "hi": "क्या आप अकेले रहते हैं, देखभाल करने वाला कोई नहीं है?",
              "mr": "तुम्ही एकटे राहता का, सांभाळणारे कोणी नाही?"}},
  "minority": {"yes": "is from a minority community", "no": "is not from a minority community", "change": False,
      "ask": {"en": "Are you from a minority community?", "hi": "क्या आप अल्पसंख्यक समुदाय से हैं?",
              "mr": "तुम्ही अल्पसंख्याक समाजातील आहात का?"}},
  "income_tax_payer": {"yes": "pays income tax", "no": "pays no income tax", "change": True,
      "ask": {"en": "Do you pay income tax?", "hi": "क्या आप आयकर देते हैं?", "mr": "तुम्ही आयकर भरता का?"}},
  "govt_employee": {"yes": "is a government employee", "no": "is not a government employee", "change": True,
      "ask": {"en": "Do you work for the government?", "hi": "क्या आप सरकारी नौकरी में हैं?", "mr": "तुम्ही सरकारी नोकरीत आहात का?"}},
  "bank_account": {"yes": "has a bank account", "no": "has no bank account", "change": True,
      "ask": {"en": "Do you have a bank account?", "hi": "क्या आपका बैंक खाता है?", "mr": "तुमचे बँक खाते आहे का?"}},
  "aadhaar": {"yes": "has an Aadhaar card", "no": "has no Aadhaar card", "change": True,
      "ask": {"en": "Do you have an Aadhaar card?", "hi": "क्या आपके पास आधार कार्ड है?", "mr": "तुमच्याकडे आधार कार्ड आहे का?"}},
  "shop_or_trade": {"yes": "runs a shop or trade", "no": "runs no shop or trade", "change": True,
      "ask": {"en": "Do you run a shop or a small trade?", "hi": "क्या आप दुकान या छोटा धंधा चलाते हैं?",
              "mr": "तुम्ही दुकान किंवा छोटा व्यवसाय चालवता का?"}},
  "new_business": {"yes": "wants to start a new business", "no": "does not want to start a new business", "change": True,
      "ask": {"en": "Do you want to start a new business?", "hi": "क्या आप नया काम-धंधा शुरू करना चाहते हैं?",
              "mr": "तुम्हाला नवीन व्यवसाय सुरू करायचा आहे का?"}},
  "kutcha_house": {"yes": "lives in a kutcha house or has no house", "no": "does not live in a kutcha house", "change": True,
      "ask": {"en": "Do you live in a kutcha house, or have no house?",
              "hi": "क्या आप कच्चे घर में रहते हैं, या आपका घर नहीं है?",
              "mr": "तुम्ही कच्च्या घरात राहता का, किंवा तुमचे घर नाही?"}},
  "breadwinner_died": {"yes": "lost the earning member of the family", "no": "has not lost the earning member of the family",
      "change": False,
      "ask": {"en": "Has the earning member of your family died?", "hi": "क्या परिवार में कमाने वाले की मृत्यु हो गई है?",
              "mr": "कुटुंबातील कमावत्या व्यक्तीचा मृत्यू झाला आहे का?"}},
  "migrant_worker": {"yes": "is a migrant worker", "no": "is not a migrant worker", "change": True,
      "ask": {"en": "Do you work away from home, in another place?", "hi": "क्या आप घर से दूर, दूसरी जगह काम करते हैं?",
              "mr": "तुम्ही घरापासून दूर, दुसऱ्या ठिकाणी काम करता का?"}},
}
assert tuple(FACTS) == FACT_NAMES


def fact_of(box: str) -> dict | None:
    """The FACTS row of a `f_<fact>` box, else None."""
    return FACTS.get(box[2:]) if box.startswith("f_") else None


def box_values(box: str) -> tuple[str, ...] | None:
    """The closed list of a talk-only box (None: no closed list, or not a talk-only box)."""
    if box == "gives":
        return GIVES
    if box == "home_state":
        return HOME_STATE
    return YES_NO if fact_of(box) else None


def value_words(box: str, value: str) -> str:
    """Plain English words for one value of a talk-only box: "has a BPL card", never a bare "yes"."""
    fact = fact_of(box)
    if fact:
        return fact.get(str(value), str(value))
    label = (LABELS.get(value) or {}).get("en")
    return str(label) if label else str(value).replace("_", " ").lower()

LABELS = {  # value -> {lang: spoken label}
  "farming":            {"en": "Farming",                    "hi": "खेती-किसानी",             "mr": "शेती"},
  "business_loans":     {"en": "Business and loans",         "hi": "व्यापार और लोन",           "mr": "व्यवसाय आणि कर्ज"},
  "jobs_skills":        {"en": "Jobs and skills",            "hi": "रोज़गार और हुनर",           "mr": "नोकरी आणि कौशल्य"},
  "health":             {"en": "Health and treatment",       "hi": "सेहत और इलाज",             "mr": "आरोग्य आणि उपचार"},
  "housing":            {"en": "A house",                    "hi": "घर",                       "mr": "घर"},
  "pension":            {"en": "Pension and old age",        "hi": "पेंशन और बुढ़ापा",          "mr": "पेन्शन आणि वृद्धापकाळ"},
  "education":          {"en": "Education",                  "hi": "पढ़ाई",                     "mr": "शिक्षण"},
  "women_children":     {"en": "Women and children",         "hi": "महिलाएँ और बच्चे",          "mr": "महिला आणि मुले"},
  "welfare_disability": {"en": "Disability and social help", "hi": "दिव्यांग और सामाजिक मदद",   "mr": "दिव्यांग आणि सामाजिक मदत"},
  "MAHARASHTRA":        {"en": "Maharashtra",                "hi": "महाराष्ट्र",                "mr": "महाराष्ट्र"},
  "OTHER":              {"en": "Another state",              "hi": "दूसरा राज्य",               "mr": "दुसरे राज्य"},
  "female":             {"en": "Woman",                      "hi": "महिला",                    "mr": "महिला"},
  "male":               {"en": "Man",                        "hi": "पुरुष",                    "mr": "पुरुष"},
  "other":              {"en": "Other",                      "hi": "अन्य",                     "mr": "इतर"},
  "GEN":                {"en": "General",                    "hi": "सामान्य",                  "mr": "सर्वसाधारण"},
  "OBC":                {"en": "OBC",                        "hi": "ओबीसी",                    "mr": "ओबीसी"},
  "SC":                 {"en": "SC",                         "hi": "एससी",                     "mr": "एससी"},
  "ST":                 {"en": "ST",                         "hi": "एसटी",                     "mr": "एसटी"},
  "farmer":             {"en": "Farmer",                     "hi": "किसान",                    "mr": "शेतकरी"},
  "street_vendor":      {"en": "Street vendor",              "hi": "रेहड़ी-पटरी विक्रेता",       "mr": "फेरीवाले"},
  "apprentice":         {"en": "Apprentice",                 "hi": "प्रशिक्षु",                  "mr": "शिकाऊ उमेदवार"},
  "entrepreneur":       {"en": "Own business",               "hi": "अपना काम-धंधा",             "mr": "स्वतःचा व्यवसाय"},
  "artisan":            {"en": "Artisan",                    "hi": "कारीगर",                   "mr": "कारागीर"},
  "weaver":             {"en": "Weaver",                     "hi": "बुनकर",                    "mr": "विणकर"},
  "worker":             {"en": "Worker",                     "hi": "श्रमिक",                    "mr": "कामगार"},
}

# N6: labels for the talk-only values (the keys hint says them). Hindi and Marathi are drafts, not checked by a speaker.
LABELS.update({
  "cash_aid":        {"en": "Cash help",        "hi": "नकद मदद",          "mr": "रोख मदत"},
  "loan":            {"en": "A loan",           "hi": "लोन",              "mr": "कर्ज"},
  "subsidy":         {"en": "A subsidy",        "hi": "सब्सिडी",          "mr": "अनुदान"},
  "insurance":       {"en": "Insurance",        "hi": "बीमा",             "mr": "विमा"},
  "monthly_pension": {"en": "A monthly pension", "hi": "मासिक पेंशन",     "mr": "मासिक पेन्शन"},
  "training":        {"en": "Training",         "hi": "प्रशिक्षण",         "mr": "प्रशिक्षण"},
  "job":             {"en": "A job",            "hi": "नौकरी",            "mr": "नोकरी"},
  "house":           {"en": "A house",          "hi": "घर",               "mr": "घर"},
  "health_cover":    {"en": "Health cover",     "hi": "इलाज का खर्च",      "mr": "उपचाराचा खर्च"},
  "scholarship":     {"en": "A scholarship",    "hi": "छात्रवृत्ति",       "mr": "शिष्यवृत्ती"},
  "equipment":       {"en": "Tools or equipment", "hi": "औज़ार या उपकरण",   "mr": "अवजारे किंवा उपकरणे"},
  "food":            {"en": "Food",             "hi": "अनाज",             "mr": "धान्य"},
})
# State names (en, hi, mr) for the key hint and the say-back. Drafts for hi / mr.
for _code, _en, _hi, _mr in (
    ("ANDAMAN_AND_NICOBAR_ISLANDS", "Andaman and Nicobar Islands", "अंडमान और निकोबार", "अंदमान आणि निकोबार"),
    ("ANDHRA_PRADESH", "Andhra Pradesh", "आंध्र प्रदेश", "आंध्र प्रदेश"),
    ("ARUNACHAL_PRADESH", "Arunachal Pradesh", "अरुणाचल प्रदेश", "अरुणाचल प्रदेश"),
    ("ASSAM", "Assam", "असम", "आसाम"), ("BIHAR", "Bihar", "बिहार", "बिहार"),
    ("CHANDIGARH", "Chandigarh", "चंडीगढ़", "चंदीगड"), ("CHHATTISGARH", "Chhattisgarh", "छत्तीसगढ़", "छत्तीसगड"),
    ("DADRA_AND_NAGAR_HAVELI_AND_DAMAN_AND_DIU", "Dadra and Nagar Haveli and Daman and Diu",
     "दादरा नगर हवेली और दमन दीव", "दादरा नगर हवेली आणि दमण दीव"),
    ("DELHI", "Delhi", "दिल्ली", "दिल्ली"), ("GOA", "Goa", "गोवा", "गोवा"), ("GUJARAT", "Gujarat", "गुजरात", "गुजरात"),
    ("HARYANA", "Haryana", "हरियाणा", "हरियाणा"), ("HIMACHAL_PRADESH", "Himachal Pradesh", "हिमाचल प्रदेश", "हिमाचल प्रदेश"),
    ("JAMMU_AND_KASHMIR", "Jammu and Kashmir", "जम्मू और कश्मीर", "जम्मू आणि काश्मीर"),
    ("JHARKHAND", "Jharkhand", "झारखंड", "झारखंड"), ("KARNATAKA", "Karnataka", "कर्नाटक", "कर्नाटक"),
    ("KERALA", "Kerala", "केरल", "केरळ"), ("LADAKH", "Ladakh", "लद्दाख", "लडाख"),
    ("LAKSHADWEEP", "Lakshadweep", "लक्षद्वीप", "लक्षद्वीप"), ("MADHYA_PRADESH", "Madhya Pradesh", "मध्य प्रदेश", "मध्य प्रदेश"),
    ("MANIPUR", "Manipur", "मणिपुर", "मणिपूर"), ("MEGHALAYA", "Meghalaya", "मेघालय", "मेघालय"),
    ("MIZORAM", "Mizoram", "मिज़ोरम", "मिझोराम"), ("NAGALAND", "Nagaland", "नागालैंड", "नागालँड"),
    ("ODISHA", "Odisha", "ओडिशा", "ओडिशा"), ("PUDUCHERRY", "Puducherry", "पुडुचेरी", "पुदुच्चेरी"),
    ("PUNJAB", "Punjab", "पंजाब", "पंजाब"), ("RAJASTHAN", "Rajasthan", "राजस्थान", "राजस्थान"),
    ("SIKKIM", "Sikkim", "सिक्किम", "सिक्कीम"), ("TAMIL_NADU", "Tamil Nadu", "तमिलनाडु", "तमिळनाडू"),
    ("TELANGANA", "Telangana", "तेलंगाना", "तेलंगणा"), ("TRIPURA", "Tripura", "त्रिपुरा", "त्रिपुरा"),
    ("UTTAR_PRADESH", "Uttar Pradesh", "उत्तर प्रदेश", "उत्तर प्रदेश"), ("UTTARAKHAND", "Uttarakhand", "उत्तराखंड", "उत्तराखंड"),
    ("WEST_BENGAL", "West Bengal", "पश्चिम बंगाल", "पश्चिम बंगाल"),
):
    LABELS[_code] = {"en": _en, "hi": _hi, "mr": _mr}


# G2 forbidden phrases: second-person promises only (D5). Single words like "पात्र", "पात्रता",
# "मिलेगा", "eligible" are NOT here: they appear in honest text ("eligible farmers get ...").
FORBIDDEN = {
  "en": ("you are eligible", "you're eligible", "you qualify", "you are entitled",
         "you will get", "you will receive", "you can get", "you will definitely",
         "you are sure to get", "guaranteed to you"),
  "hi": ("आप पात्र हैं", "आप हकदार हैं", "आपको मिलेगा", "आपको मिलेगी", "आपको मिलेंगे",
         "आप पा सकते हैं", "आपको ज़रूर", "तुम्हें मिलेगा", "आपको पक्का"),
  "mr": ("तुम्ही पात्र आहात", "आपण पात्र आहात", "तुम्ही हक्कदार आहात", "तुम्हाला मिळेल",
         "तुम्हाला मिळतील", "तुम्हाला मिळू शकते", "तुम्हाला नक्की", "तुम्हाला खात्रीने"),
}


def _fold(text: str, lang: str) -> str:
    """Normalize for comparison: NFC, then (for hi/mr) drop the nukta U+093C so ज़ == ज."""
    folded = unicodedata.normalize("NFC", text)
    if lang in ("hi", "mr"):
        folded = folded.replace("़", "")
    return folded.lower()


def find_forbidden(text: str, lang: str) -> str | None:
    """First forbidden phrase found in text, else None. Case-insensitive for en; for hi/mr compare
    after unicodedata NFC and removing the nukta U+093C on both sides (so ज़ == ज)."""
    folded_text = _fold(text, lang)
    for phrase in FORBIDDEN.get(lang, ()):
        if _fold(phrase, lang) in folded_text:
            return phrase
    return None


# Verdicts about the caller (G2, step 7.1): any yes/no on "you can apply", "you will get", both ways.
# Rule statements about a group ("farmers can apply") are fine; it is "you" that is banned.
# Patterns are written without the nukta because the text is folded first (see _fold).
_VERDICT_SRC = {
  "en": (r"\byou\s+(?:can|could|may|cannot|can't|can\s+not)\s+(?:not\s+)?(?:\w+\s+)?(?:apply|get|receive|claim|qualify)",
         r"\byou(?:'re|\s+are)\s+(?:not\s+)?(?:eligible|entitled|qualified)",
         r"\byou\s+(?:will|won't|will\s+not|do\s+not|don't)\s+(?:definitely\s+)?(?:get|receive|qualify)",
         r"\byou\s+(?:qualify|do\s+qualify)\b"),
  "hi": (r"आप\s+(?:(?:आवेदन|अप्लाई|अर्जी)\s+)?(?:नहीं\s+)?कर\s+सकत",
         r"आप(?:\s+इसके\s+लिए)?\s+(?:नहीं\s+)?पात्र",
         r"पात्र\s+हैं\s+आप",
         r"आपको\s+(?:\S+\s+)?(?:नहीं\s+)?मिल(?:ेगा|ेगी|ेंगे|\s+जाएगा|\s+जाएगी|\s+सकत)",
         r"आप\s+(?:नहीं\s+)?पा\s+सकत",
         r"मिल\s+जाएगा"),
  "mr": (r"(?:तुम्ही|आपण)\s+(?:\S+\s+)?(?:अर्ज\s+)?करू\s+शकत",
         r"(?:तुम्ही|आपण)\s+(?:\S+\s+)?पात्र",
         r"(?:तुम्हाला|आपल्याला)\s+(?:\S+\s+)?(?:मिळेल|मिळणार|मिळतील|मिळू\s+शकत|मिळत\s+नाही)"),
}
VERDICT = {lang: tuple(re.compile(_fold(p, lang)) for p in pats) for lang, pats in _VERDICT_SRC.items()}


def find_verdict(text: str, lang: str) -> str | None:
    """First yes/no verdict about the caller found in text, else None. English patterns always run
    (answers mix languages); the caller's own language runs after them."""
    for code in ("en", lang) if lang != "en" else ("en",):
        folded_text = _fold(text, code)
        for pattern in VERDICT.get(code, ()):
            m = pattern.search(folded_text)
            if m:
                return m.group(0)
    return None
