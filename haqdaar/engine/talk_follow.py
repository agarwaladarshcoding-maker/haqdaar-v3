"""haqdaar/engine/talk_follow.py

Step 1.8 (A): follow-up talk, by fixed words. "The second one", "any other?", "the one before", "which
gives more", "will I get it?", "I did not understand", "how much did you say", "hold on", "can you hear
me?": the code finds these in the caller's words (hi, mr, en) and the talk acts on them; the model only
does the wording. Pure: no model, no I/O.
"""
from __future__ import annotations

import re
from typing import Sequence

from haqdaar.data import scheme_names

_TOK = re.compile(r"[a-z0-9']+|[ऀ-ॿ]+")

SECOND = ("दूसरा", "दूसरी", "दूसरे", "दुसरा", "दुसरी", "दुसरे", "दूजा", "second one", "the second", "2nd")
FIRST = ("पहला", "पहली", "पहले वाला", "पहले वाली", "पहले वाले", "पहिला", "पहिली", "पहिले", "first one", "the first", "1st")
BACK = ("पिछला", "पिछली", "पिछले", "मागचा", "मागची", "मागचे", "आधीचा", "आधीची", "आधीचे",
        "one before", "the previous", "previous one", "earlier one", "the earlier", "before that")
# "any other?": a word for "other" next to a word for "any / more / scheme". "और बताइए" (more of the
# same scheme) is NOT here: it has no "कोई" / "योजना".
ANY_OTHER = ("और कोई", "कोई और", "कोई दूसरी", "कोई दूसरा", "दूसरी योजना", "दूसरी स्कीम", "और योजना", "और योजनाएं",
             "और स्कीम", "अन्य योजना", "आणखी काही", "आणखी कोणती", "आणखी योजना", "अजून काही", "अजून कोणती",
             "अजून योजना", "दुसरी योजना", "दुसरे काही",
             "any other", "another scheme", "another one", "other scheme", "other schemes", "something else",
             "anything else", "one more", "more schemes")
SIDE = ("किसमें ज़्यादा", "किसमें ज्यादा", "किस में ज्यादा", "कौन सी ज़्यादा", "कौन सी ज्यादा", "कौनसी ज्यादा",
        "कौन सा ज्यादा", "कौन सा ज़्यादा", "दोनों में", "दोनों योजना", "दोनों का", "फ़र्क", "फर्क",
        "कोणत्यात जास्त", "कोणती जास्त", "कोणता जास्त", "दोन्ही", "फरक",
        "which gives more", "which one gives more", "which is more", "which one is more", "which is better",
        "which one is better", "which is bigger", "compare", "difference", "between the two", "both of them")
# "will I get it": no promise. Also the door the just-tell talk leaves open (talk.py reads this list).
WILL_GET = ("मिलेगा क्या", "मिलेगी क्या", "मुझे मिलेगा", "मुझे मिलेगी", "मेरे को मिलेगा", "मैं पात्र", "milega",
            "milegi", "मिळेल का", "मला मिळेल", "मी पात्र",
            "will i get", "will i receive", "can i get", "am i eligible", "do i qualify", "would i get")
SIMPLER = ("समझ नहीं आया", "समझ नही आया", "समझ नहीं आई", "समझ में नहीं आया", "समझा नहीं", "समझी नहीं",
           "samajh nahi", "samajh nahin", "आसान शब्दों", "दूसरे शब्दों", "दुसऱ्या शब्दांत", "आसान भाषा", "सरल शब्दों", "सीधे शब्दों",
           "कळले नाही", "कळलं नाही", "समजले नाही", "समजलं नाही", "समजला नाही", "सोप्या शब्दात", "सोप्या शब्दांत",
           "did not understand", "didn't understand", "don't understand", "do not understand",
           "say it simply", "simple words", "easy words", "simpler")
HOW_MUCH = ("कितना बोला", "कितना कहा", "कितना बताया", "कितने बोले", "कितना बोले", "कितना बोली", "कितने रुपये बोले",
            "किती म्हणाल", "किती म्हणालात", "किती म्हणालास", "किती सांगितले", "किती सांगितलेत", "किती बोलला", "kitna bola", "kitna kaha",
            "how much did you say", "how much was it", "how much did you", "what amount did you")
