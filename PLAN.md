# PLAN v5: build the three flow charts, one at a time (5 Oct 2026)

The charts in `flow/` are the design. This file is the order of work.
- Phase 1 = `flow/1-talk-flow` (talk). Phase 2 = `flow/2-talk-flow-barge-in` (cut-in).
  Phase 3 = `flow/3-talk-flow-with-keys` (keys).
- One phase at a time, and only when the owner says "start Phase N". One step at a time inside it.
  After each step: run the checks, the owner tries it on the phone, stop and report.
- Older plans (v2, v4) are dropped. They are in git on branch `step-7.3-talk-first`.

## 0. How the work is cut (owner's answers of 5 Oct night are in here)
- **Phase 1, talk (chart 1), 9 steps:** 1.0 safe and smooth line, 1.1 greeting door, 1.2 language
  each turn, 1.3 clarify first, 1.8 follow-up talk, 1.4 English in the middle, 1.5 search,
  1.6 edge cases, 1.7 close. (1.8 is built right after 1.3: it is the same part of the code.)
- **Phase 2, cut-in (chart 2), 6 steps.** **Phase 3, keys (chart 3), 6 steps.**
- **Later, not planned yet:** greeting languages picked from the place of the caller's number;
  100+ schemes; an Indian phone number.
- **After every step:** the checks of section 7 and one phone call by the owner.
  (From 5 Oct ~18:00 this one call may be a Mac call, step 1.9. Phase 2 starts with 2.0.)
- **After every phase, the whole system is checked before the next one starts (the gate):**
  1. `pytest`, `make talk-eval`, `make stress`, `make barge-eval`: all clean.
  2. Five phone calls by the owner from a fixed list: a named scheme; a situation; a rude
     "just tell me" caller; a quiet caller; one call in each of Hindi, English and Marathi.
  3. The logs of those five calls are read: no dead air over 2 s, no cut sound, no wrong fact.
  4. Token and rupee count of the phase. The result is written in `PROJECT-UPDATE.md`.
  A phase is not closed with a red line in this list.

## 1. Where we stand (5 Oct, code = branch `step-7.15-cut-in`, commit 2485d79)

The shares are a rough guess, not a count.

| Chart | Built | Partly | Not built |
|---|---|---|---|
| 1 talk (about 60%) | quiet rule 30 s / 30 s; listen; the log; keyword bits; minimax question picker; truth check with one retry; "not for us"; goodbye; say it again; "one moment"; hang-up closes the log; model chain with a second key | search (no papers / how to apply, no ranking step, 4 cards not 5 chunks, caller's own words not English); clarifying questions (see 2.3); language (a key or the bare word "Hindi"; Hindi and English only) | the new greeting; Sarvam's language on every turn; English in the middle with Sarvam translate; a search the model asks for; "please say that again" when speech-to-text fails; next model on a time-out; voice retry and the "please call again" line; the 10 minute cap |
| 2 cut-in (about 80% in code, 0 phone checks) | the gate (0.6 s of real voice, Silero), pause, 2 real words, go on from the cut sentence, 2 false stops then ear off, caller's turn with a note, log row | "say it again" after a cut-in says the whole reply | ear on in the first 1-2 s of a reply; cut-in at the greeting; a key must not stop the voice in talk |
| 3 keys (about 50%) | the whole keys path (questions, bits, schemes, menu, "anything else"), key cut-in, `#` and `*` | language keys (1 and 2 only) | choosing keys or talk inside one call (today one setting at server start); key 6; speaking in keys mode goes to talk; shared answers between the two |

Three calls today died at the greeting (see NOTES): a stray noise shut the keys; a full Hindi
sentence was not taken as Hindi; the words said there were thrown away. That is step 1.1.

## 2. Phase 1: the talk flow (chart 1)

### 1.0 Safe before the first call (added 5 Oct evening, from the folder audit; about an hour)
**BUILT 5 Oct night (not yet tried on the phone).** What was built and what is not proven: `.agent/NOTES.md`, "step 1.0 BUILT". Switches: `PHONE_CHECK=false`, `LINE_RECONNECT=false`.
Small guards, no change to what the caller hears. Each was found by reading; see NOTES.
- `make call-me` and `make run` point the ONE Twilio number at this folder with no question
  asked. From then on the fallback folder gets no calls. Print which folder holds the number
  and ask once.
- The server listens on every network (0.0.0.0). Change to this computer only (127.0.0.1); both
  tunnels still reach it.
- `/stream` takes any connection as a call: check that it is Twilio's, and use the 10 minute cap
  (also in 1.6). Take out the open `/tone` test route and the open `/docs` pages.
- `make stage-check` sends about 2,500 tokens to each model just before a call: make it a few words.
  `make ear-check` is live by default: make it offline by default.
- `make pipeline-scrape` deletes a scheme's saved pages when one fetch fails: `make backup` first.
- Dead bits to cut while there: `TURN0_KEYS` (phone.py:50), the `voice_demo` branch in
  run_demo.py, 4 settings no code reads, the `WORK.md` pointer in types.py:41.
- **The line stays smooth (owner, 5 Oct night: no cuts from the network).** The call runs
  phone -> Twilio -> tunnel -> this laptop -> Sarvam and Groq. A weak wifi cuts it in three places.
  - Measure first: each call's log gets a "line report" (longest gap in the caller's sound, how
    far ahead our sound was sent, slowest Sarvam and Groq reply, why the line closed).
  - Before a call, `make call-me` tests the network (tunnel, Sarvam, Groq: one tiny request
    each) and says "weak network" instead of ringing.
  - Sarvam and Groq: connections are kept open between turns; one quick second try on a
    network error; "one moment" covers the wait (built).
  - Our sound is sent to Twilio ahead of time (built), so a short stall is not heard.
  - If the line to the laptop drops in a call: Twilio is told to connect again and the talk goes
    on from the same log, within 60 s. If it can not: a recorded "the line dropped, please call
    again", not silence.
  - The real fix is the place: a phone hotspot or wired net instead of the hall wifi for now; a
    small cloud server in Mumbai later (D9).
  - Owner, 5 Oct late: the hotspot it is; no cloud server. So the network test before a call and
    the connect-again path matter most: a hotspot can dip.
