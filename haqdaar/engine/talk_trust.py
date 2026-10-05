"""haqdaar/engine/talk_trust.py

Step 1.8 (B): fixed answers to what a caller says about the LINE and not about a scheme: is it free, who
are you, a long number being read out, what the line can not do, giving up on life, "thanks", "slowly".
Same pattern as talk_follow: word lists in hi, mr, en; each list exact; the talk acts on them.
Pure: no model, no I/O. The Hindi and Marathi lists are not checked by a speaker.
"""
from __future__ import annotations

import re
from haqdaar.engine.talk_follow import _TOK, _has

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# --- trust: short, exact. A scheme or a need word in the sentence sends it to the model (see trust_free) ---
FREE = ("is it free", "is this free", "is it free of charge", "is the call free", "is this call free", "is the line free",
        "is this service free", "is the service free", "do i have to pay", "do i need to pay", "will you charge",
        "do you charge", "are you charging", "any charge", "any charges", "any fees", "will it cost me",
        "क्या यह मुफ्त है", "क्या यह मुफ़्त है", "मुफ्त है", "मुफ़्त है", "फ्री है", "फ्री है क्या", "पैसे लगेंगे",
        "पैसे लगते", "पैसे देने पड़ेंगे", "पैसे कटेंगे", "चार्ज लगेगा", "कुछ देना पड़ेगा",
        "फुकट आहे", "फुकट आहे का", "मोफत आहे", "फ्री आहे", "पैसे लागतील", "पैसे लागतात", "चार्ज लागेल")
SCHEME_WORDS = ("scheme", "schemes", "yojana", "yojna", "योजना", "योजनेचे", "योजनेत", "योजनाएं", "स्कीम", "card", "कार्ड",
                "insurance", "बीमा", "विमा")
GOVERNMENT = ("are you the government", "are you government", "are you from the government", "are you from government",
              "are you a government", "is this the government", "is this government", "are you govt", "are you from govt",
              "क्या आप सरकार", "आप सरकार हैं", "आप सरकार से", "आप सरकारी हैं", "आप सरकारी हो", "आप सरकार की",
              "तुम्ही सरकार", "तुम्ही सरकारी", "सरकारी आहात")
PERSON = ("are you a person", "are you a human", "are you human", "are you a machine", "are you a robot",
          "are you a computer", "are you a real person", "are you real", "is this a machine", "is this a robot",
          "is this a recording", "is this a person",
          "आप इंसान", "इंसान हो", "आप मशीन", "मशीन हो", "रोबोट हो", "आप रोबोट", "आदमी हो", "आप असली", "क्या आप असली",
          "माणूस आहात", "तुम्ही माणूस", "मशीन आहात", "रोबोट आहात", "तुम्ही मशीन")
TO_PERSON = ("talk to a person", "talk to someone", "talk to a human", "talk to a real person", "speak to a person",
             "speak to someone", "speak to a human", "speak to a real person", "i want a person", "i want a human",
             "connect me to a person", "give me a person", "human agent",
             "इंसान से बात", "इंसान से बात कराओ", "किसी इंसान", "आदमी से बात", "किसी से बात करा", "व्यक्ति से बात",
             "माणसाशी बोला", "माणसाशी बोलायचे", "माणसाशी बोलायचं", "माणसाशी बात", "कोणाशी तरी बोला", "कोणाशी बोलायचे")
TRUST_TOKENS = 10

# --- what the line can not do ---
FORM = ("fill the form for me", "fill my form", "fill out my form", "fill this form for me", "can you fill",
        "will you fill", "please fill the form", "apply for me", "apply on my behalf", "can you apply", "will you apply",
        "submit the form for me", "submit my application", "register me", "enrol me", "enroll me",
        "फॉर्म भर दो", "फॉर्म भर दीजिए", "फॉर्म भर दीजिये", "फॉर्म भर दें", "मेरा फॉर्म भर", "मेरे लिए आवेदन", "मेरी तरफ से आवेदन",
        "मेरी तरफ़ से आवेदन", "आवेदन कर दो", "आवेदन कर दीजिए", "अप्लाई कर दो", "मेरे लिए अप्लाई", "अप्लाई कर दीजिए",
        "फॉर्म भरून द्या", "फॉर्म भरा माझा", "माझ्यासाठी अर्ज", "माझ्या वतीने अर्ज", "अर्ज करून द्या", "अर्ज भरून द्या")
