# Prompt for a new chat: finish the TALK BUILD (steps B4 to B7)

Paste everything below the line into a new Claude Code chat opened in `~/code/haqdaar-v2`.

---

Finish Plan v4 "TALK BUILD". B0 to B3 are done and committed. Do B4, B5, B6, B7, one at a time.
Stop and report after each step. I check on my phone after B4 and after B5.

## Read first
1. `~/code/haqdaar-v2/.agent/TASK.md` (the plan: "Plan v4 — TALK BUILD" and the owner's changes C1-C7).
2. The last five sections of `~/code/haqdaar-v2/.agent/NOTES.md` (from "B0 done + B1 map" to the end).
   NOTES is big: read it by line range, not whole.

## Where things are
- Code folder: `~/code/haqdaar-v2-7.3`. The new branch `step-7.14-talk-rest` is already made and checked out
  (off `step-7.13-talk`, tip `d53b483`). Do all the work on it. Not pushed, not merged.
- The owner's phone check of `d53b483` was good (5 Oct). `step-7.13-talk` is the rollback point: do not touch it.
- Only `.agent/` files, `PROJECT-UPDATE.md` and prompt files are written in `~/code/haqdaar-v2`.
- The two folders share one `.venv` and one `.env`.
- First thing: run `git branch --show-current` there and check it says `step-7.14-talk-rest`.

## What works today (do not rebuild)
- `TALK_ONLY=true` : after the language key the call is talk only. Loop: `haqdaar/engine/talk.py`.
  Prompt: `haqdaar/prompts/talk.py`. Search: `haqdaar/data/scheme_index.py`. Picker glue:
  `haqdaar/engine/talk_pick.py`. Fixed word spotting: `haqdaar/engine/talk_words.py`.
- STRICT TURNS: the agent does not listen while it talks. Words said over it are dropped.
- Already done from B4: live voice pace 1.0 (`LIVE_TTS_PACE`), end-of-speech wait 600 ms
  (`TALK_END_WAIT_MS`), later sentences made while the first is said (`PhoneAudio.warm_text`),
  "one moment" after about 2 s of quiet and again every 4 s, fastest model first (`TALK_MODELS`).
- A caller with no phone: `tools/talk_probe.py` (Mac voice into the real server). Scripts: farmer, vague,
  sidetalk, overtalk, details, vendor, quiet.

## How to run
- My phone: `cd ~/code/haqdaar-v2-7.3 && TALK_ONLY=true make call-me`
- No phone (two terminals):
  `TALK_ONLY=true .venv/bin/python -m uvicorn haqdaar.server:app --port 8001`
  `.venv/bin/python -m tools.talk_probe --script farmer`
- Read a call: `make log-text ID=<call id>`; timeline in `logs/calls/trace/<call id>.jsonl`.

## Hard limits
- Groq: 8,000 tokens a minute and 1,000 requests a day PER MODEL. One talk turn is about 2,000 tokens.
  Three models are chained. Do not fire many real-model turns in a few seconds; wait a minute between
  probe runs if you see `http_429` in `data_cache/reports/groq_usage.jsonl`.
- FREE ONLY for anything new (C7). Sarvam and Groq stay as they are. No new paid tool, no new account.
- One caller at a time. No "model is down" handling. No Marathi work. Keys stay off (I bring them back).
- Do not change what the keys call does: with `TALK_ONLY` off, everything must be as before.
- Never run `make render` without `SNAP=snapshots/CURRENT`. No Muse spend.

## Steps
### B4 (the rest of it) — stage times, and cut the wait
1. Put stage times in the call log for every talk turn: end wait, speech-to-text, search, model, first voice.
   Today only the model time is there (the `act` row's `ms`). Add fields to the `act` row; old log readers
   must keep working. Show them in `tools/log_text.py` as one short line per turn.
2. With those numbers, cut the time from "caller stops" to "answer starts". Today it is about 2 to 3 s.
   Ideas, try the cheap ones first and keep what the numbers prove:
   - play the live voice stream as it arrives, not after the whole sentence is made
     (`haqdaar/audio/live_tts.py` reads the whole stream first);
   - make the first sentence short (the prompt already asks for it);
   - trim the prompt (fewer tokens = faster and more turns a minute).
3. Run the probe scripts. Report the before and after times. PHONE CHECK.

### B5 — cut-in with a strict gate (replaces "does not listen while it talks")
1. Silero VAD (free, 8 kHz) in place of the loudness check in `haqdaar/audio/ear.py`, so a noise is not a voice.
   Check it installs in the shared venv and runs on 20 ms mu-law frames fast enough.
2. While the agent talks: 600 ms of real voice PAUSES the mouth -> speech-to-text -> 2 or more real words ->
   it is the caller's turn (the model may still answer `not_for_me`). Fewer words, or `not_for_me` ->
   the agent says the cut sentence again from its start and goes on. No "sorry".
3. Flag `CUT_IN_GATE` (default off) so strict turns can be switched back on at once.
4. Test with the probe's `during:` step (script `overtalk`) and add a side-talk-during-reply script.
   PHONE CHECK (talk over it; let someone talk near the phone).

### B6 — stress
- (a) The two real calls of 4 Oct 22:38 and 22:41 as replay tests.
- (b) 200 scripted talk calls on the barge-eval rig (side talk, cut-in, quiet, noise at every place).
  Rules: never dead air over 2.5 s, never the same line twice in a row, never a restart, always ends.
- (c) 40 real questions through the real model, spaced so Groq does not refuse: right scheme, truth checks
  pass, reply time. Confirm or change the model order by this score.

### B7 — write up
- `PROJECT-UPDATE.md` and NOTES. Tell me how to run the demo call and what is left for keys.

## Known small faults (fix if cheap, else list them)
- "How much do I pay into Atal Pension" gets "no information": it is not in the scheme text.
- Search is weak on English words written in Hindi letters ("ठेला", "फार्मर"); `talk_words.py` covers the common ones.
- `haqdaar/engine/talk.py` imports `haqdaar.model.answer` (the old house rule says engine imports no model).
- The Hindi word choice is sometimes odd (once "जमींदार" for a farmer who owns land).

## Rules of work
- Follow `AGENTS.md`: keep `.agent/TASK.md` and `.agent/NOTES.md` up to date as you go; smallest correct change;
  never say a check passed without running it.
- Checks before you say a step is done (run in `~/code/haqdaar-v2-7.3`):
  `.venv/bin/python -m pytest -q` (expect all pass but the one old `test_door_a` failure),
  `make stress`, `make barge-eval`, `python3 -m py_compile` on changed files, `python3 sync_vault.py --status`.
- Commit only when I say "commit". Write to me in simple, short words.

Start with B4. Stop after it and tell me what to try on the phone.