- Done this turn already: 7 old snapshots removed, `make talk-questions` needs `YES=1`,
  `scratch/` is ignored, junk files cleared.

### 1.1 The greeting door
**PART A BUILT 5 Oct late night (not yet tried on the phone).** Keys stay open after a noise; any real words at the greeting start the talk; the words are turn 1 with no second hello; "hello?" alone gets the short hello. NOT built yet: the new greeting words (part B, paid render, owner's OK), key 6 at the greeting, the 60 s answering-machine rule. Details: `.agent/NOTES.md`, "Step 1.1 part A".
- Keys stay open after a noise with no words.
- Any real words at the greeting start the talk. They are kept as turn 1.
- New greeting: hello in Hindi, English and 3 set languages (a setting, not from the phone
  number), then "speak in any language". Keep it near 15 s.
- **Owner, 5 Oct night (this is the greeting to build).** Three languages for now, those of
  Pune, Maharashtra: Hindi, Marathi, English. Each says the same three short things: welcome to
  Haqdaar; speak in English or your own language; for keys press 6. About 4 s each, 12 s in all.
  Draft words, to be OK'd before the paid render:
  - Hindi: "हक़दार में आपका स्वागत है। हिंदी, अंग्रेज़ी या अपनी भाषा में बोलिए। बटन के लिए 6 दबाइए।"
  - Marathi: "हक्कदार मध्ये आपले स्वागत आहे. मराठी, इंग्रजी किंवा तुमच्या भाषेत बोला. बटणांसाठी 6 दाबा."
  - English: "Welcome to Haqdaar. Speak in English or your own language. For keys, press 6."
- **Owner, later the same night: five languages.** Hindi, English, Marathi and two more spoken
  in Mumbai and Maharashtra. Picked: Gujarati and Tamil (the next most spoken there that the
  Sarvam voice can speak; Urdu speakers are served by the Hindi line). The two are a setting,
  one line to change. Draft words, to be checked by a speaker before the paid render:
  - Gujarati: "હકદારમાં આપનું સ્વાગત છે. ગુજરાતી, અંગ્રેજી કે તમારી ભાષામાં બોલો. બટન માટે 6 દબાવો."
  - Tamil: "ஹக்தாரில் உங்களை வரவேற்கிறோம். தமிழ், ஆங்கிலம் அல்லது உங்கள் மொழியில் பேசுங்கள். பொத்தான்களுக்கு 6 ஐ அழுத்துங்கள்."
  - **Owner's choice (5 Oct, late): Gujarati and Tamil are right, and they say the SHORT line**
    ("welcome, speak in your own language", about 2 s each). Hindi, English and Marathi say the
    full line. About 16 s in all. The full Gujarati and Tamil drafts above are kept, not used.
  - Length: five times about 4 s is about 20 s, over the 12 s aim. Until cut-in at the greeting
    (2.3) is built the caller must wait for the end. If 20 s feels long on the phone: Gujarati
    and Tamil say only "welcome, speak in your own language" (about 2 s each, 16 s in all).
  - The code knows three languages today. In 1.1 the greeting only NAMES Gujarati and Tamil;
    hearing and answering in them comes with 1.2 (language each turn) and 1.4 (translate).
- **Key 6 must work the day the greeting says it.** So the small part of 3.1 and 3.2 moves
  here: key 6 at the greeting starts the keys path that is already built. Key 6 in the middle
  of a talk, and going back from keys to talk, stay in Phase 3.
- Check: no-phone probe scripts (says "Hindi"; a noise then key 1; a full Hindi question). Phone check.
- Added 5 Oct evening, more ways a call can start (each gets a probe script):
  - The caller says only "hello?" or "haan?": not a need. Say the short "tell me what you need" line, not the whole greeting again.
  - The caller asks a full question at the greeting ("PM Kisan mein kitna milta hai"): it is turn 1 and is answered; no "which language" step.
  - The caller speaks a language the voice does not have: reply in Hindi and say so once (the full rule is 1.2).
  - Nobody speaks, only room sound or a TV: the quiet rule runs (30 s, greeting once more, 30 s, goodbye). Room sound must not reset the 30 s.
  - An answering machine or the trial-line message: no words meant for us for 60 s = hang up; never talk for 10 minutes to a machine.
  - The tests that pin today's greeting are changed in the same step, not left red.
- Added from the audit, traps in this step (file and line for each are in NOTES):
  - The greeting is a RECORDED clip. New words need a paid render and a new snapshot
    (`make render YES=1 SNAP=snapshots/CURRENT`, then `make snapshot`). So 1.1 goes in two
    parts. Part A, no cost: the three bugs (keys stay open, any words start the talk, words
    kept as turn 1). Phone check. Part B, on the owner's word: the new greeting words (D3 first).
  - One setting (`LANGS_OFFERED`) sets the greeting parts, the keys and the languages that can
    be picked. Five hellos with two pickable languages needs a setting of its own.
  - The code knows three languages only (the `Lang` type, the log check, three voices). A
    greeting may NAME more; picking more is 1.2.
  - The talk loop has no way to take first words, and says its own hello after the greeting
    (two hellos, written in two files). Give it the first words; then it skips its hello.
  - The pick-a-language step has 5 copies (the app, the sim, two test rigs, test fakes). All
    change together.
  - Words said WHILE the greeting plays are thrown away today (that is 2.3). Say so in the
    phone check: wait for the greeting to end.
  - The call viewer and talk-eval read the log line of the language pick and the clip's name.
    Keep both as they are.
  - About 10 test files pin today's greeting; two of them pin the very thing 1.1 removes
    ("words that name no language ask again").

### 1.2 Language from Sarvam, on every turn
- Use the language code the speech service already sends back. Under 3 words, or no code: keep
  the last language. A language the voice can not speak: reply in Hindi, say so once.
- Fixed lines (one moment, we are waiting, goodbye, not sure) are made per language on first use
  and kept on disk.
- Risk: the language guess is weak on short words. That is why short turns keep the last one.
- Check: probe in Hindi, English, Marathi, and a switch in the middle. Phone check.

### 1.3 Clarify first, with the fixed picker (the owner's main point)
What is wrong today: the code says "ask nothing" as soon as 4 or fewer schemes are left, and no
category has more than 4. So "my crops died" jumps straight to a list of schemes.
- **Kind of turn, by code.** A named scheme (name match 88+) or a straight question on the
  scheme in talk: answer first, ask nothing. Anything else is a situation or a loose remark:
  clarify first.
- **Which question, by code, never by the model.** The planner's minimax stays as it is: for
  each box (kind of need, work, age, gender, state, social group, income) count how many
  schemes are left after each possible answer; take the box whose worst answer leaves the
  fewest. Ties: fewer left on average, then a fixed easy-first order. No model, no chance.
- **Bits.** Candidates = search hits + every scheme of the named need, cut by the bitmask of
  all that is known. Each answer sets a bit and the list shrinks.
- **Talk limits.** Stop asking at 2 or fewer left (keys keep 4), after 3 questions, when no box
  cuts the list, or when the caller says "just tell me". One question a turn.
- **Relevance.** Never a box no remaining scheme depends on. Never a box already told. A box is
  asked at most twice. A need with no scheme (health and education are empty today) is said
  plainly, not papered over with schemes that do not fit.
- **The model's part.** It words the picked question in the caller's language and ties it to
  what was said in one short clause ("Sorry about your crop. Do you own the land?"). A free
  question of its own only when the words were not understood; code counts these.
- **Prompt.** New SITUATION block: do not list schemes while a next question is set.
- Check: new set of 30 situations -> the first question expected (no model, in pytest); minimax
  tests on a made-up set of 100 schemes; new talk-eval scripts. Then 10 real-model turns
  (about 30,000 tokens) on the owner's word. Phone check.

#### 1.3 additions (5 Oct evening): what a no-model run of human-style talk showed
The cases are in `fixtures/talk_human.json` (55 cases, each with what the line must do and what
it does today). The run is in NOTES. These are added to 1.3; nothing above is taken out.
- **Short names of schemes, first.** "Answer first for a named scheme" can not work today: only
  the full written name is found by name. "पीएम किसान", "मनरेगा", "केसीसी", "pm awas", "स्वनिधि"
  are not. Add a list of the names people say (short forms, letters, Hindi and Latin) for each
  scheme, kept next to the scheme data so 100 schemes can carry theirs.
- **A scheme we do not hold.** "आयुष्मान", "राशन कार्ड", "लाडली बहना" look like a loose need today
  and would get questions. Add a list of well-known schemes we do not hold; the line says "I do
  not have that one yet" and names the kinds it does have. So there are FOUR kinds of turn: a
  scheme we hold, a scheme we do not hold, a straight question, a situation.
- **The word "not".** "मैं किसान नहीं हूँ" sets farmer today; "मुझे लोन नहीं चाहिए" sets loans. The
  word spotter must skip a word that has "नहीं / नही / मत / not / no / don't" right by it. And the
  model may take a fact away (a `not` list in its reply), which it can not do today.
- **"Just tell me."** "नहीं नहीं, बस योजना बता दो", "सीधे बताओ", "just tell me": a word list in
  code plus a model flag. Asking stops for the rest of the call; the 2 best left are shown, with
  one clause on what the pick is based on ("from what you told me, a farmer in Maharashtra").
  The only time a question comes back: the caller asks "will I get it?" (see 1.8).
- **"I do not know" / "I will not say."** The box is set to not known at once and never asked
  again (today it is asked a second time). "Why do you ask?" gets one sentence of reason and the
  question once more.
- **An answer to another question** (asked age, told the state): the fact is taken and the age
  question does not count as asked.
- **Who the help is for.** "for my mother", "my son", "my husband": the questions are then about
  that person ("what is her age?"). Another person's work is not the caller's ("my husband was a
  farmer"). A new person in the same call clears age, gender and work; state and social group stay.
- **Two needs in one sentence.** Take the newest or the first named, keep the other in a short
  list, and come back to it: "you also asked about a house".
- **A new need.** The search runs on the new words only (today the last 3 turns are joined), the
  scheme in talk is dropped, and facts that came from the old need's words are checked again.
- **A corrected fact** ("not 26, 62") builds the list again from all schemes of the need.
- **Vague answers** ("बुज़ुर्ग हूँ", "थोड़ी ज़मीन है"): no guess; one yes-or-no question ("above 60?").
- **A caller in distress gets a kind sentence before any question** (see 1.8).
- Check: the "by code" cases of `fixtures/talk_human.json` become pytest cases with no model.

### 1.4 English in the middle
- **Owner, 5 Oct night (closes D1): ONE path for every language, Hindi and English too.** The
  caller's words always go through Sarvam and come out as English; the model works in English
  only; the reply always goes back through Sarvam translate into the caller's language. No
  "direct" way is kept for Hindi. For a caller who speaks English the reply is already English,
  so the translate-back step has nothing to do and is skipped; the speech step is the same.
  The time is still measured against today (1.2 to 2.1 s to the first sound) and told to the
  owner, but it no longer decides the path.
- Speech service in translate mode gives English words and the language in one call. The model
  reads and writes English. The truth check runs on the English. Sarvam translate turns the
  reply into the caller's language; numbers and scheme names must come out unchanged, or the
  safe line is said. Then the voice.
- Measure the time against today (1.2 to 2.1 s to the first sound). A switch keeps today's
  direct way.
- Owner decides on the numbers: if Hindi gets more than 0.5 s slower, Hindi and English stay
  direct and only other languages go through translate.

### 1.5 Search as drawn
- Add "papers" and "how to apply" to the index. Top 5 chunks go to the model, not whole cards.
- Query in English (from 1.4), more than one query for a need. Ranking is fixed code: vector
  score, name match, and the bits' "fits" mark. No paid ranking tool.
- Code searches first on every turn (20 ms). The model may ask for ONE more search with its own
  query. This keeps one model call on most turns; a second call costs about 0.6 s and 3,000 tokens.
- Check: the 30-sentence search set must not drop below today's 28 of 30; a new set of papers
  and how-to-apply questions.

### 1.6 Edge cases of chart 1
- Speech-to-text fails: "please say that again", not silence.
- Model time-out: go to the next model (today the chain stops).
- Voice fails: one more try, then a recorded "please call again" and hang up.
- 10 minute cap with a polite goodbye (the setting exists and is used nowhere).
- BUILT 5 Oct ~20:00 (commit 29930e1), checked by tests, not yet on a call:
  a model that fails in any way hands over to the next one (no new model once the time of two
  calls is used up); a sentence with no voice is tried once more; a reply with no voice at all
  gets the recorded "please say it again", and two such replies in a row end the call with the
  goodbye; the talk says goodbye 60 s before the 10 minute cap; a failed speech call gets
  "please say it again". Left open: the recorded "please call again" line does not exist (a
  new clip is a paid render, on the owner's word); until then the goodbye clip is used.

### 1.7 Close Phase 1
- talk-eval scripts for every new path, pytest, py_compile. Phone check. Commit and push on the
  owner's word.

### 1.8 Follow-up talk, like a person (added 5 Oct evening; done before 1.7 closes the phase)
After the first answer a real caller does not ask clean questions. Each line below is a group in
`fixtures/talk_human.json`. Fixed code does what it can; the model does the wording.
- **What was named, kept by code.** A list of the schemes named in the last reply, in order, and
  of all schemes named in the call. "दूसरा वाला" is the second of the last reply. "और कोई?" shows
  only schemes not yet named; when none are left the line says so.
- **Going back.** "वो पहले वाली": the first scheme again; its told parts are remembered.
- **Two schemes side by side.** "किसमें ज़्यादा पैसा": one sentence each, numbers from the papers.
  Never "this one is better for you". The "other scheme" guard lets a second scheme through
  only when it is one of the two last named.
- **"Will I get it?"** No promise, as today. The line says who the scheme is for, then the picker
  runs on THAT ONE scheme and asks the one thing it depends on that is not known. When all is
  known: "it is for X; you told me Y". Words as in D6 (agreed).
- **Say it another way.** "समझ नहीं आया": shorter and simpler, not the same sentences (new action
  `simpler`). "कितना बोला?": only the number sentence. "धीरे बोलो": slower voice for the rest of the call.
- **Hold on.** "एक मिनट रुको": new action `hold`; "take your time", then quiet for up to 2 minutes
  before the quiet rule starts. Today two quiet spells end the call at about 60 s.
- **"Hello? Can you hear me?"** is for us: "yes, I can hear you", then the last question again.
- **A sentence in two halves.** A 1 or 2 word start with no sense waits for the rest (the ear's
  end-of-speech wait is longer for it). Full fix is with the ear work in Phase 2.
- **Trust, fixed lines.** "Is it free?", "are you the government?", "are you a person?", "let me
  talk to a person": true, fixed lines. A caller who starts to read out an Aadhaar, bank or OTP
  number is stopped at once; the digits never reach the log (they are masked today).
- **What the line can not do.** Fill a form, send an SMS, check a payment: said plainly, with
  where to go.
- **Distress.** Words of giving up on life, or a death in the house: one kind sentence first,
  never a list of questions; then the schemes if the caller wants. (Owner, 5 Oct night: no
  help-line number is said. It was dropped.)
- **Off topic three times in a row:** a polite goodbye.
- **"Thanks" is not goodbye:** "anything else?" once; goodbye on the next no, bye or quiet.
- **Guard on cost:** all of this must fit one model call a turn and the 3,000 token turn. New
  actions are added to the one prompt; no second prompt.
- Check: one talk-eval script per group; the "by code" cases in pytest; 10 real-model turns on
  the owner's word; phone check with the owner playing a rude, a slow and a confused caller.

### 1.9 The Mac call (added 5 Oct ~18:00, the owner's plan for the demo)
The owner: the phone leg (Twilio in the US, the hotspot) breaks the sound and adds a wait, and
it is not the part we are building. So for the demo and for every step check, talk to the
system on the Mac itself: the Mac's microphone in, the Mac's speakers or headphones out.
- `make mac-call` starts the server with no phone and runs `tools/mac_call.py`. The tool plays
  Twilio's part on the same `/stream` socket (8 kHz sound, marks, clear, keys typed in the
  terminal). Nothing under `haqdaar/` changes, so what is shown IS the real call path: ear,
  language, model, search, voice, log.
- What it takes out: Twilio's trial message, the US leg, the tunnel, the number-move question.
  What stays: Sarvam (ear, voice) and Groq over the network, so the hotspot or hall network
  still sets the reply time.
- Headphones. With the speakers the microphone hears the agent's own voice. Today that sound is
  thrown away while a clip plays (cut-in is off), so a plain talk works on speakers; any cut-in
  test needs headphones.
- The step check "one phone call by the owner" may be a Mac call from now on. The phase gate
  keeps its five PHONE calls: the phone line is still what a real caller gets.
- Not in this step: a recording of the Mac call (the call's log and trace are written as for
  any call); a screen that shows the log live.
- Added 5 Oct ~18:50 (owner asked): the screen now shows the talk live. `make mac-call` prints what
  the ear heard (YOU), what the agent says (AGENT), keys, what the agent chose and the reply time.
  It reads the call's own log, so nothing under `haqdaar/` changed. `--plain` for no colour.

## 3. Phase 2: cut-in (chart 2)
- 2.0 (added 5 Oct ~18:00) Cut-in on the Mac first. One Mac call with headphones and
  `CUT_IN_GATE=true`: talk over a reply, cough, stay quiet, talk over the greeting. Costs no
  phone time and has no phone-leg noise, so what goes wrong is our gate and nothing else. Read
  the call's trace: every stop of the voice must have a reason line. Its result picks the order
  of 2.2 to 2.5. The same call on the phone is 2.1.
- 2.1 Phone check of the gate as built (`CUT_IN_GATE=true`). Costs nothing; do it first.
- 2.2 Ear on from the first sound of a reply.
- 2.3 Cut-in at the greeting: real words stop it and become turn 1.
- 2.4 A key does not stop the voice in a talk call.
- 2.5 "Say it again" after a cut-in starts at the cut sentence; the log says what was not heard.
- 2.6 Speakerphone and side-talk tests; talk-eval with the gate on; phone check with someone
  talking near the phone.

## 4. Phase 3: keys (chart 3)
- 3.1 Keys or talk is chosen inside the call, not at server start.
- 3.2 Key 6 at any time goes to keys with the answers so far. The greeting then says "for keys, press 6".
- 3.3 Speaking in keys mode goes to talk; answers given by key stay. Same log, same bits.
- 3.4 Language by key: 1 Hindi, 2 English, 3 to 5 the set languages.
- 3.5 Three clarifying questions with no usable reply: offer keys.
- 3.6 `make stress` (1,000 callers), `make barge-eval`, mixed keys-and-talk scripts, phone check.

## 4b. Phase 4: a photo by a link in an SMS (added 5 Oct ~18:50; changed ~19:30 on the owner's word)
What it is: in a call the caller asks to send a photo. The line sends an SMS with a link to the
caller's own number. The link opens one small page. The page already knows the number, takes
many photos, and has one send button. A reader looks at the photos, a helper at a desk checks
the result, and the line calls the caller back and says the answer, with the scheme that fits.
It sits next to cut-in and keys; it changes neither.
(The first plan said a 3-digit code on the call, typed into the page. The owner dropped the
code at ~19:30: a link, nothing to type.)

The flow, box by box:
1. In a call the caller says photo words ("फोटो भेजना है", "photo pathavaycha aahe", "I want
   to send a photo"), or presses key 9. Found by a word list in code, not by the model.
2. The agent says one fixed line: "I am sending a link to this phone by SMS. Open it and send
   the photos. I will call you back." A case is saved: a long random token, the language, the
   caller's number, the time. The SMS goes out. The talk then goes on as before.
3. The link is `<photo address>/p/<token>`. The number is NOT in the link; the token stands
   for it, and the page shows only "for the phone ending 4321". Nothing is typed.
4. The page is one small file (no outside file, under 20 KB), so it opens fast on a slow line.
   Two big buttons: "take a photo" (camera) and "pick photos" (many at once). Up to 6 photos,
   shown small, each can be taken out again. Each is made small on the phone (about 1,000 dots
   wide), so a send is quick. One button: "send".
5. The reader gets all the photos of the case and gives: what they show, what looks wrong, how
   sure, words to search our schemes with. Our own search then picks the scheme.
6. The desk page (this laptop only) shows the photos, the reader's result, the scheme, and the
   text that will be said. The helper can change the text, then presses "call back".
7. The line calls the caller. The call opens with the answer in the caller's language, not the
   greeting. After it the caller can talk as in any call.

CHANGED 5 Oct ~20:00 (owner): the reader is Muse, for any photo. `PHOTO_READER=auto` picks Muse when its key is set (`.agent/PROMPT-antigravity-photo-2.md`). The lines below are the older word.
The reader is NOT ours to build (owner, ~19:30). The team is finding a model made for crops
now, and others later. It runs on a computer of ours ("local"), with a Muse API as the backup.
Our part is the plug: `PHOTO_READER=stand-in | http | muse`. `http` posts the photos to
`PHOTO_READER_URL` and takes back the same five fields. Until a reader is plugged in, the desk
says "no reader set" and the helper writes the answer.

Rules:
- The reader's words are never said to a caller before a helper pressed "call back".
- No medicine name and no dose comes from the reader. Only what the helper typed.
- The caller's number is kept for the case only, in one file, and wiped after the call-back or
  after 24 hours. This is the one place a number is kept; the call log still holds none. The
  number is never in the link, never on a page in full, never in a log line.
- A link lives 24 hours. A wrong token gets "link not found"; many wrong tries from one address
  are slowed down. A photo over 5 MB or not a picture is refused. At most 6 photos a case.
- Two small servers in one tool (`tools/photo_desk.py`), NOT on the call server: the photo page
  on port 8002, which is the only one the outside can reach, and the desk on port 8003, bound to
  this laptop. They are apart because a tunnel makes every visitor look like this laptop, so
  "is it this laptop" can not guard a page behind a tunnel.
- The photo page must be reached from the caller's phone, so it needs an address the phone can
  open: `PHOTO_BASE_URL`. For the demo, on the hotspot, the laptop's own address works with no
  tunnel when the phone is the hotspot. For any other phone it needs its own tunnel.
- One caller at a time holds: the call-back waits while a call is live.

Steps:
- 4.1 The case store and the pages (new files only, no call code). Antigravity.
  `haqdaar/photo/cases.py`, `haqdaar/photo/reader.py`, `tools/photo_desk.py`, `make photo-desk`,
  tests. Prompt: `.agent/PROMPT-antigravity-photo.md`.
- 4.2 In the call: photo word list, key 9 in a talk call, the fixed line, the case, the SMS.
  The caller's number is taken at `/answer` (the server keeps only a hash of it today). A new
  provider function `send_sms`. Claude.
- 4.3 The call-back: "call back" places the call; the call opens with the answer. One pending
  answer in a file, read at call start (one caller at a time makes this safe). Works for the
  Mac call too: press "call back", run `make mac-call`, the agent opens with the answer. Claude.
- 4.4 The reader plug is filled when the team has its model. Not our build.
- 4.5 Check: a Mac call sends the link (shown on the screen too); the phone opens it and sends
  three photos; the desk shows them; "call back"; the answer is heard. Then the same by phone.
- Open risks, said plainly: (a) SMS on the Twilio trial goes only to a checked number, starts
  with Twilio's trial words, and an SMS from a US number to India is often held back by the
  Indian networks. So the link is ALSO shown on the Mac call screen and on the desk, and one
  real SMS is tried before the demo. (b) A keypad phone can not open a link: the caller passes
  the SMS on, or a person near them opens it. The page works on any phone that has the link.
- Not in this phase: WhatsApp, many helpers, a queue of cases, photos of papers (Aadhaar and
  such: private, not taken).

## 4c. The next steps (written 5 Oct ~20:00; takes the place of "the next two hours")
Done on 5 Oct evening: 1.9 (Mac call + its screen), 1.3a + 1.3b (clarify first, with the fixes
from its read), 1.5a + 1.5b and 1.4a + 1.4b in the branch (called by nothing yet), 1.6.
Workers: Claude and Antigravity. The file sets do not cross.
1. Owner: one Mac call on this commit (`make mac-call`, headphones). A situation ("my crops
   died"), a named scheme ("PM Kisan"), "just tell me", "for my mother".
2. DONE 5 Oct ~21:00 (e946c06, flag TALK_CHUNKS). Claude: wire search by part (1.5) into the talk: the top 5 chunks go to the model, not whole
   cards. Check: 30-set stays at 28, prompt size, 10 real-model turns on the owner's word.
3. Antigravity: step 4.1, the photo page and the desk (`.agent/PROMPT-antigravity-photo.md`).
4. FAULTS DONE 5 Oct ~21:00 (e946c06, with four more from a Mac call); 1.8 is left. Claude: the two faults of 1.3 still open (a need said about another person; the not-held
   line for Gujarati and Tamil), then 1.8 follow-up talk (hold on, say it simpler, the second
   one, will I get it).
5. Antigravity, after 4.1: the translate guard's fix pass (number words on both sides, "18-40",
   phone numbers, Tamil names, the time limit) with a set of 100 real reply lines. Only then
   is 1.4 wired.
6. Claude: 4.2 + 4.3 (photo words and key 9 in the call, the SMS, the call-back).
7. Owner: 2.0, cut-in on the Mac with headphones; Claude fixes what the trace shows (2.2-2.5).
8. 1.7 close of Phase 1: all checks, five phone calls, push.
9. Phase 3 keys (3.1-3.6). Then the reader plug is filled when the team has its model (4.4).

## 5. Risks, and what guards each
- **Groq day limit** (200,000 tokens a model, about 65 turns): real-model test runs stay small
  and only on the owner's word. Never send a big request to read the limit.
- **Translate changes a number or a name:** compare digits and names before and after; the safe
  line on a mismatch.
- **Language guess on short words:** keep the last language.
- **A long five-language greeting:** short hellos; cut-in at the greeting comes in Phase 2.
- **A demo today:** `~/code/haqdaar-v2-7.3` is left as it was (branch `step-7.15-cut-in`).
- **Too many questions drive the caller away** (added 5 Oct evening): at most 3, never the same
  one twice after "I do not know", and "just tell me" always wins.
- **Fixed word lists grow wild** (not, just tell me, hold on, distress, short names): each list
  lives in one file, has its own test, and is checked in Hindi, Marathi and English. They must
  hold for 100 schemes: the lists are about how people talk, not about one scheme, except the
  short names, which sit with each scheme's data.
- **The prompt grows past the Groq limit:** count the tokens of the prompt in a test; the new
  actions may add no more than 400 tokens.
- **A new action the model picks wrongly** (hold instead of goodbye): each new action gets
  talk-eval scripts with the near-miss sentences, before the phone check.

## 6. For the owner to decide
**Closed on 5 Oct night:** D2 + D8 (the brain folder: five papers kept in `docs/old-design/` as
background, the rest and its rule file removed; nothing in it is binding). D3 (Hindi, Marathi,
English; by place later). D4 (the greeting says "press 6" from Phase 1, and key 6 works at the
greeting from 1.1). D5 (dropped: no help-line number). D6 (agreed as proposed). D7 (1.8 is
built right after 1.3).
**Closed later the same night:** D1 (every language goes through English, Hindi and English too; see 1.4). D3 again (five languages: Hindi, English, Marathi, Gujarati, Tamil).
**Closed (5 Oct, late): D9. A phone hotspot. No money is spent on a server; section 8 is NOT taken and is kept only as a record.**
Older wording: **Open:** D9 only (the owner wants the cloud path kept in the plan; steps are in section 8).
Older wording: D1, and new: D9. Where the server runs so the line is smooth: a phone hotspot for now
(free), or a small cloud server in Mumbai (costs a little each month, no tunnel, no hall wifi).
The older text of each decision is kept below.

- D1. English in the middle for Hindi too, or only for other languages (after the 1.4 numbers).
- D2. `haqdaar-v2-brain/`, `source-docs/` and `sync_vault.py` were kept on this branch. Say the
  word and they go.
- D3. Which 3 local languages the greeting names (clips exist for Marathi).
- D4. Should the greeting say "for keys, press 6" from Phase 1, or only when it works (Phase 3)?
  The plan says Phase 3.

- D5. (added 5 Oct evening) The help-line number said to a caller in distress. Proposed: Kisan
  Call Centre 1800-180-1551 and Tele-MANAS 14416. Please check both numbers before they go in.
- D6. The words for "will I get it?". Proposed: "This scheme is for <who>. You told me <fact>."
  and never "you will get it" or "you will not get it".
- D8. `.agents/rules/haqdaar-brain.md` tells every agent the brain folder is "binding" and
  `AGENTS.md` names `sync_vault.py` as the build check. Both clash with this plan. They are your
  rule files, so they were left. Goes with D2: keep the brain as old background, or drop it.
- D7. Follow-up talk (1.8): build it right after 1.3, or after 1.5 as numbered? The cases that
  are fixed code (the word "not", short names, "just tell me", "I do not know") are in 1.3 now.

**Open (5 Oct ~18:50), for Phase 4:**
- D10. CLOSED again (owner, 5 Oct ~20:00): Muse reads the photo. Simple, shows the idea, any photo
  (crop, house, field, animal), not only crops. Tried: Muse read a test picture in 5.3 s for under
  1 paisa. The photo goes to Muse (its Contributor tier may train on it). The `http` plug stays for
  a local model later.
- D11. Changed with D10: any photo of a need, not only crops. Not papers.
- D12. Who gets the SMS and the call-back on the Twilio trial: only a checked number (today one:
  the owner's, ...9690). TRIED 5 Oct 20:10: an SMS with a link from the US number was delivered to
  it (Twilio's word; 8.3 US cents each, balance 10.56 USD). Another phone must be checked in the
  Twilio console first, or the account paid up. The link needs an open address (PHOTO_BASE_URL).

## 7. Checks, every step
```
.venv/bin/python -m pytest -q        # 2,385 pass on this branch (5 Oct)
make talk-eval                       # 2,552 scripted talk calls, 0 rules broken
python3 flow/build_flows.py          # only if a chart changed
python3 -m py_compile <changed files>
```
`make stress` and `make barge-eval` when the keys path or `turn.py` is touched.

## 8. The cloud server in Mumbai: NOT TAKEN (owner, 5 Oct late: no money on this; the line runs on a phone hotspot)
Kept as a record only. Do not build it and do not bring it up again unless the owner asks.
Why: no laptop, no tunnel, no hall wifi in the call. Twilio talks to a server that sits near
Sarvam's and Twilio's Indian ends. One caller at a time needs only a small machine.
What the owner sets up (about 30 minutes, once):
1. An account at a cloud with a Mumbai region (AWS `ap-south-1`, or DigitalOcean / Google Cloud
   Mumbai). Smallest machine with 2 GB of memory, Ubuntu 24.04. About Rs 500 to 1,000 a month.
2. A web name for it (any cheap domain, or a free sub-name), pointed at the machine's address.
   Twilio needs `https` and `wss`, so a real name with a certificate is needed.
3. Give the agent ssh access (a key), or run the set-up script yourself.
What the agent then does (a step of its own, after Phase 1's gate):
4. A set-up script: Python 3.11, the repo, the audio clips and the snapshot, `.env` copied by
   hand (never through git), Caddy in front for the certificate, the server as a service that
   starts again by itself.
5. Twilio's number pointed at `https://<name>/answer`. `make call-me` gets a `HOST=` way that
   skips the tunnel.
6. The line report of 1.0 is compared: laptop on a hotspot against the cloud server, five calls each.
Until then: a phone hotspot or wired net, not the hall wifi.
