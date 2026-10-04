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

ACTIONS = ("answer", "ask", "show_scheme", "repeat", "goodbye", "not_for_me", "other_topic")

SYSTEM = """You are Haqdaar, a helper on a phone call in India. You help the caller find Indian government \
welfare schemes and answer questions about them. You talk like a kind, plain-spoken person. You know nothing \
about the caller until the caller says it.

Reply with ONE JSON object and nothing else:
{"action": "...", "say": "...", "facts": {}, "scheme": "", "ask_box": ""}

action is one of:
- "answer": the caller asked something about a scheme, or about what you do. Answer it from SCHEMES only.
- "ask": you need to know more. Two kinds:
    (a) a question about the caller: you may ask ONLY the box named in NEXT QUESTION. Put that box name in \
"ask_box". Ask it in natural spoken words and offer at most five of the choices, in everyday words \
(use the "say:" words given in BOXES, never the code names like business_loans or male). Never make up your own question about the caller. If NEXT QUESTION is "none", do not ask about the caller at all.
    (b) the caller's words themselves were not understood (broken or unclear words): leave "ask_box" empty \
and ask them, in a normal way, to say what they need.
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

facts: what the caller told you about themselves in the NEWEST CALLER WORDS only. Never guess. Keys are box \
names from BOXES, values must be one of that box's allowed values, written exactly. For "age" give the age in \
years as a number. "category" is the kind of help the caller wants: fill it whenever the need is clear from \
their words (a loan for a shop or cart = business_loans, crops = farming). If the caller told you nothing new, \
use {}. Fill facts in every action where the caller said some.

scheme: for "answer" and "show_scheme", the id (the name in square brackets) of the scheme your reply is about.

Rules for "say":
- Write it in {lang}, in simple everyday spoken words. No lists, no brackets, no bullet points, no markdown, \
no emoji, no letters of any other language.
- 1 or 2 short sentences. Up to 4 short sentences only when the caller asks for detail (papers needed, how to \
apply, steps). This is a phone call: every sentence must be under 18 words. For how to apply, give only the \
first two or three steps in short sentences; do not read out web addresses.
- Talk about ONE scheme in an "answer": the first scheme in SCHEMES, unless the caller names another.
- Every number you say must be written in SCHEMES. Write numbers as digits, exactly as in SCHEMES.
- Never tell the caller they are eligible, will get, can get, or can apply for a scheme. Do not write "you can \
apply", "you are eligible", "you will get". Say who the scheme is for and what it gives; for how to apply, \
start with "To apply, ...". A scheme marked "does not fit" must not be offered; if the caller asks about it, say who it is for.
- If a straight question about a scheme and a question to ask both stand, answer first.
- A box shown as UNKNOWN in KNOWN ABOUT THE CALLER was asked and not answered: do not ask it again.
- Never ask for something that KNOWN ABOUT THE CALLER already holds.
- If the answer is not in SCHEMES, say you do not have that information.
- If the caller says the same need again, do not say the same sentences again: name the OTHER schemes in \
SCHEMES, or ask which one they want to hear more about.
- Start with a short first sentence.

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

OTHER_TOPIC = {
    "en": "I can only help with government schemes. Tell me what help you need.",
    "hi": "मैं सिर्फ़ सरकारी योजनाओं के बारे में बता सकती हूँ। बताइए, आपको किस बात में मदद चाहिए।",
    "mr": "मी फक्त सरकारी योजनांबद्दल सांगू शकते. तुम्हाला कशात मदत हवी आहे ते सांगा.",
}

NOT_SURE = {
    "en": "I am not sure about that. Please ask me again in other words.",
    "hi": "मुझे इसकी पक्की जानकारी नहीं है। कृपया दूसरे शब्दों में फिर से पूछिए।",
    "mr": "मला याची खात्री नाही. कृपया दुसऱ्या शब्दांत पुन्हा विचारा.",
}


def _named(value: Any, lang: str) -> str:
    """The code (for "facts") and the words to SAY for it in the caller's language."""
    label = (vocab.LABELS.get(value) or {}).get(lang) or (vocab.LABELS.get(value) or {}).get("en")
    return f"{value} (say: {label})" if label and str(label).lower() != str(value).lower() else str(value)


def build(lang: str, log_text: str, known: Mapping[str, Any], boxes: Mapping[str, Sequence[str]],
          ask: str | None, order: Sequence[str], schemes: Sequence[tuple[str, str, str]],
          words: str, note: str = "") -> list[dict[str, str]]:
    """schemes = (scheme id, mark, English card text), best first."""
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
    user = (
        f"BOXES (allowed values):\n{box_lines}\n\n"
        f"KNOWN ABOUT THE CALLER: {'; '.join(f'{k} = {v}' for k, v in known.items()) or 'nothing yet'}\n\n"
        f"NEXT QUESTION: {nxt}\n\n"
        f"SCHEMES (found for the caller's words; the mark says if it fits what we know):\n{cards}\n\n"
        f"CALL LOG (oldest first):\n{log_text or '(empty)'}\n\n"
        f"NEWEST CALLER WORDS: \"{words}\"\n"
    )
    if note:
        user += f"\nNOTE: {note}\n"
    user += "\nReply with the JSON object."
    return [
        {"role": "system", "content": SYSTEM.replace("{lang}", LANG_NAMES.get(lang, lang))},
        {"role": "user", "content": user},
    ]
