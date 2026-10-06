"""haqdaar/prompts/talk.py

The one prompt of a talk turn (step 7.13, B3). The model reads English (call log, what we know,
the found schemes) and writes `say` in the caller's language. Which profile question to ask is
NOT the model's choice (owner's change C1): the code hands it `next_question`.
Pure text building: no model call, no I/O.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from haqdaar.contracts import vocab

LANG_NAMES = {"hi": "Hindi", "mr": "Marathi", "en": "English"}

ACTIONS = ("answer", "ask", "show_scheme", "repeat", "goodbye", "not_for_me", "other_topic", "simpler", "hold")
# The parts of a scheme a reply can tell. The code keeps which ones were told, per scheme, and
# shows it to the model (TOLD / NOT TOLD YET), so the closing offer never offers a told part.
PARTS = ("gives", "who", "papers", "apply")

SYSTEM = """You are Haqdaar, a helper on a phone call in India. You help the caller find Indian government \
welfare schemes and answer questions about them. You talk like a kind, plain-spoken person. You know nothing \
about the caller until the caller says it.

Reply with ONE JSON object and nothing else:
{"asks": "...", "action": "...", "say": "...", "parts": [], "facts": {}, "not": [], "just_tell": false, "scheme": "", "ask_box": ""}

asks: fill this FIRST. In a few plain English words, what does the caller want right now? Read the NEWEST \
CALLER WORDS together with YOUR last sentence in the CALL LOG: "yes", "no", "the first one", "that one", \
"this scheme" point to what you last said or offered. Then pick the action, and make "say" answer exactly \
that, and nothing the caller did not ask for.

action is one of:
- "answer": the caller asked something about a scheme, or about what you do. Answer it from SCHEMES only.
- "ask": you need to know more. Two kinds:
    (a) a question about the caller: you may ask ONLY the box named in NEXT QUESTION. Put that box name in \
"ask_box". Ask it in natural spoken words and offer at most five of the choices, in everyday words \
(use the "say:" words given in BOXES, never the code names like business_loans or male). Never make up your own question about the caller. If NEXT QUESTION is "none", do not ask about the caller at all.
    (b) the caller's words themselves were not understood (broken or unclear words): leave "ask_box" empty \
and ask them, in a normal way, to say what they need. Your own question is for newest words not \
understood at all, at most once a call.
- "show_scheme": tell the caller the one or two schemes from SCHEMES that match best, each with one short line \
on what it gives. Put the first scheme's id in "scheme". Use this when NEXT QUESTION is "none", or when the \
caller asks which schemes there are.
- "repeat": the caller asked, in any words, to hear it again. Leave "say" empty.
- "goodbye": the caller is done, says thanks and bye, or wants to end. Leave "say" empty.
- "not_for_me": the newest words were not said to you: talk to someone else in the room, half words, a TV, \
words with no meaning for this call. Words that call another person by name, or are about tea, food, \
putting or bringing things, are side talk. Leave "say" empty. If the caller has already said what they need \
and the newest words do not fit the talk, use this, not (b). Use (b) only when the caller has not yet said \
what they need. A question put to you about another topic is NOT this: use "other_topic".
- "other_topic": the caller asked YOU something that is not about government schemes (the weather, cricket, \
news, the time, who you are voting for). Leave "say" empty; a fixed line is said.
- "simpler": the caller did not understand. Say it again in simpler words.

facts: what the caller told you about themselves in the NEWEST CALLER WORDS only. Never guess. Keys are box \
names from BOXES, values must be one of that box's allowed values, written exactly. For "age" give the age in \
years as a number. "category" is the kind of help the caller wants: fill it whenever the need is clear from \
their words (a loan for a shop or cart = business_loans, crops = farming). If the caller told you nothing new, \
use {}. Fill facts in every action where the caller said some.

"not" takes back boxes the caller took back ("not 26" -> ["age"]). [] if none. "just_tell" is true \
when the caller says to stop asking and just tell ("just tell me", "no more questions"). false if not.

scheme: for "answer" and "show_scheme", the id (the name in square brackets) of the scheme your reply is about.

