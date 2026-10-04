# STEP 7.1 — Caller questions, answered in TEXT only (Antigravity work order)

Plain goal: a caller can ask a question at any point ("how much money is in PM Kisan?"). The
system sees it is a question, writes a short true answer from the scheme's own text, shows it as
text, and goes back to where the call was. **No live speech in this step.** That is step 7.2.

**Do step 7.0b first** (`PROMPT-ANTIGRAVITY-7.0b-GATE.md`): it fixes how keys are taken.

**Language (the owner's rule, 4 Oct):** speech in the caller's language -> **English** -> the
router and the answer step work on English -> the answer goes **back to the caller's language**
-> out. Section 2j says how. Where an item below says "in the caller's language", 2j wins.

Everything sits behind one switch, `QA_ENABLED`, **off by default**. With it off, the app must
behave exactly as it does today. This is the most important rule in this file.

## 0 · Setup
```
cd ~/code/haqdaar-v2
git branch --show-current     # must print: step-7.0-live-answers   (wrong branch -> STOP)
git log --oneline -1          # must print: 628818a ...              (wrong base -> STOP)
make test                     # write down the pass count before you change anything
```
The tree has uncommitted doc files from Claude (`PROJECT-UPDATE.md`, `.agent/*`, this file). Leave them.
Read first: `AGENTS.md`, `HANDOFF.md`, `.agent/NOTES.md` from "Scheme Q&A" (3 Oct) to the end.

## 1 · What exists that you build on
| Thing | Where | What it gives you |
|---|---|---|
| Question loop, spoken input | `haqdaar/engine/call.py:297`, handled 498-633 | `turn_n += 1` at 499, `model.turn` at 607, the UNCLEAR path with the strike at 612-633 |
| Anything-else turn | `call.py:988-1007` | `model.confirm`; only True re-opens |
| Section menu | `call.py:1077-1089` (`Engine._read_back`) | any non-Digit moves to the next scheme |
| Model | `haqdaar/model/router.py:30`, client `haqdaar/model/client.py:36-126` | JSON mode, never raises, usage ledger |
| Scheme text | `snapshots/<id>/schemes.jsonl` | per row: `chunks[en|hi|mr]` (name, summary, benefit_text, who_can_apply, documents, how_to_apply) and `gate_notes` |
| Path pattern | `haqdaar/data/corpus.py:96-115` | `Path(tunables.SNAPSHOTS_DIR) / corpus.snapshot_id / "schemes.jsonl"` |
| Banned-phrase check | `haqdaar/contracts/vocab.py:75,94` | `FORBIDDEN`, `find_forbidden(text, lang)` |
| Typed test call | `tools/dashboard_api.py:253-338`, `haqdaar/sim.py:182` (`FakeAudio`) | typed words become `Speech` only on profile `spoken` |
| Draft answer cases | `.agent/qa_stress_draft.py` | 15 answer cases, with the answer prompt that passed |
| Draft router prompt | `.agent/qa_router_draft.py` | the sorting prompt (`SYS`) and 50 cases; qwen got 49 of 50 |
| Router prompt today | `haqdaar/model/prompts/turn.py:35-47` | the five classes |

## 2 · Build

### 2a · Fix the router's model name (the app is broken without this)
1. `client.py:62` falls back to `llama-3.3-70b-versatile`. Groq no longer has that model (404).
   Change the fallback to `openai/gpt-oss-120b`. Env names stay the same.
2. Run `tools/model_bakeoff.py` live for `qwen/qwen3.8-27b` and `openai/gpt-oss-120b`, on the
   prompt as it is today. Report right/wrong counts, the middle time and the slowest call for
   each. Do not pick for the owner; just report. Claude's sorting test (50 cases, new prompt):
   qwen 49 right, middle 0.50 s, slowest 1.77 s; gpt-oss-120b 46 right, middle ~0.9 s, slowest
   2.74 s; gpt-oss-20b 43 right. `MODEL_TIMEOUT_S` is 2.0.

2x. Spoken yes/no is broken for Hindi and Marathi script. `match_confirm("हाँ", "hi")`,
   `("नहीं", "hi")`, `("हो", "mr")`, `("नाही", "mr")` all return `None` today, because
   `haqdaar/model/confirm.py:12-22` holds Roman words only. Add the Devanagari forms of the words
   already in the lists (and "हां", "जी हाँ", "सही है", "ठीक है", "गलत", "होय", "बरोबर", "नको").
   Add tests. This is a bug fix and is not behind the switch.

### 2b · Switches (`haqdaar/contracts/tunables.py`, same style as line 50)
3. `QA_ENABLED` (bool, default **false**), `QA_MAX_PER_CALL = 5`, `QA_MAX_SCHEMES = 4`,
   `QA_TIMEOUT_S = 4.0`, `QA_MAX_WORDS = 40`.

### 2c · The router decides what the caller's words are (`haqdaar/model/`)
The owner's call: one small, well-prompted router decides. No keyword list decides it.
4. Kinds: `ANSWER`, `BOTH` (an answer and a question), `QUESTION`, `REPEAT`, `OTHER`. The
   rules and examples are `SYS` in `.agent/qa_router_draft.py`. Keep their order and wording.
4a. `Model.turn`: **when `QA_ENABLED` is false, the prompt sent must be the same as today, byte
   for byte** (test this). When true, add the kind rules to the prompt so ONE call returns the
   kind and the value. Map the reply: ANSWER -> `Answer` as today; BOTH -> `Answer` with a new
   field `also_question: bool = False` set True; QUESTION -> a new result class `Question()`;
   REPEAT -> `Repeat`; OTHER, a missing kind, or bad JSON -> `Unclear`. Signature unchanged.
4b. `Model.sort(asked, transcript) -> str` (new): the same rules as a call of its own, for the
   two places that have no router call today (anything-else, section menu). Any failure -> `"OTHER"`.
4c. Add a mode to `tools/model_bakeoff.py` (or a `make qa-router-check`) that runs the 50 draft
   cases live and prints right/wrong per model. Not part of `make test`.
5. `find_verdict(text, lang) -> str | None` in `haqdaar/contracts/vocab.py`, next to
   `find_forbidden`. Catches any yes/no about the caller, both ways: "you can apply", "you
   cannot apply", "आप आवेदन कर सकते / नहीं कर सकते", "आपको मिलेगा", "तुम्ही अर्ज करू शकता",
   "तुम्हाला मिळेल" and the like. Start from `VERDICT` in `.agent/qa_stress_draft.py`.

### 2d · Scheme text (`haqdaar/data/scheme_text.py`, new, stdlib + contracts only)
6. `SchemeText.load(snapshot_id)` reads `schemes.jsonl` once. `card(scheme_id, lang) -> str` gives
   the six chunk fields plus `gate_notes`. Unknown id or language -> `""`. Never raises.

### 2e · The answer (`haqdaar/model/answer.py`, new, and one method on `Model`)
7. `Model.answer(question, lang, cards, profile) -> str | None`. `cards` is the text of 1 to
   `QA_MAX_SCHEMES` schemes. `None` means "no safe answer". Never raises.
8. One model call through the existing client, task name `qa_answer`, JSON reply
   `{"answer": "<text>"}` or `{"answer": null}`. Use the system prompt `ANS_SYS` from the draft,
   and add: say what the rule says; no "I"/"we" verbs; write numbers in digits exactly as in the
   text; you cannot see the caller's application or payments, so questions about their own case
   get null. Use `QA_TIMEOUT_S`, not the 2.0 s router timeout. If the client cannot take a
   timeout per call, add an optional argument whose default keeps today's value.
8b. Backup model: if the first call fails or times out, try once more with
    `tunables.QA_BACKUP_MODEL` (default `qwen/qwen3.8-27b`, same Groq key), inside the same
    `QA_TIMEOUT_S` total. If that fails too, return `None`. **Do not wire NVIDIA into a live
    call**: Claude timed 12 NVIDIA free models on 3 Oct; one answered, in 3.5-21 s, the rest
    gave 404 or timed out. `NVIDIA_API_KEY` is in `.env` for offline work only; `make qa-check`
    may take `--provider nvidia` so the owner can re-time it later.
9. Before sending or logging, replace any run of 8 or more digits in the question with `…`
   (callers read out Aadhaar and phone numbers).
10. Return `None` if any check fails: `find_forbidden`, `find_verdict`, more than 2 sentences,
    more than `QA_MAX_WORDS` words, or a number in the answer that is not in `cards`
    (compare digits only; treat Devanagari digits as the same digits).
11. A failed or late answer call must **not** count toward `Model.failures` / keypad-only.
12. Write one line per question to `tunables.REPORTS_DIR/questions.jsonl`:
    `{ts, lang, question, scheme_ids, answer, blocked_by, seconds}`. `blocked_by` is `null`,
    `"model_null"`, `"timeout"`, `"verdict"`, `"forbidden"`, `"number"` or `"too_long"`.

### 2f · The engine (`haqdaar/engine/call.py`) — smallest change that works
13. One helper, e.g. `_try_question(...) -> bool`. It returns False at once (and does nothing)
    unless **all** of these hold: `tunables.QA_ENABLED`, `hasattr(model, "answer")`,
    `hasattr(audio, "say_text")`, fewer than `QA_MAX_PER_CALL` questions answered this call,
    call not in keypad-only mode, and the router said the words are a question (see 16).
14. Which schemes go in: a scheme the caller named; else the current survivors **that pass
    `Filter.speakable`**, if there are `QA_MAX_SCHEMES` or fewer; else none -> return False.
15. If `model.answer` gives text: `audio.say_text(text)`, write the log line (2g), return True.
    If it gives `None`: return False. The caller of the helper then does what it does today.
16. Use the helper in three places only:
    - **Question loop** (after 607-611): when `model.turn` returns `Question`, before the strike
      at 614. On True, take back the `turn_n += 1` from line 499, add no strike, and `continue`
      so the same question is asked again. On False, today's UNCLEAR path, unchanged.
    - **Anything-else** (1000-1007): when `model.confirm` is `None` and `model.sort` says
      QUESTION or BOTH; on True, ask anything-else again.
    - **Section menu** (1086-1089): on a `Speech`, when `model.sort` says QUESTION or BOTH, with
      the scheme being read as the named scheme; on True, offer the same menu again.
    Guard every new call with `hasattr` (the test fakes have no `sort`, `answer`, `also_question`).
17. BOTH ("I am a farmer, will I get a loan?"): take the answer exactly as today, with the
    confirm read-back. If `also_question` is True, keep the transcript and try it once, right
    after the confirm accepts. If this needs more than about 15 lines in `call.py`, stop and report.
17a. The fences around the models, all in code. None of them may be skipped:
    - a value not in the box's closed list is not an answer (the span guard, as today);
    - every value still gets the confirm read-back, as today;
    - OTHER and anything the router is unsure of goes down today's UNCLEAR path;
    - an order to change the rules is OTHER, and the answer prompt also refuses it;
    - no answer text reaches the caller without passing item 10.
18. `call.py` import lines must not contain `audio`, `model` or `pipeline`, and the words
    `Thread`, `asyncio`, `Queue`, `Pool` must not appear in it at all (`tests/test_call.py:1009-1030`).
    `haqdaar.data.scheme_text` and `haqdaar.contracts.vocab` are allowed. Check `Question` by a duck-typed attribute or import it from `haqdaar.contracts.types`.

### 2g · Log (`haqdaar/contracts/log_schema.py`, `haqdaar/data/log.py:116-215`)
19. Add turn class `QUESTION` and one optional field `answer` on `TurnLogRecord`. Copy it in
    `Log.write` (126-138). A QUESTION line keeps `turn_n` unchanged, like SILENCE.

### 2h · Showing it (`haqdaar/sim.py`, `tools/dashboard_api.py`)
20. `FakeAudio.say_text(text)`: `self.note(f"-> answer {text}")`. The call viewer already shows
    unknown trace lines as plain notes. **Do not add `say_text` to `PhoneAudio`** — that keeps
    real phone calls unchanged in this step even if the switch is on.
21. `TypedCaller._next_input` (290-292): typed words also become `Speech` on profiles `confirm`
    and `readback`, so a question can be typed there.
22. Typed test call: when `QA_ENABLED` is true, run it with the real `Model()`; when false,
    keep the offline `SimModelClient` as today.

### 2j · English in, the caller's language out (`ENGLISH_PIPE`, default **false**)
Claude's live check, 4 Oct, 5 saved clips (clean test voices, not real phone callers):
Sarvam `saaras:v4` with `mode: "translate"` gave good English in 0.56-0.94 s, the same speed as
`transcribe` ("मैं बिहार की एक महिला किसान हूँ..." -> "I am a female farmer from Bihar and I
need an agricultural scheme."). It writes numbers as words ("six lakh rupees"). English back to
hi/mr: `sarvam-translate:v1` got all 6 money and age sentences right in 0.83-1.26 s;
`mayura:v1` got 2 of 6 wrong (it turned "6,000" into "three thousand two hundred"). Do not use mayura.
24. `tunables.ENGLISH_PIPE` (bool, default false). Off -> everything as today.
25. On: `SarvamSTT.transcribe` (`haqdaar/audio/ear.py:195-203`) sends `mode: "translate"`. The
    language code stays the caller's picked language. `Speech` gets two optional fields:
    `lang: str = ""` (what the speech service heard) and `english: bool = False`.
26. The backup speech service (Groq whisper) does not give English. When it is used, the text
    stays in the caller's language, `english` is False, and the turn goes on as today.
27. The router prompt (`prompts/turn.py`, `opener.py`): when `english` is True, add one line
    saying the caller's words are an English translation of speech in <language>. The value ids
    are already English, so the span guard now checks an English span in English text.
28. Yes/no (`haqdaar/model/confirm.py`): when `english` is True, check the English word list
    first, then the caller's language list. Item 2x still stands (the backup path needs it).
29. Scheme names (`haqdaar/engine/door_a.py`): check that "PM Kisan", "Atal Pension Yojana" and
    three more names match from English text. Report what does not.
30. The answer: the model gets the English question and the **English** card
    (`card(scheme_id, "en")`) and writes the answer in English. All checks of item 10 run on the
    English answer. For the typed test call, typed words are treated as already English only if
    they are ASCII; otherwise they go as they are and the card is in the typed language.
31. Then, if the caller's language is not English: translate the answer with Sarvam
    `POST https://api.sarvam.ai/translate`, body `{input, source_language_code: "en-IN",
    target_language_code: "hi-IN" | "mr-IN", model: "sarvam-translate:v1"}`, header
    `api-subscription-key`. Time-out 3 s, inside a total of `QA_TIMEOUT_S + 3`.
32. Code check after translating: the digits in the translated text must be the same set as the
    digits in the English answer (drop commas; Devanagari digits count as the same digits). Run
    `find_forbidden` and `find_verdict` on it in the caller's language too. Any failure or a
    time-out -> `None`, `blocked_by: "translate"`.
33. `questions.jsonl` gets `question_en`, `answer_en`, `answer` (what the caller gets), `lang`.
34. `make qa-check` runs with `ENGLISH_PIPE=true` as well and prints both texts side by side.
35. Tests with fakes: switch off -> the speech request is the same as today; switch on -> mode
    is `translate`; a translated answer with a changed number gives `None`.

### 2i · Live check tool (`tools/qa_check.py`, `make qa-check`)
23. Runs the 15 answer cases from the draft against the real model and prints, per case: the
    question, the answer, `blocked_by`, seconds. Ends with counts. This is the owner's manual
    check. It is not a pytest test and must never run inside `make test`.

## 3 · The design, in short
```
caller input
 ├─ button press ........................ today's path
 └─ speech -> ONE router call says the kind
     ├─ ANSWER ......................... today's path (closed list, confirm read-back)
     ├─ BOTH ........................... answer as today; the question is tried after the confirm
     ├─ QUESTION ─> model.answer(few schemes' text) ─ checks pass ─> say_text, same question again,
     │                                               │                no turn, no strike
     │                                               └ None ───────> today's UNCLEAR path
     ├─ REPEAT ......................... today's path
     └─ OTHER / unsure / bad reply ..... today's UNCLEAR path
```

## 3b · Rules for mixed-up input (the owner asked for these to be fixed in writing)
0. **Key rules G1-G11 are in `PROMPT-ANTIGRAVITY-7.0b-GATE.md`** (double press, random key, key
   in a gap, key after speech). They come first; nothing here changes them.
1. **A key always beats speech** in the same turn, as today (`turn.py:84-88`). A key is never a question.
2. **A key means what the menu at that moment says.** Nothing here changes any key map.
3. **Spoken answers are read back and need a yes; key answers are taken at once.** As today.
4. **A question never moves the call.** After the answer, the same prompt is asked again. No
   turn, no strike. At most `QA_MAX_PER_CALL` per call; after that, today's path.
5. **Answer plus question:** the answer first, its read-back, then the question.
6. **"Yes" / "no" only count** at the read-back and the anything-else turn. At a box question
   they are OTHER (unless that box's own values are yes/no).
7. **A spoken number** ("एक", "one") is not a key. It goes to the router like any other words.
   Do not add a number-word map in this step; log such turns so the owner can decide later.
8. **Which scheme does "this" mean?** In the results menu: the scheme whose menu is open. In
   the question loop: a scheme the caller names; else the survivors if there are 4 or fewer;
   else no answer (7.3 adds search).
9. **Keypad-only mode:** speech is not heard, so there are no questions. Unchanged.
10. **While a clip plays,** a key stops it and speech is not heard, as today. Unchanged.
11. On a real phone the results menu does not listen for speech (`turn.py:94,117`). **Leave
    that alone in 7.1**; only the typed test call takes words there (item 21). 7.2 opens it.

## 4 · What Claude's stress test found (so you know why the rules above exist)
- Round 1, a loose sorting prompt: 21 of 26 right. Round 2, the prompt in the draft (rules in
  order, nine examples): qwen 25 of 26 on the same cases and 24 of 24 on new ones. The one miss
  ("can I apply if I am sixty five?" -> ANSWER) holds an age, so it is close to BOTH.
- "The land is in my father's name": without the rule-only prompt the model said "you cannot
  apply". The card says land in the **family's** name. With the prompt it stated the rule.
- "My PM Kisan money has not come": the model made up a long reply. Such questions must get null.
- Off-topic, another scheme not in the text, and "ignore your rules" all came back with no answer.
- Still open: the model sometimes concludes a little beyond the text (tenant farmers). The
  code checks do not catch that. The owner will read `questions.jsonl` to judge it.

## 5 · Tests and checks
Tests use fakes only; `tests/conftest.py` blocks any real HTTP call.
- `Model.turn` with a fake client: switch off -> the prompt is byte-for-byte today's; switch on
  -> each kind maps to the right result class; bad JSON or a missing kind -> `Unclear`.
- `Model.sort` with a fake client: each kind comes back; a client error gives `"OTHER"`.
- `find_verdict`: one hit and one miss per language.
- `Model.answer` with a fake client: good answer returned; each of verdict / forbidden / number /
  too long / null / client error gives `None` and the right `blocked_by`; 12 digits are masked;
  `failures` is unchanged after an error.
- Engine with `QA_ENABLED` on: a question in the loop is answered, `turn_n` and strikes do not
  move, the same box is asked again; the 6th question in a call is not answered; keypad-only
  mode never answers; a model without `.answer` and an audio without `.say_text` behave as today.
- **Engine with `QA_ENABLED` off: nothing in the trace or log changes.** Run one existing sim
  call both ways and compare the traces line by line.
```
make test          # all pass, 0 fail, more tests than before
make sim           # ends at closing_farewell
make stress        # crashes 0, truth failures 0
python3 -m py_compile haqdaar/engine/call.py haqdaar/model/answer.py haqdaar/data/scheme_text.py
QA_ENABLED=true make qa-check     # prints 15 answers; paste the output in your reply
make qa-router-check              # 50 sorting cases, live; paste the counts per model
```

## 6 · Records and hand-back
- Append what you learn to `.agent/NOTES.md` as you go. Update `.agent/TASK.md` item 5.
- Do not edit `haqdaar-v2-brain/` or `source-docs/`. Claude writes the rule changes at review.
- No commit, no merge, no push, no tag. Leave the work in the tree for Claude's review.
- Reply with: files changed, test counts before and after, the bake-off numbers from 2a, the
  `make qa-check` output, and anything you could not do.

## 7 · Do not
- Do not add live speech, a TTS client, streaming, a search index, embeddings or a cache. Later steps.
- Do not change `Model.opener`, `Model.confirm`, `Corpus`, or the signature of `Model.turn`. The only
  changes to result types are the new `Question` class and `Answer.also_question`.
- Do not change how a call behaves when `QA_ENABLED` is off.
- Do not touch the confirm read-back turn (`call.py:662`) or the keypad menu (`call.py:286`).
- Do not run `make pipeline-extract`. Do not spend Muse. Do not run bulk Sarvam renders.
- Do not start or stop the owner's `make dashboard`; do not use ports 3000, 3210, 8001.
- Do not print, log or commit any API key.
