"""Writes the three Haqdaar call-flow charts as Excalidraw files, and checks them.

    python3 flow/build_flows.py            # write + check
    python3 flow/build_flows.py <folder>   # also write a plain picture (.svg) of each there

Chart 1: the owner's flow, loops closed, edge cases.   (black = his boxes, orange = added)
Chart 2: chart 1 + cut-in (barge-in).                  (blue)
Chart 3: chart 2 + keys.                               (green)
Boxes keep the same place in all three.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flowlib import Chart, check_file  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

XA, XR = 820, 1500            # two columns right of the main one
XL, XN = -1250, -600          # search + log column, "not for us" column
G_LOOP, G_NFM, G_CUT = -1700, -1620, 1840    # empty lanes the long loop lines run in
K1, K3 = -2650, -2050         # keys columns
KG1, KG2 = -2980, -3200       # keys loop lanes

NAMES = {
    1: ("1-talk-flow", "HAQDAAR call flow, chart 1 of 3: your flow, loops closed, edge cases added"),
    2: ("2-talk-flow-barge-in", "HAQDAAR call flow, chart 2 of 3: chart 1 + cut-in (barge-in)"),
    3: ("3-talk-flow-with-keys", "HAQDAAR call flow, chart 3 of 3: talk + cut-in + keys"),
}


def build(level):
    c = Chart(NAMES[level][1])
    n, a = c.node, c.arrow

    # ---------------- the top: call, trial line, greeting ----------------
    start = n("start", "Call comes in from my phone number", 0, top=0, w=420, kind="start")
    twilio = n("twilio", "Twilio free-trial line plays. The caller presses any key to clear it. "
               "It can not be switched off on a trial account.", 0, top=start.bottom + 100, w=520)
    greet = n("greet", "GREETING, short\nIn Hindi, English, Marathi, Gujarati and Tamil, each says: \"Welcome to "
              "Haqdaar. Speak in English or your own language. For keys, press 6.\"",
              0, top=twilio.bottom + 80, w=520)
    speaks = n("speaks", "Speaks?", 0, top=greet.bottom + 80, kind="diamond", w=200)
    row_a = speaks.cy + 170
    listen = n("listen", "LISTEN\nWait for them to speak in their own language. Sarvam finds the "
               "language by itself, on every turn. It can be mixed, and it can be a language "
               "outside the greeting.", 0, top=row_a + 130, w=520)
    heard = n("heard", "Real words heard?", 0, top=listen.bottom + 70, kind="diamond", w=240,
              layer="add")
    lang = n("lang", "Reply language = the language Sarvam heard on this turn. Not sure (very few "
             "words): keep the last one. A language the voice can not speak: reply in Hindi and "
             "say so once.", 0, top=heard.bottom + 70, w=520, layer="add")
    question = n("question", "a question?", 0, top=lang.bottom + 70, w=220)

    n("tw_note", "No key pressed: Twilio ends the call by itself. A paid Twilio account has no "
      "such line.", -820, cy=twilio.cy, w=380, kind="note", layer="add")
    n("greet_note", "For now Hindi, English, Marathi + 2 more of Mumbai and Maharashtra: "
      "Gujarati, Tamil (a setting). Later: picked from the place of the caller's number.", -820, cy=greet.cy, w=380,
      kind="note", layer="add")

    a("start", "b", "twilio", "t", layer="base", label="6296399690")
    a("twilio", "b", "greet", "t", layer="base")
    a("greet", "b", "speaks", "t", layer="base")
    a("speaks", "b", "listen", "t", layer="base",
      label="Yes (words said at the greeting are kept: they are turn 1)", lab=(0, 0.3, 0, 0), lw=270)

    # quiet at the greeting (his loop, with a count so it ends)
    q1 = n("q1", "2nd time quiet?", XA, cy=speaks.cy, kind="diamond", w=200, layer="add")
    n("say_again", "Says the same thing again", XR, cy=speaks.cy, w=340)
    n("bye_q", "Says goodbye", XA, cy=row_a, w=260, layer="add")
    n("end_q", "Call disconnected", XR, cy=row_a, w=340, kind="end")
    a("speaks", "r", "q1", "l", layer="base", label="No: waits 30 sec, no words (a noise is not words)",
      lw=250)
    a("q1", "r", "say_again", "l", label="no, 1st time")
    a("q1", "b", "bye_q", "t", label="yes: 30 sec wait, twice")
    a("say_again", "t", "greet", "r", layer="base", label="the greeting plays once more",
      lab=(1, 0.5, 0, 0))
    a("bye_q", "r", "end_q", "l")

    keys_kind = "box" if level == 3 else "link"
    n("keys", "KEYS MODE starts" if level == 3 else "KEYS MODE (chart 3)", -820, cy=speaks.cy,
      w=300, kind=keys_kind, layer="keys")
    a("speaks", "l", "keys", "r", layer="base", label="presses 6")

    # quiet in the middle of the talk
    n("remind", "Says \"We are waiting for your reply\" and the last question again", XA,
      cy=listen.cy, w=400, layer="add")
    n("q2", "2nd quiet wait in a row?", XA, cy=heard.cy, kind="diamond", w=170, layer="add")
    n("bye2", "Says goodbye", XR, cy=heard.cy, w=260, layer="add")
    a("listen", "b", "heard", "t")
    a("heard", "r", "q2", "l", label="no: 30 s of quiet, only noise, or speech-to-text failed", lw=250)
    a("heard", "b", "lang", "t", label="yes")
    a("q2", "t", "remind", "b", label="no, 1st")
    a("remind", "l", "listen", "r")
    a("q2", "r", "bye2", "l", label="yes")
    a("bye2", "t", "end_q", "b")
    a("lang", "b", "question", "t")

    # ---------------- the three kinds of turn ----------------
    cat_top = question.bottom + 110
    cat1 = n("cat1", "A SITUATION\ne.g. \"my health is bad\", \"my crops died\". Understand the "
             "situation, put the facts together, find the schemes that help, and guide them on "
             "what to do, from the system's own info.", -560, top=cat_top, w=440)
    n("cat2", "A SCHEME NAME", 0, top=cat_top, w=300)
    n("cat3", "Could be off-topic. Handled by the AI itself.", 560, top=cat_top, w=380)
    a("question", "l", "cat1", "t", layer="base", label="category 1", lab=(0, 0.6, 0, 0))
    a("question", "b", "cat2", "t", layer="base", label="category 2")
    a("question", "r", "cat3", "t", layer="base", label="category 3", lab=(0, 0.6, 0, 0))
    n("people", "HOW PEOPLE REALLY TALK (plan 1.3 and 1.8)\n- \"no no, just tell me the scheme\": stop "
      "asking, show the 2 best, say what the pick is based on\n- \"I do not know\" / \"I will not "
      "say\": never asked again\n- \"I am NOT a farmer\": the word \"not\" is read\n- \"for my "
      "mother\": the questions are about her\n- a short name (\"PM Kisan\", \"MNREGA\") is a scheme "
      "name\n- a scheme we do not hold: \"I do not have that one yet\"\n- two needs at once: one, "
      "then the other\n- \"the second one\", \"any other?\": from a list the code keeps\n- \"will "
      "I get it?\": no promise; who it is for, then the ONE thing not known\n- \"did not "
      "understand\": simpler words, not the same ones\n- \"one minute\": waits up to 2 min\n- is it "
      "free, are you a person: true fixed lines\n- distress: one kind sentence FIRST, "
      "never a list of questions\n- never takes an Aadhaar, bank or OTP number", 2300, top=cat_top - 60,
      w=460, kind="note", layer="add", align="left")

    # ---------------- the model, search, log ----------------
    llm = n("llm", "THE MODEL (LLM)\nReads the system prompt, the log and this turn. Decides the "
            "next step:\n1. ask a clarifying question (which one: the fixed picker says, see 5)\n2. do a search (RAG)\n3. give the answer to "
            "the caller's question (each kind of question has its own way of output)\n4. more, as "
            "needed: say the last reply again, say goodbye, or \"not for us\"\n5. find schemes by "
            "keyword bits (bitmask); the bits also pick the next question", 0, top=cat1.bottom + 120, w=560, align="left")
    a("cat1", "b", "llm", ("t", 0.15), via=[("y", cat1.bottom + 60)], layer="base")
    c.note("a situation: clarify first, then schemes", -800, cat1.bottom + 40, layer="add", fs=16, w=330)
    a("cat2", "b", "llm", "t", layer="base")
    a("cat3", "b", "llm", ("r", 0.1), layer="base")

    rag = n("rag", "RAG SYSTEM\n- top 5 chunks\n- vector search, always in English\n- chunks cut "
            "by part: summary, benefits, how to apply, details. Not by size, not at random.\n"
            "- more than one query for one need, then ranking, to get the best chunks\n- plain "
            "name search too, for safety", XL, top=llm.top - 110, w=460, align="left")
    log = n("log", "LLM NOTEBOOK or LOG\nEverything decided, pressed or said is logged, in order, "
            "so the model has context. Needs the best system prompt to handle clashes and all.",
            XL, top=rag.bottom + 90, w=460)
    y_out, y_back = llm.top + 45, llm.top + 115
    a("llm", ("l", (y_out - llm.top) / llm.h), "rag", ("r", (y_out - rag.top) / rag.h),
      layer="base", label="if rag", lab=(0, 0.3, 0, 0))
    a("rag", ("r", (y_back - rag.top) / rag.h), "llm", ("l", (y_back - llm.top) / llm.h),
      label="top 5 chunks back, or \"nothing found\" (at most 2 searches a turn)", lab=(0, 0.42, 0, 0),
      lw=330)
    a("rag", "b", "log", "t", layer="base")
    a("llm", ("l", 0.85), "log", ("r", 0.35), via=[("x", -700)], layer="base", both=True,
      label="reads it each turn, writes each choice", lab=(2, 0.5, 0, 28), lw=300)

    bits = n("bits", "KEYWORD BITS + QUESTION PICKER\n(fixed code, no model)\nWords like farmer, widow, "
             "60+, a state name set bits. Schemes that do not fit are dropped. Many still fit: "
             "minimax picks the ONE question whose worst answer leaves the fewest schemes.",
             XA, cy=llm.fy(0.40), w=420, layer="add")
    y1, y2 = bits.cy - 32, bits.cy + 32
    a("llm", ("r", (y1 - llm.top) / llm.h), "bits", ("l", (y1 - bits.top) / bits.h),
      label="5. keyword bits")
    a("bits", ("l", (y2 - bits.top) / bits.h), "llm", ("r", (y2 - llm.top) / llm.h),
      label="short list + the next question", lab=(0, 0.5, 0, 22))

    fail = n("fail", "MODEL OR VOICE FAILS\nModel: the 2nd key, then the next model. Voice: one "
             "more try. Still nothing: a recorded line, \"Sorry, please call again.\"",
             XR, cy=llm.fy(0.9), w=400, layer="add")
    n("end_fail", "Call ends. Log saved.", XR, top=fail.bottom + 70, w=300, kind="end")
    a("llm", ("r", 0.9), "fail", "l", label="no reply in time", lab=(0, 0.72, 0, 0))
    a("fail", "b", "end_fail", "t")

    # ---------------- the output ----------------
    truth = n("truth", "TRUTH CHECK, before anything is said\nEvery number and name must be in "
              "the scheme text. Short sentences. No promise like \"you will get it\". Failed "
              "twice: says \"I am not sure about that\".", 0, top=llm.bottom + 110, w=440,
              layer="add")
    convert = n("convert", "If an output: Sarvam converts it from English to the caller's "
                "language, and into voice.", 0, top=truth.bottom + 80, w=440)
    limits = n("limits", "RULES AND LIMITS\n- a situation or a loose remark: ask first, one question at a time, "
      "at most 3, then show schemes\n- a named scheme or a straight question: answer first\n"
      "- at most 2 searches in one turn\n- 3 "
      "clarifying questions in a row with no usable reply: \"Press 6 to use keys\"\n- 2 quiet "
      "waits in a row: goodbye\n- nothing ready 1.6 s after the caller stops: says \"one moment\"\n"
      "- 40 turns or 10 minutes: a polite goodbye\n- \"just tell me\" always wins over a question\n"
      "- off topic 3 times in a row: a polite goodbye\n- \"thanks\" is not goodbye: \"anything else?\" once",
      XA, top=truth.top, w=420, kind="note",
      layer="add", align="left")
    hear_top = max(convert.bottom + 110, log.bottom + 30, limits.bottom + 100)
    hear = n("hear", "User hears the output", 0, top=hear_top, w=440)
    r0 = hear.cy
    r1, r2, r3 = r0 + 200, r0 + 420, r0 + 640
    a("llm", "b", "truth", "t", layer="base", label="if an output: a question, an answer, a goodbye",
      lab=(0, 0.5, -150, 0), lw=250)
    a("truth", "r", "llm", ("b", 0.88), via=[("x", 340), ("y", llm.bottom + 45)],
      label="fails: back to the model once, with the reason", lab=(1, 0.45, 0, 0), lw=220)
    a("truth", "b", "convert", "t", label="passes")
    a("convert", "b", "hear", "t", layer="base")


    n("nfm", "NOT FOR US (side talk, half words): says nothing", XN, cy=r0, w=400, layer="add")
    a("llm", ("l", 0.95), "nfm", ("t", 0.875), via=[("x", -450)], label="\"not for us\"",
      lab=(1, 0.5, 0, 0))
    a("nfm", "l", "listen", ("l", 0.7), via=[("x", G_NFM), ("y", listen.fy(0.7))],
      label="keeps listening", lab=(0, 0.5, 0, 0))

    n("bye", "Was that the goodbye?", 0, cy=r2, kind="diamond", w=240, layer="add")
    n("end_call", "Call ends. The log is closed and saved.", 0, cy=r3, w=440, kind="end")
    n("hangup", "ANY TIME: the caller hangs up", XN, cy=r3, w=360, kind="event", layer="add")
    a("hear", "b", "bye", "t")
    a("bye", "b", "end_call", "t", label="yes")
    a("bye", "l", "listen", ("l", 0.3), via=[("x", G_LOOP), ("y", listen.fy(0.3))],
      label="no: THE LOOP. Back to LISTEN for the next thing the caller says.", lab=(0, 0.45, 0, 0),
      lw=520)
    a("hangup", "r", "end_call", "l")

    # ---------------- title ----------------
    c.note(c.title, 1250, start.top + 10, layer="base", fs=28, w=760)
    c.note("black = your own boxes, in your places", 1250, start.top + 100, layer="base", fs=18, w=700)
    c.note("orange = added: loops closed, edge cases", 1250, start.top + 130, layer="add", fs=18, w=700)
    c.note("red = the call ends", 1250, start.top + 160, layer="end", fs=18, w=700)
    if level >= 2:
        c.note("blue = cut-in (barge-in)", 1250, start.top + 190, layer="barge", fs=18, w=700)
    if level >= 3:
        c.note("green = keys", 1250, start.top + 220, layer="keys", fs=18, w=700)

    if level >= 2:
        barge(c, greet, hear, lang, r0, r1, r2, r3)
    if level >= 3:
        keys(c, greet, speaks, listen, row_a)
    return c


def barge(c, greet, hear, lang, r0, r1, r2, r3):
    """Cut-in: the ear stays on while the agent talks."""
    n, a = c.node, c.arrow
    B = "barge"
    n("b_voice", "A real voice for 0.6 s?", XA, cy=r0, kind="diamond", w=240, layer=B)
    n("b_pause", "PAUSE the voice at once. Keep the cut sentence and the ones after it.",
      XR, cy=r0, w=400, layer=B)
    n("b_listen", "Listen till the caller stops. Sarvam gives the words and the language.",
      XR, cy=r1, w=400, layer=B)
    n("b_words", "2 or more real words?", XR, cy=r2, kind="diamond", w=240, layer=B)
    n("b_resume", "GO ON: says the cut sentence again from its start, then the rest. No "
      "\"sorry\". 2 false stops in one reply: the ear is off till that reply ends.",
      XA, cy=r1, w=420, layer=B)
    n("b_log", "CALLER'S TURN\nLog: the caller cut in, which sentence was cut, what was not "
      "heard. The rest of the old reply is dropped.", XR, cy=r3, w=400, layer=B)
    a("hear", "r", "b_voice", "l", layer=B, label="a sound while the agent talks", lw=200)
    a("b_voice", "t", "hear", ("t", 0.93), via=[("y", hear.top - 40)], layer=B,
      label="no (cough, TV, horn, hiss): keeps talking, nothing stops", lab=(1, 0.42, 0, 0), lw=420)
    a("b_voice", "r", "b_pause", "l", layer=B, label="yes")
    a("b_pause", "b", "b_listen", "t", layer=B)
    a("b_listen", "b", "b_words", "t", layer=B)
    a("b_words", "l", "b_resume", "b", layer=B, label="no (\"hmm\", \"ok\", \"haan\")",
      lab=(0, 0.45, 0, 0))
    a("b_resume", "l", "hear", ("b", 0.93), layer=B)
    a("b_words", "b", "b_log", "t", layer=B, label="yes")
    a("b_log", "r", "lang", "r", via=[("x", G_CUT), ("y", lang.cy)], layer=B,
      label="the words go in as a new turn, marked \"cut-in\" for the model", lab=(2, 0.25, 0, 0),
      lw=330)
    a("nfm", "r", "hear", "l", layer=B, label="after a cut-in: goes on from the cut sentence",
      lab=(0, 0.5, 0, 52), lw=165)
    n("b_rules", "CUT-IN RULES\n- the ear is on from the first sound of each reply\n- \"one "
      "moment\" is never cut\n- in talk mode a key does not stop the voice (6 = keys, chart 3)\n"
      "- speakerphone: the agent's own voice must not count as the caller; the 2-false-stops "
      "rule ends it if it does\n- \"say it again\" after a cut-in starts from the cut sentence",
      2330, cy=r1, w=440, kind="note", layer=B, align="left")
    n("b_greet", "CUT-IN AT THE GREETING, the same gate: real words stop the greeting and are "
      "taken as turn 1. Key 6 stops it and goes to keys.", -1420, cy=greet.cy, w=420,
      kind="note", layer=B)


def keys(c, greet, speaks, listen, row_a):
    """Keys: a fixed path, no model. Same log and same bits as the talk path."""
    n, a = c.node, c.arrow
    K = "keys"
    n("ev_six", "ANY TIME in talk: the caller presses 6, or 3 clarifying questions in a row "
      "got no usable reply", -820, cy=row_a + 10, w=400, kind="event", layer=K)
    a("ev_six", "t", "keys", "b", layer=K)
    k_lang = n("k_lang", "LANGUAGE BY KEY\n1 Hindi, 2 English, 3 to 5 the three local languages. "
               "Skipped when the talk has already set the language.", K1, cy=speaks.cy, w=440,
               layer=K)
    a("keys", "l", "k_lang", "r", layer=K)
    k_ask = n("k_ask", "ASK ONE THING, with its key list\nFirst the kind of need (farming, "
              "health, pension ...). Then the question picker names the box that cuts the list "
              "most: gender, social group, age, income, work, state.\n1 to 9 = a choice, 0 = I do "
              "not know", K1, top=k_lang.bottom + 80, w=440, layer=K)
    k_in = n("k_in", "A key on the list?", K1, top=k_ask.bottom + 70, kind="diamond", w=240, layer=K)
    k_bits = n("k_bits", "KEYWORD BITS (the same bitmask as the talk path): the answer sets a "
               "bit, schemes that do not fit are dropped. The key and what it meant go in the "
               "same log.", K1, top=k_in.bottom + 80, w=440, layer=K)
    k_few = n("k_few", "4 or fewer schemes left, or 6 questions asked?", K1, top=k_bits.bottom + 70,
              kind="diamond", w=250, layer=K)
    k_read = n("k_read", "READ ONE SCHEME: its name and a short summary. Then the menu:\n"
               "1 what you get, 2 how to apply, 3 papers, 4 who can apply, 9 next scheme, 0 stop",
               K1, top=k_few.bottom + 80, w=440, layer=K)
    k_menu = n("k_menu", "Which key?", K1, top=k_read.bottom + 70, kind="diamond", w=200, layer=K)
    k_else = n("k_else", "Anything else? 1 = yes, 2 = no", K1, top=k_menu.bottom + 90,
               kind="diamond", w=200, layer=K)
    k_bye = n("k_bye", "Says goodbye", K1, top=k_else.bottom + 80, w=260, layer=K)
    n("k_end", "Call disconnected", K1, top=k_bye.bottom + 70, w=340, kind="end")

    k_miss3 = n("k_miss3", "3 wrong keys or 2 quiet waits in a row?", K3, cy=k_in.cy,
                kind="diamond", w=215, layer=K)
    n("k_miss", "Says the list again (after a quiet 30 s: \"we are waiting\" first)", K3,
      cy=k_ask.cy, w=380, layer=K)
    k_bye_m = n("k_bye_m", "Says goodbye", K3, top=k_miss3.bottom + 60, w=260, layer=K)
    n("k_end_m", "Call disconnected", K3, top=k_bye_m.bottom + 60, w=300, kind="end")
    n("k_part", "Reads that part of the scheme (recorded clips)", K3, cy=k_menu.cy, w=380, layer=K)

    a("k_lang", "b", "k_ask", "t", layer=K)
    a("k_ask", "b", "k_in", "t", layer=K)
    a("k_in", "b", "k_bits", "t", layer=K, label="yes")
    a("k_in", "r", "k_miss3", "l", layer=K, label="no, or quiet", lab=(0, 0.5, 0, 0), lw=140)
    a("k_miss3", "t", "k_miss", "b", layer=K, label="no")
    a("k_miss", "l", "k_ask", "r", layer=K)
    a("k_miss3", "b", "k_bye_m", "t", layer=K, label="yes")
    a("k_bye_m", "b", "k_end_m", "t", layer=K)
    a("k_bits", "b", "k_few", "t", layer=K)
    a("k_few", "l", "k_ask", ("l", 0.8), via=[("x", KG1), ("y", k_ask.fy(0.8))], layer=K,
      label="no: the next question", lab=(1, 0.5, -95, 0), lw=160)
    a("k_few", "b", "k_read", "t", layer=K, label="yes")
    a("k_read", "b", "k_menu", "t", layer=K)
    a("k_menu", "r", "k_part", "l", layer=K, label="1 to 4")
    a("k_part", "t", "k_read", "r", layer=K, label="then the menu again", lab=(0, 0.5, 0, 0), lw=200)
    a("k_menu", "l", "k_read", "l", via=[("x", KG1)], layer=K, label="9: the next scheme",
      lab=(1, 0.5, -90, 0), lw=150)
    a("k_menu", "b", "k_else", "t", layer=K, label="0, or 9 after the last scheme", lw=250)
    a("k_else", "l", "k_ask", ("l", 0.3), via=[("x", KG2), ("y", k_ask.fy(0.3))], layer=K,
      label="1: one more round", lab=(1, 0.3, -90, 0), lw=150)
    a("k_else", "b", "k_bye", "t", layer=K, label="2, or quiet")
    a("k_bye", "b", "k_end", "t", layer=K)

    n("k_rules", "KEYS THAT WORK ALL THE TIME IN KEYS MODE\n# = say it again (twice = slower)\n"
      "* = the next language\nCUT-IN BY KEY: a key pressed while a list is read stops the voice "
      "at once and is taken. In the first 0.25 s of a new prompt a key is not counted: it was "
      "meant for the old prompt.", -3660, cy=k_bits.cy, w=440, kind="note", layer=K, align="left")

    n("ev_speak", "ANY TIME in keys mode: the caller speaks real words (the cut-in gate: 0.6 s "
      "of voice, 2 real words)", -1500, cy=listen.top - 35, w=440, kind="event", layer=K)
    a("ev_speak", "r", "listen", ("t", 0.15), layer=K,
      label="to the talk path. Answers given by key stay: same log, same bits", lab=(0, 0.45, 0, 32),
      lw=330)


def main():
    preview = sys.argv[1] if len(sys.argv) > 1 else None
    bad = 0
    for level in (1, 2, 3):
        name = NAMES[level][0]
        c = build(level)
        errs, warns, crossings = c.check()
        path = os.path.join(HERE, name + ".excalidraw")
        with open(path, "w") as f:
            json.dump(c.excalidraw(), f, indent=1)
        ferrs, counts = check_file(path)
        kinds = {}
        for node in c.nodes.values():
            kinds[node.kind] = kinds.get(node.kind, 0) + 1
        print(f"{name}: {len(c.nodes)} boxes {kinds}, {len(c.edges)} arrows, "
              f"{len(c.labels)} labels, {crossings} line crossings; file parts {counts}")
        for e in errs + ferrs:
            print("   ERROR", e)
        for w in warns:
            print("   warn ", w)
        bad += len(errs) + len(ferrs)
        if preview:
            os.makedirs(preview, exist_ok=True)
            with open(os.path.join(preview, name + ".svg"), "w") as f:
                f.write(c.svg())
    print("ALL CHECKS PASS" if not bad else f"{bad} ERRORS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
