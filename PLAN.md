# PLAN v5: build the three flow charts, one at a time (5 Oct 2026)

The charts in `flow/` are the design. This file is the order of work.
- Phase 1 = `flow/1-talk-flow` (talk). Phase 2 = `flow/2-talk-flow-barge-in` (cut-in).
  Phase 3 = `flow/3-talk-flow-with-keys` (keys).
- One phase at a time, and only when the owner says "start Phase N". One step at a time inside it.
  After each step: run the checks, the owner tries it on the phone, stop and report.
- Older plans (v2, v4) are dropped. They are in git on branch `step-7.3-talk-first`.

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

### 1.1 The greeting door
- Keys stay open after a noise with no words.
- Any real words at the greeting start the talk. They are kept as turn 1.
- New greeting: hello in Hindi, English and 3 set languages (a setting, not from the phone
  number), then "speak in any language". Keep it near 15 s.
- Check: no-phone probe scripts (says "Hindi"; a noise then key 1; a full Hindi question). Phone check.

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

### 1.4 English in the middle
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

### 1.7 Close Phase 1
- talk-eval scripts for every new path, pytest, py_compile. Phone check. Commit and push on the
  owner's word.

## 3. Phase 2: cut-in (chart 2)
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

## 5. Risks, and what guards each
- **Groq day limit** (200,000 tokens a model, about 65 turns): real-model test runs stay small
  and only on the owner's word. Never send a big request to read the limit.
- **Translate changes a number or a name:** compare digits and names before and after; the safe
  line on a mismatch.
- **Language guess on short words:** keep the last language.
- **A long five-language greeting:** short hellos; cut-in at the greeting comes in Phase 2.
- **A demo today:** `~/code/haqdaar-v2-7.3` is left as it was (branch `step-7.15-cut-in`).

## 6. For the owner to decide
- D1. English in the middle for Hindi too, or only for other languages (after the 1.4 numbers).
- D2. `haqdaar-v2-brain/`, `source-docs/` and `sync_vault.py` were kept on this branch. Say the
  word and they go.
- D3. Which 3 local languages the greeting names (clips exist for Marathi).
- D4. Should the greeting say "for keys, press 6" from Phase 1, or only when it works (Phase 3)?
  The plan says Phase 3.

## 7. Checks, every step
```
.venv/bin/python -m pytest -q        # 2,385 pass on this branch (5 Oct)
make talk-eval                       # 2,552 scripted talk calls, 0 rules broken
python3 flow/build_flows.py          # only if a chart changed
python3 -m py_compile <changed files>
```
`make stress` and `make barge-eval` when the keys path or `turn.py` is touched.