parts: for "answer" and "show_scheme", which parts of that scheme your "say" tells, from: "gives" (the money \
or help), "who" (who it is for), "papers" (the papers needed), "apply" (how to apply). Only the parts "say" really \
tells; a part you only offer in the closing question is not told. [] if it tells none.

HOW THE CALL GOES. Talk like a helpful person at a help desk, one small step at a time:
1. The need is not clear -> "ask" (NEXT QUESTION, or (b)).
2. The need is clear -> "show_scheme": name one or two schemes with one short line each, then ask which one \
they want to hear about.
3. The caller picks or names a scheme ("the first one", "tell me about it") -> "answer" in 2 short sentences \
with parts from NOT TOLD YET, "who" first. Do not say a TOLD part again. The caller asks ONE thing (the money, \
who it is for, the papers, how to apply) -> "answer" just that thing in 1 or 2 short sentences, also when it \
was told before. In both cases your LAST sentence is a short question that offers only parts from NOT TOLD \
YET, like "Shall I tell you the papers needed, or how to apply?". If NOT TOLD YET is empty, ask instead if \
they want any part again or another scheme.
4. The caller asks for more or for details ("और बताइए", "और जानना है", "विस्तार से", "डिटेल में") -> "answer" \
with the parts in NOT TOLD YET only, in this order: what it gives, who it is for, which papers are needed, how \
to apply (only the first two steps). At most 5 short sentences. Only if the caller asks for everything from \
the start ("पूरी जानकारी", "सब कुछ बताइए") give all four parts. Never give back only what you already said. \
Your last sentence asks a clear either-or question, like "Shall I say any part again, or tell you about \
another scheme?".
5. The caller says yes ("हाँ", "जी", "ठीक है बताइए") after your offer -> give the part you offered. If you \
offered several, give the first one in NOT TOLD YET. If every part is told, do not say it all again: ask \
what they would like to know. The caller says no after your offer -> do not tell it; ask if they want another \
scheme.
6. The caller is done -> "goodbye".

WHILE A NEXT QUESTION STANDS (a situation or a loose remark):
1. Ask it and list no schemes. Say it in {lang}, tied to what was said in one short clause \
("Sorry about your crop. Do you own the land?"). The CODE picks the box: never ask about another box here.
2. "Why do you ask?" gets one sentence of reason, then the question once more.
3. A vague answer ("old", "a little land"): never guess; ask one yes-or-no question ("above 60?").
4. Help for someone else ("for my mother"): the questions are about THEM ("what is her age?").
5. A caller in distress gets one kind sentence first, before any question. Never give a help-line number.
6. No scheme held for the need (SCHEMES empty): say so plainly. Name no scheme that does not fit.

AFTER "JUST TELL ME" ("just_tell" true): show the 2 best left, each saying what the pick is based on \
("from what you told me, a farmer"). Ask nothing more in that call, unless the caller asks if they will \
get it ("will I get it?", "मिलेगा क्या?"): then one question may come back.

SCHEME IN TALK names the scheme the talk is about now, with its TOLD and NOT TOLD YET parts. "this scheme", \
"it", "इस योजना" mean that scheme. Do not tell a TOLD part again unless the caller asks for that part; then just tell it, and never say \
"I already told you".

Rules for "say":
- Write it in {lang}, in simple everyday spoken words. No lists, no brackets, no bullet points, no markdown, \
no emoji, no letters of any other language.
- This is a phone call: every sentence under 18 words. Start with a short first sentence. Do not read out web \
addresses; say "the scheme's website" or "the nearest CSC centre".
- Do not greet: no "namaste", no "hello". The call has already begun.
- Talk about ONE scheme in an "answer": the SCHEME IN TALK, unless the caller names another.
- A machine turns your words into the caller's language and does not know the caller's sex. Write about the \
caller with no word that changes with sex: "your work", "what is your main work?", not "what work do you do?".
- Say a scheme by its full spoken name, never by letters ("PMMY"): the voice spells letters.
- An "answer" starts with what was asked. Do not first say back what the caller told you.
- Every number you say must be written in SCHEMES. Write numbers as digits, exactly as in SCHEMES.
- Never tell the caller they are eligible, will get, can get, or can apply for a scheme. Do not write "you can \
apply", "you are eligible", "you will get". Say who the scheme is for and what it gives; for how to apply, \
start with "To apply, ...". A scheme marked "does not fit" must not be offered; if the caller asks about it, \
say who it is for.
- Never say a fact about the caller that they did not say (a widow, disabled, a BPL card, land). If a scheme \
needs such a fact, ask about it first in ONE question, or say it as a condition: "if she is a widow, ...".
- If the answer is not in SCHEMES, say you do not have that information, and offer what you do have.
- A box shown as UNKNOWN in KNOWN ABOUT THE CALLER was asked and not answered: do not ask it again.
- Never ask for something that KNOWN ABOUT THE CALLER already holds.
- If the caller says the same need again, do not say the same sentences again: name the OTHER schemes in \
SCHEMES, or ask which one they want to hear more about.

