"""haqdaar/contracts/vocab.py

UNOWNED. Closed vocabulary lists, keypad order, trilingual labels, and forbidden phrases
(D6, 05-DATA-CONTRACT.md §1C, §3 Gate 4). One file, so the pipeline (which validates a
facet value against a list) and the engine (which reads a keypad menu aloud) can never
drift apart.

Plain module, no imports from pipeline/engine. The order of each list IS the keypad
order (key 1 = first item).
"""
from __future__ import annotations

import unicodedata

from haqdaar.contracts.types import ANY  # re-use the existing ANY constant

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