# A hold is a short remark; a long sentence with "रुको" in it is something else.
HOLD = ("एक मिनट", "एक मिनिट", "एक सेकंड", "एक सेकेंड", "एक क्षण", "रुको", "रुकिए", "रुकिये", "ठहरो", "ठहरिए",
        "थांबा", "थांबता", "hold on", "hold the line", "wait a minute", "wait a moment", "wait one", "please wait",
        "one minute", "one moment", "just a minute", "just a moment", "give me a minute", "give me a moment")
HOLD_TOKENS = 5
HEAR = ("can you hear me", "do you hear me", "are you there", "आवाज़ आ रही", "आवाज आ रही", "आवाज़ सुनाई",
        "सुनाई दे रहा", "सुनाई दे रही", "सुन रहे हो", "सुन रही हो", "सुन रहे हैं", "आप हैं", "ऐकू येत", "ऐकू येतंय",
        "ऐकतोय", "ऐकताय")
# 4.2: the caller wants to send or show a photo: a word for photo next to a word for send / show / take
# (matched by the start of the word: bhej, bhejun, bhejna), or one of the short "I can show you" forms.
PHOTO_WORDS = ("photo", "photos", "foto", "pic", "pics", "picture", "pictures", "tasveer", "tasvir", "फोटो", "फ़ोटो",
               "फोटू", "फ़ोटू", "तस्वीर", "छवि")
PHOTO_VERBS = ("send", "show", "take", "upload", "bhej", "dikha", "dikhaun", "pathav", "pathva", "dakhav", "khich", "kheench",
               "भेज", "दिखा", "दिखाऊ", "पाठव", "दाखव", "खींच", "खिंच", "काढ")
SHOW_YOU = ("dikha sakta hoon", "dikha sakti hoon", "dikha sakta hu", "dikha doon", "दिखा सकता हूँ", "दिखा सकता हूं",
            "दिखा सकती हूँ", "दिखा सकती हूं", "दिखा दूं", "दिखा दूँ", "दाखवू शकतो", "दाखवू शकते", "दाखवू का",
            "can i show you", "can i show it", "let me show you", "i can show you")
# Asking for the link outright is the same as asking to send a photo.
LINK_ASK = ("send the link", "send me the link", "send link", "लिंक भेज", "link bhej", "लिंक पाठव")
# 4.2: a need one can SEE. Short and exact: no bare "house" or "crop".
PHOTO_SEEN = ("my crop is spoiled", "my crop is ruined", "my crop is damaged", "my crop is destroyed", "my crop died",
              "my crops are spoiled", "my crops are ruined", "my crops are damaged", "my crops died", "crop got spoiled",
              "crop got damaged", "crops got damaged", "crop failed", "crops failed", "insects on my crop",
              "insects in my crop", "pests on my crop", "pests in my crop", "pest attack", "worms on my crop",
              "house fell", "house collapsed", "house is damaged", "house got damaged", "house was damaged",
              "my house broke", "roof fell", "roof collapsed", "wall fell", "wall collapsed",
              "cow is sick", "buffalo is sick", "goat is sick", "my animal is sick", "my cow died", "my buffalo died",
              "my goat died", "my animal died", "cow is dead", "buffalo is dead",
              "field is flooded", "fields are flooded", "field got flooded", "water in my field", "flood in my field",
              "फसल खराब", "फसल ख़राब", "फसल बर्बाद", "फसल सूख गई", "फसल सड़ गई", "फसल में कीड़े", "फसल में कीड़ा",
              "फसल में कीट", "घर गिर गया", "घर गिर गई", "घर गिरा", "घर टूट गया", "मकान गिर गया", "मकान टूट गया", "छत गिर गई",
              "छत गिर गयी", "गाय बीमार", "भैंस बीमार", "बकरी बीमार", "जानवर बीमार", "गाय मर गई", "भैंस मर गई",
              "बकरी मर गई", "जानवर मर गया", "खेत में पानी भर", "खेत डूब", "खेत में बाढ़",
              "fasal kharab", "fasal barbad", "fasal mein keede", "ghar gir gaya", "ghar toot gaya", "gaay beemar",
              "bhains beemar", "janwar beemar", "khet mein pani bhar",
              "पीक खराब", "पीक वाया गेले", "पिकावर कीड", "पिकाला कीड", "घर पडले", "घर पडलं", "घर कोसळले",
              "भिंत पडली", "छप्पर पडले", "गाय आजारी", "म्हैस आजारी", "शेळी आजारी", "जनावर आजारी", "गाय मेली",
              "म्हैस मेली", "जनावर मेले", "शेतात पाणी साचले", "शेतात पाणी भरले")