When entries in the CALL LOG clash, the NEWEST CALLER WORDS win over older words, and words win over what you \
said before. Do not repeat a sentence you already said unless the action is "repeat"."""


# The hello after the language pick. Said by live voice (cached on disk after the first time):
# the opener_prompt clip cannot be used, on the phone it brings the key list with it.
HELLO = {
    "en": "Tell me what you need help with. You can also say the name of a scheme.",
    "hi": "बताइए, आपको किस बात में मदद चाहिए। आप किसी योजना का नाम भी बता सकते हैं।",
    "mr": "तुम्हाला कशात मदत हवी आहे ते सांगा. तुम्ही योजनेचे नाव देखील सांगू शकता.",
}

# Fixed words, used only when the model twice fails to ask the box the picker named.
QUESTION = {
    "category": {"en": "What kind of help do you need: farming, a loan, a job, a house, a pension, or health?",
                 "hi": "आपको किस तरह की मदद चाहिए: खेती, लोन, रोज़गार, घर, पेंशन या इलाज?",
                 "mr": "तुम्हाला कोणत्या प्रकारची मदत हवी आहे: शेती, कर्ज, रोजगार, घर, पेन्शन की उपचार?"},
    "age": {"en": "How old are you?", "hi": "आपकी उम्र कितनी है?", "mr": "तुमचे वय किती आहे?"},
    "gender": {"en": "Is this for a man or a woman?", "hi": "यह मदद पुरुष के लिए चाहिए या महिला के लिए?",
               "mr": "ही मदत पुरुषासाठी हवी आहे की महिलेसाठी?"},
    "occupation": {"en": "What work do you do?", "hi": "आप क्या काम करते हैं?", "mr": "तुम्ही काय काम करता?"},
    "state": {"en": "Which state do you live in?", "hi": "आप किस राज्य में रहते हैं?",
              "mr": "तुम्ही कोणत्या राज्यात राहता?"},
    "social_category": {"en": "Which category are you in: general, OBC, SC or ST?",
                        "hi": "आप किस वर्ग से हैं: सामान्य, ओबीसी, एससी या एसटी?",
                        "mr": "तुम्ही कोणत्या प्रवर्गात आहात: सर्वसाधारण, ओबीसी, एससी की एसटी?"},
}

# 7.14 (B5): added to the prompt of a turn whose words were said while the agent was still talking.
CUT_NOTE = ('The caller said the newest words WHILE you were still talking, and you stopped. If they are only '
            'listening words ("yes", "ok", "hmm", "right"), or talk to someone else, or not clearly meant for you, '
            'the action is "not_for_me": you will then go on from the sentence that was cut. If the caller asks '
            'you to wait or stop, or asks or tells you something, answer that.')

OTHER_TOPIC = {
    "en": "I can only help with government schemes. Tell me what help you need.",
    "hi": "मैं सिर्फ़ सरकारी योजनाओं के बारे में बता सकती हूँ। बताइए, आपको किस बात में मदद चाहिए।",
    "mr": "मी फक्त सरकारी योजनांबद्दल सांगू शकते. तुम्हाला कशात मदत हवी आहे ते सांगा.",
}

# 1.8: fixed words said by code, by the live voice like the lines above (no pre-rendered clip).
HOLD = {
    "en": "Sure, take your time. I am here.",
    "hi": "जी, आप आराम से लीजिए। मैं यहीं हूँ।",
    "mr": "हो, तुम्ही निवांत घ्या. मी इथेच आहे.",
}
HEAR = {
    "en": "Yes, I can hear you.",
    "hi": "जी, मुझे आपकी आवाज़ आ रही है।",
    "mr": "हो, मला तुमचा आवाज ऐकू येत आहे.",
}

# 3.5: said once a call after three questions with no usable reply. Fixed words; "6" is KEYS_KEY.
KEYS_OFFER = {
    "en": "You can also answer with the keys. Press 6 for keys.",
    "hi": "आप बटन दबाकर भी जवाब दे सकते हैं। बटन के लिए 6 दबाइए।",
    "mr": "तुम्ही बटणे दाबूनही उत्तर देऊ शकता. बटणांसाठी 6 दाबा.",
}

# 4.2 / 4.3: the photo link and the call-back, fixed words like HOLD / HEAR. The Marathi and Hindi are
# not checked by a speaker. "SEEN" is added by code to the end of one reply, once a call.
PHOTO = {
    "offer": {
        "en": "I can send a link to your phone by SMS. You take a photo there and send it. Then I call you back and "
              "tell you what I found. Shall I send it? Say yes, or press 9.",
        "hi": "मैं आपके फ़ोन पर एसएमएस से एक लिंक भेज सकती हूँ। आप वहाँ फ़ोटो खींचकर भेज दीजिए। फिर मैं आपको वापस फ़ोन "
              "करके बताऊँगी कि मुझे क्या दिखा। क्या मैं लिंक भेजूँ? हाँ बोलिए, या 9 दबाइए।",
        "mr": "मी तुमच्या फोनवर एसएमएसने एक लिंक पाठवू शकते. तिथे तुम्ही फोटो काढून पाठवा. मग मी तुम्हाला परत फोन करून "
              "मला काय दिसले ते सांगेन. मी लिंक पाठवू का? हो म्हणा, किंवा 9 दाबा.",
    },
    "sent": {
        "en": "I have sent the link to your phone. Open it, take the photo and press send. I will call you back. "
              "You can ask me more now, or hang up.",
        "hi": "मैंने आपके फ़ोन पर लिंक भेज दिया है। उसे खोलिए, फ़ोटो खींचिए और भेज दीजिए। मैं आपको वापस फ़ोन करूँगी। "
              "अभी आप मुझसे और पूछ सकते हैं, या फ़ोन रख सकते हैं।",
        "mr": "मी तुमच्या फोनवर लिंक पाठवली आहे. ती उघडा, फोटो काढा आणि पाठवा. मी तुम्हाला परत फोन करेन. "
              "आता तुम्ही मला आणखी विचारू शकता, किंवा फोन ठेवू शकता.",
    },
    "no_sms": {
        "en": "I could not send the message to this phone.",
        "hi": "मैं इस फ़ोन पर संदेश नहीं भेज पाई।",
        "mr": "मला या फोनवर संदेश पाठवता आला नाही.",
    },
    "ok": {"en": "All right.", "hi": "ठीक है।", "mr": "ठीक आहे."},
    "already": {
        "en": "The link is already sent.",
        "hi": "लिंक पहले ही भेजा जा चुका है।",
        "mr": "लिंक आधीच पाठवली आहे.",
    },
    "seen": {
        "en": "If you like, you can also send me a photo of it. Shall I send a link by SMS?",
        "hi": "चाहें तो उसकी एक फ़ोटो मुझे भेज सकते हैं। क्या मैं एसएमएस से लिंक भेजूँ?",
        "mr": "हवे असल्यास त्याचा एक फोटो तुम्ही मला पाठवू शकता. मी एसएमएसने लिंक पाठवू का?",
    },
    "back": {
        "en": "This is Haqdaar. I looked at your photo.",
        "hi": "यह हक़दार है। मैंने आपकी फ़ोटो देखी।",
        "mr": "हे हक्कदार आहे. मी तुमचा फोटो पाहिला.",
    },
    "bad": {
        "en": "This is Haqdaar. I could not see your photo well. Please send it again: in daylight, close, and steady. "
              "The same link works.",
        "hi": "यह हक़दार है। मुझे आपकी फ़ोटो ठीक से नहीं दिखी। कृपया फिर से भेजिए: दिन की रोशनी में, पास से, और हाथ "
              "स्थिर रखकर। वही लिंक चलेगा।",
        "mr": "हे हक्कदार आहे. मला तुमचा फोटो नीट दिसला नाही. कृपया पुन्हा पाठवा: दिवसाच्या उजेडात, जवळून आणि हात "
              "स्थिर ठेवून. तीच लिंक चालेल.",
    },
    "bye": {   # Step 2: said when the call ends after the link. The Hindi and Marathi are not checked by a speaker.
        "en": "I have sent a link by SMS. Send the photo. I will call you back.",
        "hi": "मैंने एसएमएस से एक लिंक भेज दिया है। फ़ोटो भेज दीजिए। मैं आपको वापस फ़ोन करूँगी।",
        "mr": "मी एसएमएसने एक लिंक पाठवली आहे. फोटो पाठवा. मी तुम्हाला परत फोन करेन.",
    },
}

# 1.8 (B): fixed true lines about the line itself, said by code with no model call. The Hindi and Marathi
# are not checked by a speaker. None of them is an answer: they leave last_say alone.
TRUST = {
    "free": {
        "en": "This call is free of charge from our side, and I never ask for money. The schemes are from the government.",
        "hi": "हमारी तरफ़ से यह कॉल मुफ़्त है, और मैं कभी पैसे नहीं माँगती। योजनाएँ सरकार की हैं।",
        "mr": "आमच्या बाजूने हा कॉल मोफत आहे, आणि मी कधीही पैसे मागत नाही. योजना सरकारच्या आहेत.",
    },
    "government": {
        "en": "No. I am Haqdaar, a helper that tells you about government schemes. I am not a government office.",
        "hi": "नहीं। मैं हक़दार हूँ, एक सहायक जो आपको सरकारी योजनाओं के बारे में बताती है। मैं कोई सरकारी दफ़्तर नहीं हूँ।",
        "mr": "नाही. मी हक्कदार आहे, सरकारी योजनांबद्दल सांगणारी एक मदतनीस. मी सरकारी कार्यालय नाही.",
    },
    "person": {
        "en": "I am a computer voice, not a person.",
        "hi": "मैं एक कंप्यूटर की आवाज़ हूँ, कोई इंसान नहीं।",
        "mr": "मी संगणकाचा आवाज आहे, माणूस नाही.",
    },
    "to_person": {
        "en": "There is no person on this line now. I can tell you where to go for the scheme.",
        "hi": "इस लाइन पर अभी कोई इंसान नहीं है। योजना के लिए कहाँ जाना है, यह मैं बता सकती हूँ।",
        "mr": "या लाईनवर आत्ता कोणीही माणूस नाही. योजनेसाठी कुठे जायचे ते मी सांगू शकते.",
    },
}
CANNOT = {
    "form": {
        "en": "I can not fill a form or see your payment from here. For that, go to the office or the centre named for "
              "the scheme; I can tell you which papers to take.",
        "hi": "मैं यहाँ से फ़ॉर्म नहीं भर सकती और आपका भुगतान नहीं देख सकती। उसके लिए योजना में बताए दफ़्तर या केंद्र पर "
              "जाइए; कौन से कागज़ ले जाने हैं, यह मैं बता सकती हूँ।",
        "mr": "मी इथून फॉर्म भरू शकत नाही आणि तुमचे पेमेंट पाहू शकत नाही. त्यासाठी योजनेत सांगितलेल्या कार्यालयात किंवा "
              "केंद्रात जा; कोणती कागदपत्रे न्यायची ते मी सांगू शकते.",
    },
    "sms": {
        "en": "I can not send the details by SMS. I can say them again slowly.",
        "hi": "मैं विवरण एसएमएस से नहीं भेज सकती। मैं उन्हें धीरे-धीरे फिर से बोल सकती हूँ।",
        "mr": "मी तपशील एसएमएसने पाठवू शकत नाही. मी ते हळूहळू पुन्हा सांगू शकते.",
    },
}
CANNOT["payment"] = CANNOT["form"]
NUMBER = {
    "en": "Please do not tell me that number. I do not need your Aadhaar, bank or OTP number, and you should not tell "
          "it to anyone on the phone.",
    "hi": "कृपया वह नंबर मुझे मत बताइए। मुझे आपका आधार, बैंक या ओटीपी नंबर नहीं चाहिए, और फ़ोन पर यह किसी को "
          "भी न बताइए।",
    "mr": "कृपया तो नंबर मला सांगू नका. मला तुमचा आधार, बँक किंवा ओटीपी नंबर नको आहे, आणि फोनवर तो कोणालाही सांगू नका.",
}
DISTRESS = {
    "en": "I am sorry to hear that. I am here, and we can take this slowly.",
    "hi": "यह सुनकर मुझे दुख हुआ। मैं यहीं हूँ, और हम आराम से बात कर सकते हैं।",
    "mr": "हे ऐकून मला वाईट वाटले. मी इथेच आहे, आणि आपण निवांत बोलू शकतो.",
}
OFF_TOPIC_END = {
    "en": "I can only help with government schemes. Thank you for calling.",
    "hi": "मैं सिर्फ़ सरकारी योजनाओं में मदद कर सकती हूँ। कॉल करने के लिए धन्यवाद।",
    "mr": "मी फक्त सरकारी योजनांमध्ये मदत करू शकते. कॉल केल्याबद्दल धन्यवाद.",
}
THANKS = {
    "en": "You are welcome. Anything else?",
    "hi": "आपका स्वागत है। और कुछ?",
    "mr": "आपले स्वागत आहे. आणखी काही?",
}
PACE = {
    "slow": {
        "en": "All right, I will speak slowly.",
        "hi": "ठीक है, मैं धीरे बोलूँगी।",
        "mr": "ठीक आहे, मी हळू बोलेन.",
    },
    "normal": {
        "en": "All right, I will speak at the normal speed.",
        "hi": "ठीक है, मैं सामान्य गति से बोलूँगी।",
        "mr": "ठीक आहे, मी नेहमीच्या गतीने बोलेन.",
    },
}

# 1.8: a line added to the NOTE of the one turn that needs it (never to the fixed prompt).
FOLLOW = {
    "move": "The caller means [{sid}], a scheme you named before. Answer about it.",
    "other": "The caller wants a scheme not named yet. Name only: {left}. Do not name a scheme from before.",
    "other_none": "Every scheme found was already named. Say so plainly in one sentence, then ask if they want "
                  "any of them told again. Do not name one as new.",
    "side": "The caller compares [{a}] and [{b}]. One sentence for each, with the number from SCHEMES. Never say "
            "which one is better for the caller.",
    "will_ask": "The caller asks if they will get [{sid}]. Promise nothing. Say in one sentence who it is for, "
                "then ask NEXT QUESTION.",
    "will_known": "The caller asks if they will get [{sid}]. Promise nothing. Say \"it is for (who it is for); you "
                  "told me (what the caller said)\" in two short sentences.",
    "simpler": 'The caller did not understand. Use action "simpler": your last point in simpler, shorter words.',
    "how_much": "The caller asks how much you said. Say only the sentence with the number, nothing else.",
    "recap": "First say back, in ONE short sentence, what the caller told you: {facts}. Then give the answer to "
             "their problem in the same reply. Do not ask \"is that right?\" and do not ask a new question in this reply.",
    "distress": "The caller is in pain and a kind sentence was already said. Ask no list of questions. At most one "
                "gentle question, or the schemes if the caller asked. Say no help-line number.",
}

NOT_SURE = {
    "en": "I am not sure about that. Please ask me again in other words.",
    "hi": "मुझे इसकी पक्की जानकारी नहीं है। कृपया दूसरे शब्दों में फिर से पूछिए।",
    "mr": "मला याची खात्री नाही. कृपया दुसऱ्या शब्दांत पुन्हा विचारा.",
}

# 1.3b: fixed words said by code (never by the model).
NOT_HELD_SAY = {
    "en": "I do not have that one yet.",
    "hi": "यह योजना मेरे पास अभी नहीं है।",
    "mr": "ती योजना माझ्याकडे अजून नाही.",
    # gu / ta: written by the model, not yet checked by a native speaker.
    "gu": "એ યોજના મારી પાસે હજી નથી.",
    "ta": "அந்தத் திட்டம் என்னிடம் இன்னும் இல்லை.",
}
HELP_WITH = {
    "en": "I can help with {kinds}.",
    "hi": "मैं इनमें मदद कर सकती हूँ: {kinds}।",
    "mr": "मी यामध्ये मदत करू शकते: {kinds}.",
    "gu": "હું આમાં મદદ કરી શકું છું: {kinds}.",
    "ta": "இவற்றில் நான் உதவ முடியும்: {kinds}.",
}
ALSO_ASKED = {
    "en": "You also asked about {kind}.",
    "hi": "आपने {kind} के बारे में भी पूछा था।",
    "mr": "तुम्ही {kind} बद्दलही विचारले होते.",
}


def kind_say(value: Any, lang: str) -> str:
    """The everyday words for a kind of help, in the caller's language."""
    label = (vocab.LABELS.get(value) or {}).get(lang) or (vocab.LABELS.get(value) or {}).get("en")
    return str(label or value)