PAYMENT = ("check my payment", "check my status", "check my application", "check my money", "status of my application",
           "application status", "when will the money come", "when will my money come", "when will i get the money",
           "when will i get my money", "where is my money", "my money has not come", "my payment has not come",
           "my money did not come", "my payment did not come", "payment not received", "money not received",
           "मेरा पेमेंट चेक", "मेरा स्टेटस", "स्टेटस चेक", "आवेदन की स्थिति", "पैसा कब आएगा", "पैसे कब आएंगे",
           "पैसे कब आयेंगे", "पैसा कब आयेगा", "पैसा नहीं आया", "पैसे नहीं आए", "पैसे नहीं आये", "पैसा अभी तक नहीं",
           "पेमेंट कब", "किस्त कब", "क़िस्त कब", "किश्त कब",
           "पैसे कधी येतील", "पैसे आले नाहीत", "पैसे अजून आले नाहीत", "स्टेटस तपासा", "स्टेटस तपासून", "माझे पेमेंट", "हप्ता कधी")
SMS_WORDS = ("sms", "message", "messages", "text", "whatsapp", "एसएमएस", "मैसेज", "संदेश", "व्हाट्सएप", "व्हॉट्सअॅप", "मेसेज")
SMS_VERBS = ("send", "sms", "text", "whatsapp", "bhej", "भेज", "पाठव", "भेजो", "भेजिए")
SMS_TOKENS = 12

# --- a number being read out: Aadhaar, bank, OTP ---
READ_START = ("my aadhaar number is", "my aadhar number is", "my aadhaar is", "my aadhar is", "my otp is", "otp is",
              "my account number is", "account number is", "my bank account number is",
              "मेरा आधार नंबर", "मेरा आधार नंबर है", "आधार नंबर है", "मेरा ओटीपी", "ओटीपी है", "मेरा खाता नंबर",
              "खाता नंबर है", "मेरा अकाउंट नंबर",
              "माझा आधार नंबर", "माझा ओटीपी", "माझा खाते क्रमांक", "आधार क्रमांक आहे", "खाते क्रमांक आहे")
CUES = ("aadhaar", "aadhar", "adhar", "आधार", "account", "अकाउंट", "खाता", "खाते", "bank", "बैंक", "बँक")
OTP = ("otp", "ओटीपी")
# A 6 or 7 digit number with one of these is an amount or a pin code, not a number to stop.
EXEMPT = ("income", "salary", "earn", "earning", "earns", "rupees", "rupee", "rs", "₹", "pin", "pincode", "रुपये", "रुपए",
          "रुपया", "कमाई", "आमदनी", "आय", "पगार", "वेतन", "उत्पन्न", "पिन", "पिनकोड")
DIGIT_WORDS = frozenset(
    "zero one two three four five six seven eight nine ek do teen char paanch panch chhe chhah saat aath nau "
    "शून्य ज़ीरो जीरो एक दो तीन चार पांच पाँच छह छः छे सात आठ नौ दोन पाच सहा नऊ".split())
_EDGE = ".,;:!?()-–"

# --- giving up on life, or a death in the house ---
LIFE = ("want to die", "wanna die", "kill myself", "end my life", "end it all", "no reason to live", "do not want to live",
        "don't want to live", "dont want to live", "better off dead", "suicide", "give up on life", "ready to die",
        "life is over", "मरना चाहता", "मरना चाहती", "जीना नहीं चाहता", "जीना नहीं चाहती", "जीने का मन नहीं",
        "जीने की इच्छा नहीं", "आत्महत्या", "जान दे दूं", "जान दे दूँ", "जिंदगी खत्म", "ज़िंदगी खत्म", "ज़िंदगी ख़त्म",
        "मर जाऊं", "मर जाऊँ", "मरावेसे वाटते", "मरावेसे वाटतंय", "जगावेसे वाटत नाही", "जगायचे नाही", "जगायचं नाही",
        "जीव द्यावा", "जीव देईन", "आयुष्य संपवायचे", "आयुष्य संपवेन")