# Short answers (at most YES_NO_TOKENS words). A no word wins: "no, not now" is a no.
YES = ("yes", "yeah", "yep", "ok", "okay", "sure", "please", "send it", "go ahead", "do it", "haan", "han", "haa", "ji",
       "ji haan", "theek hai", "bhej do", "bhejiye", "bhejo", "हाँ", "हां", "हा", "हाँ जी", "हां जी", "जी", "जी हाँ",
       "जी हां", "ठीक है", "भेज दो", "भेज दीजिए", "भेजिए", "भेजो", "होय", "हो", "ठीक आहे", "पाठवा", "पाठव")
NO = ("no", "nope", "nah", "no thanks", "not now", "don't", "dont", "nahi", "nahin", "nai", "mat", "नहीं", "नही", "ना",
      "मत", "रहने दो", "रहने दीजिए", "नको", "नाही", "नका", "राहू दे")
YES_NO_TOKENS = 4
HELLO_WORDS = frozenset({"hello", "hallo", "हैलो", "हेलो", "हॅलो", "हलो"})
HEAR_TOKENS = 8


def _has(text: str, forms: Sequence[str]) -> bool:
    lowered = " " + " ".join(str(text).lower().split()) + " "
    return any(scheme_names.contains_word(lowered, f) for f in forms)


def pick(words: str, last_named: Sequence[str], all_named: Sequence[str], focus: str) -> tuple[str, str]:
    """("move", scheme id): the caller points at a scheme already named ("the second one", "the one
    before"); ("other", ""): the caller wants a scheme not named yet; ("", ""): neither.
    `last_named`: the schemes the last accepted reply named, in order. `all_named`: every scheme named in the call."""
    if simpler(words):                        # "in other words" is not "the other one"
        return "", ""
    if _has(words, BACK):
        at = all_named.index(focus) if focus in all_named else -1
        return ("move", all_named[at - 1]) if at > 0 else ("", "")
    if _has(words, SECOND) and len(last_named) >= 2:
        return "move", last_named[1]
    if _has(words, FIRST):
        if len(last_named) >= 2:
            return "move", last_named[0]
        before = [s for s in all_named if s != focus]
        if before:                            # one scheme in the last reply: "the first one" is an earlier one
            return "move", before[0]
        return "", ""
    if _has(words, ANY_OTHER) or _has(words, SECOND):
        return "other", ""
    return "", ""


def side_by_side(words: str, all_named: Sequence[str]) -> bool:
    return len(all_named) >= 2 and _has(words, SIDE)


def will_get(words: str) -> bool:
    return _has(words, WILL_GET)


def simpler(words: str) -> bool:
    return _has(words, SIMPLER)


def how_much(words: str) -> bool:
    return _has(words, HOW_MUCH)


def hold(words: str) -> bool:
    return len(_TOK.findall(str(words).lower())) <= HOLD_TOKENS and _has(words, HOLD)


def hear(words: str) -> bool:
    toks = _TOK.findall(str(words).lower())
    if not toks or len(toks) > HEAR_TOKENS:
        return False
    return all(t in HELLO_WORDS for t in toks) or _has(words, HEAR)


def photo_ask(words: str) -> bool:
    toks = _TOK.findall(str(words).lower())
    near = any(t in PHOTO_WORDS for t in toks) and any(t.startswith(v) for t in toks for v in PHOTO_VERBS)
    return near or _has(words, SHOW_YOU) or _has(words, LINK_ASK)


def photo_seen(words: str) -> bool:
    return _has(words, PHOTO_SEEN)


def no(words: str) -> bool:
    return len(_TOK.findall(str(words).lower())) <= YES_NO_TOKENS and _has(words, NO)


def yes(words: str) -> bool:
    return len(_TOK.findall(str(words).lower())) <= YES_NO_TOKENS and not no(words) and _has(words, YES)