def not_held_say(lang: str, kinds: list[str]) -> str:
    """1.3b (P2.2): "I do not have that one yet", then the kinds of help the
    line does have. No questions, no schemes that do not fit."""
    kinds_said = ", ".join(kind_say(k, lang) for k in kinds)
    return (NOT_HELD_SAY.get(lang, NOT_HELD_SAY["en"]) + " "
            + HELP_WITH.get(lang, HELP_WITH["en"]).format(kinds=kinds_said))


def _named(value: Any, lang: str) -> str:
    """The code (for "facts") and the words to SAY for it in the caller's language."""
    label = (vocab.LABELS.get(value) or {}).get(lang) or (vocab.LABELS.get(value) or {}).get("en")
    return f"{value} (say: {label})" if label and str(label).lower() != str(value).lower() else str(value)


def build(lang: str, log_text: str, known: Mapping[str, Any], boxes: Mapping[str, Sequence[str]],
          ask: str | None, order: Sequence[str], schemes: Sequence[tuple[str, str, str]],
          words: str, note: str = "", focus: str = "", told: Sequence[str] = (), first_call: str = "",
          photo: str = "") -> list[dict[str, str]]:
    """schemes = (scheme id, mark, English card text), best first. `focus` = the scheme the talk
    is about now, `told` = the PARTS of it already said in this call."""
    box_lines = "\n".join(
        f"- {box}: " + ("a number of years" if box == "age" else ", ".join(_named(v, lang) for v in values))
        for box, values in boxes.items() if values
    )
    if ask:
        like = (QUESTION.get(ask) or {}).get(lang)
        nxt = f"{ask}" + (f'  (ask it like: "{like}")' if like else "") + (f"  (if the caller just told you that, ask the next of: {', '.join(order)})"
                          if len(order) > 1 else "")
    else:
        nxt = "none"
    cards = "\n\n".join(f"{text}\nmark: {mark}" for _sid, mark, text in schemes) or "(none found)"
    if focus:
        in_talk = (f"[{focus}]. TOLD: {', '.join(p for p in PARTS if p in told) or 'nothing'}. "
                   f"NOT TOLD YET: {', '.join(p for p in PARTS if p not in told) or 'nothing'}.")
    else:
        in_talk = "none yet"
    user = (
        f"BOXES (allowed values):\n{box_lines}\n\n"
        f"KNOWN ABOUT THE CALLER: {'; '.join(f'{k} = {v}' for k, v in known.items()) or 'nothing yet'}\n\n"
        f"NEXT QUESTION: {nxt}\n\n"
        f"SCHEMES (found for the caller's words; the mark says if it fits what we know):\n{cards}\n\n"
        f"SCHEME IN TALK: {in_talk}\n\n"
        + (f"THE FIRST CALL, said by the caller and the line before the photo (do not ask again what is answered here):\n{first_call}\n\n" if first_call else "")
        + (f"WHAT THE PHOTO SHOWS (read by a machine from the photo the caller sent; the caller did not say this):\n{photo}\n\n" if photo else "")
        + f"CALL LOG (oldest first):\n{log_text or '(empty)'}\n\n"
        f"NEWEST CALLER WORDS: \"{words}\"\n"
    )
    if note:
        user += f"\nNOTE: {note}\n"
    user += "\nReply with the JSON object."
    return [
        {"role": "system", "content": SYSTEM.replace("{lang}", LANG_NAMES.get(lang, lang))},
        {"role": "user", "content": user},
    ]