RELATIONS = ("husband", "wife", "father", "mother", "son", "daughter", "brother", "sister", "child", "parents", "dad",
             "mom", "पति", "पत्नी", "पिता", "पिताजी", "माँ", "मां", "माता", "बेटा", "बेटी", "भाई", "बहन", "बच्चा", "बच्चे",
             "पती", "बायको", "नवरा", "वडील", "आई", "मुलगा", "मुलगी", "भाऊ", "बहीण", "मूल")
DEATH = ("died", "passed away", "is dead", "has died", "is no more", "expired", "death in the family",
         "death in our house", "death in my house", "गुज़र गए", "गुजर गए", "गुज़र गये", "गुजर गये", "गुज़र गई",
         "गुजर गई", "गुज़र गया", "गुजर गया", "नहीं रहे", "नहीं रहीं", "नहीं रही", "नहीं रहा", "मर गए", "मर गया",
         "मर गई", "चल बसे", "चल बसी", "देहांत", "मृत्यु हो गई", "मृत्यु हो गया", "निधन", "मौत हो गई", "मौत हो गया",
         "वारले", "वारला", "वारली", "निधन झाले", "निधन झाल", "मृत्यू झाला", "मृत्यू झाली", "मरण पावले", "मरण पावला")
DEATH_HOUSE = ("death in the family", "death in our house", "death in my house", "घर में मौत", "घर में मृत्यु",
               "घरात मृत्यू", "घरात निधन")

# --- "thanks" is not goodbye ---
THANKS = ("thanks", "thank", "thankyou", "धन्यवाद", "शुक्रिया", "शुक्रीया", "आभार", "आभारी", "धन्यवाद", "आभारी आहे")
BYE = ("bye", "goodbye", "good bye", "bye bye", "अलविदा", "फिर मिलेंगे", "रखता हूं", "रखता हूँ", "रखती हूं", "रखती हूँ",
       "चलता हूं", "चलता हूँ", "चलती हूं", "चलती हूँ", "ठेवतो", "ठेवते", "निरोप", "फोन रख", "call end")
THANKS_TOKENS = 4
NOTHING_MORE = ("that is all", "that's all", "thats all", "nothing", "nothing else", "no more", "बस", "बस इतना", "कुछ नहीं",
                "और कुछ नहीं", "आणखी काही नाही", "काही नाही", "एवढेच")

# --- the pace of the voice ---
SLOW = ("slowly", "speak slowly", "talk slowly", "say it slowly", "slow down", "speak slow", "too fast", "slower",
        "धीरे बोलो", "धीरे बोलिए", "धीरे बोलिये", "धीरे बोलें", "धीरे से बोलो", "थोड़ा धीरे", "आराम से बोलो",
        "बहुत तेज़ बोल रहे", "बहुत तेज़ बोल रही", "बहुत तेज बोल रहे", "बहुत तेज बोल रही", "बहुत जल्दी बोल रहे", "बहुत जल्दी बोल रही", "इतना तेज़", "इतना तेज", "हळू बोला", "हळू", "हळूहळू बोला",
        "जरा हळू", "खूप वेगाने", "खूप फास्ट", "dheere bolo", "dheere boliye")
NORMAL = ("normal speed", "normal pace", "speak normally", "talk normally", "speak faster", "talk faster", "faster", "speak fast",
          "तेज़ बोलो", "तेज बोलो", "तेज़ बोलिए", "तेज बोलिए", "जल्दी बोलो", "सामान्य गति", "नॉर्मल स्पीड",
          "वेगाने बोला", "नेहमीसारखे बोला", "नेहमीच्या गतीने", "नॉर्मल बोला")
SLOW_TOKENS = 6


def _n(words: str) -> int:
    return len(_TOK.findall(str(words).lower()))


def trust_free(words: str, blocked: bool = False) -> bool:
    """"Is it free?" about the LINE. `blocked`: the code found a scheme name or a need in the words ("is
    the insurance free" is a question about a scheme: the model has the papers). A scheme word blocks it
    too, and so does a long sentence."""
    return (_n(words) <= TRUST_TOKENS and not blocked and not _has(words, SCHEME_WORDS) and _has(words, FREE))


def trust(words: str, blocked: bool = False) -> str:
    """"free", "government", "person" or "to_person" (the key of a prompts.talk.TRUST line), else ""."""
    if _n(words) > TRUST_TOKENS:
        return ""
    if _has(words, GOVERNMENT):
        return "government"
    if _has(words, PERSON):
        return "person"
    if _has(words, TO_PERSON):
        return "to_person"
    return "free" if trust_free(words, blocked) else ""


def cannot(words: str) -> str:
    """"form", "payment" or "sms" (the key of a prompts.talk.CANNOT line), else ""."""
    if _has(words, FORM):
        return "form"
    if _has(words, PAYMENT):
        return "payment"
    toks = _TOK.findall(str(words).lower())
    if len(toks) <= SMS_TOKENS and _has(words, SMS_WORDS) and (_has(words, SMS_VERBS) or any(t.startswith(("bhej", "pathav")) for t in toks)):
        return "sms"
    return ""


def _digits_in(token: str) -> int:
    token = token.strip(_EDGE)
    if token in DIGIT_WORDS:
        return 1
    return len(re.sub(r"\D", "", token)) if token and re.fullmatch(r"[\d\-–]+", token) else 0


def _groups(text: str) -> list[tuple[int, int, int]]:
    """Runs of tokens that are digits or spoken digit words: (first token, last token + 1, digits in it)."""
    out: list[tuple[int, int, int]] = []
    start, total = -1, 0
    toks = text.split()
    for i, tok in enumerate(toks + [""]):
        d = _digits_in(tok) if tok else 0
        if d:
            start, total = (i, 0) if start < 0 else (start, total)
            total += d
        elif start >= 0:
            out.append((start, i, total))
            start, total = -1, 0
    return out


def read_out(words: str) -> bool:
    """The caller starts to read out a long number (6 or more digits, as digits or as digit words), or says
    "my Aadhaar number is", or gives an OTP. An age, an income, a land size and a year are not this: a
    6 or 7 digit amount with an income or pin word is let through, and so is any short number."""
    text = " ".join(str(words).lower().translate(_DEVANAGARI_DIGITS).split())
    if _has(text, READ_START):
        return True
    cue, otp, exempt = _has(text, CUES), _has(text, OTP), _has(text, EXEMPT)
    for _a, _b, d in _groups(text):
        if d >= 8 or (d >= 6 and (cue or otp or not exempt)) or (otp and d >= 4):
            return True
    return False


def mask(words: str) -> str:
    """The words with every number in them cut out, when they are a number being read out; else as they are.
    This is what the log and the later prompts hold."""
    if not read_out(words):
        return words
    toks = str(words).translate(_DEVANAGARI_DIGITS).split()
    cut = {i for a, b, d in _groups(" ".join(t.lower() for t in toks)) if d >= 2 for i in range(a, b)}
    out: list[str] = []
    for i, tok in enumerate(toks):
        if i not in cut:
            out.append(tok)
        elif not out or out[-1] != "…":
            out.append("…")
    return " ".join(out)


def distress(words: str) -> bool:
    """Words of giving up on life, or of a death in the house ("my husband passed away", "मेरे पति गुज़र गए").
    A cow that died is not this: the death word must come with a person of the family."""
    toks = set(_TOK.findall(str(words).lower()))
    return (_has(words, LIFE) or _has(words, DEATH_HOUSE)
            or (_has(words, DEATH) and any(r in toks for r in RELATIONS)))


def thanks(words: str) -> bool:
    """A bare "thanks": short, with no goodbye in it."""
    return 0 < _n(words) <= THANKS_TOKENS and _has(words, THANKS) and not _has(words, BYE)


def no_more(words: str) -> bool:
    return _n(words) <= THANKS_TOKENS and _has(words, NOTHING_MORE)


def pace(words: str) -> str:
    """"slow", "normal" or "": the caller asks for another speed of the voice."""
    if _n(words) > SLOW_TOKENS:
        return ""
    if _has(words, SLOW):
        return "slow"
    return "normal" if _has(words, NORMAL) else ""
