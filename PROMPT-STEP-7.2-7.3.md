# STEP 7.2 and 7.3 — work order (written by Claude, 4 Oct; the owner said: build all of step 7)

Read first: `AGENTS.md`, `PROMPT-ANTIGRAVITY-7.1-QUESTIONS-TEXT.md` (the 7.1 design this builds
on), `PROMPT-ANTIGRAVITY-7.0b-GATE.md` section 2 (key rules G1-G11), and `.agent/NOTES.md` from
"Plan stress test + Sarvam streaming" to the end.

Shared names already in the tree (do not rename): `tunables.QA_ENABLED, ENGLISH_PIPE, QA_SPEAK,
SPEECH_CUT_IN, QA_SEARCH, QA_TTS_TIMEOUT_S, CUT_IN_MIN_MS` (all switches default false);
`types.Question`, `Answer.also_question`, `Speech.lang`, `Speech.english`, `Speech.cut_clip`,
`Speech.heard_ms`. **With every switch off the call must behave exactly as before.**

## 7.2 · Audio side (files: `haqdaar/audio/*`, `haqdaar/server.py` only if needed)

### A · Two gaps left from 7.0b
A1. `prompt_n` goes up when `say()` queues, not when the clip sounds. So when the engine queues
    several things at once (results: preamble, scheme 1, scheme 2, anything_else), a key or a
    hangup during scheme 1 is stamped with the last one. Fix in the audio layer: the stamp on a
    key / hangup must be the prompt that is **sounding** at that moment (use the Mouth's clip
    schedule and marks). A key pressed while an earlier queued prompt sounds stops the line and
    is judged against what the engine waits on next, exactly as today (do not drop it: today
    `1`/`9` pressed during the results reading is how the caller moves on). Only the trace
    stamp (`prompt`, `cut_clip`, `heard_ms`) must name the clip that was really playing.
A2. `PhoneAudio.was_cut()` exists. Add `heard(token) -> bool`: True only if a clip of that token
    played to its end (its mark came back, or its scheduled end passed with no clear).
    The engine side will call it with `hasattr`.

### B · English pipe at the ear (7.1 items 25, 26)
B1. `ENGLISH_PIPE` on: `SarvamSTT.transcribe` sends `mode: "translate"`; the language code stays
    the caller's language. The `Speech` it gives has `english=True` and `lang` = what Sarvam
    heard. Off: the request is byte-for-byte as today (test it with a fake HTTP).
B2. The Groq whisper backup gives the caller's language: `english=False`.

### C · Saying an answer aloud (`QA_SPEAK`)
C1. New `haqdaar/audio/live_tts.py`: `speak(text, lang) -> bytes | None`, mu-law 8000 Hz, from
    Sarvam `bulbul:v3`, the same voice as the recorded lines (see `haqdaar/audio/render.py:113`
    and `.agent/tts_stream_draft.py`: HTTP `/text-to-speech/stream` gave first bytes in 0.64 s,
    the websocket in 0.3 s). Check the bytes are raw mu-law with no header (strip a WAV header if
    there is one). Clean the text first: "‑" -> "-", "%" -> the word for percent in that
    language, no markdown. Total time-out `QA_TTS_TIMEOUT_S`. Never raises; failure -> `None`.
C2. Same text + language + voice -> the same sound: keep answers in the audio pool by the same
    content key the pool uses (`haqdaar/audio/pool.py`), so a repeated answer is free.
C3. `PhoneAudio.say_text(text) -> bool`. Only when `tunables.QA_SPEAK` is on; when off the
    method returns False at once and plays nothing. On: get the sound (pool, else `speak`),
    play it through the Mouth as a prompt clip named `answer` (so the gate, `#` repeat, cut by a
    key and the trace all work), return True. No sound in time -> False.
    If streaming straight into the Mouth is simple and safe, do it (first sound sooner); if not,
    fetch whole and play. Say which you did.
C4. This spends Sarvam money per answer. Log one line per live render (chars, seconds, cached
    or not) through the existing log callback. **Do not spend Muse. No bulk renders.** In tests
    use a fake `speak`; `tests/conftest.py` blocks real HTTP.

### D · The caller's voice stops a playing clip (`SPEECH_CUT_IN`)
Rules (fixed, no model):
| # | Case | What must happen |
|---|---|---|
| S1 | Voice for `CUT_IN_MIN_MS` (400) or more while a prompt clip plays, on profiles `spoken`, `confirm`, `readback` | The clip stops. The line listens until the caller finishes. One `Speech` is given, with `cut_clip` and `heard_ms` set |
| S2 | Voice shorter than that (cough, "hm") | Nothing stops. Not logged as a turn (one trace line, `took: false, why: "short_voice"`) |
| S3 | Voice in the first `KEY_GUARD_MS` of a prompt | Ignored (same guard as keys) |
| S4 | A key at any time during or after the voice, before the engine uses the words | The key wins (G7), the words are dropped and logged |
| S5 | Voice while the greeting (`turn0`) or a results/scheme reading on profile `normal` plays | Not heard, as today |
| S6 | Keypad-only mode | Not heard, as today |
| S7 | Voice while an `answer` clip (C3) plays | Same as S1: the caller can cut the answer |
| S8 | Hangup | Its own event, as G10 |
D1. Use the existing voice detector and thresholds; do not retune them. The line's own sound
    must not trigger it: Twilio sends only the caller's side, but add a simple guard anyway
    (need `CUT_IN_MIN_MS` of voice in a row) and say in NOTES what you could not test without a phone.
D2. Profile `readback` (the results menu) listens for speech on a real phone **only when
    `QA_ENABLED` is on** (7.1 rule 11 said 7.2 opens it). Off: as today.
D3. Every event gets a trace line as in 7.0b (`event: "speech"`, `took`, `why`).

### Tests (fakes only): one per row S1-S8, A1, A2, B1 (off = same request; on = translate),
C3 (off -> False and nothing played; on with fake speak -> a clip named `answer` is played and
a key cuts it; `speak` None -> False), cache hit does not call `speak` twice.

## 7.3 · Search, the read-back turn, saved answers (after 7.1 is in the tree)
E1. `QA_SEARCH` on: when the caller's question names no scheme and more than `QA_MAX_SCHEMES`
    survivors are left, pick up to `QA_MAX_SCHEMES` schemes by plain word overlap between the
    question (English when `ENGLISH_PIPE`, else the caller's language) and each speakable
    scheme's card. Stdlib only, no embeddings, no index on disk. Fewer than 2 shared content
    words -> no schemes -> no answer (today's path). New file `haqdaar/data/scheme_search.py`.
E2. A scheme named in the question (existing alias lookup, `haqdaar/engine/door_a.py`) always
    wins over search and over the survivors.
E3. A question at the confirm read-back turn ("is it X? yes or no"): when `model.confirm` is
    None and `model.sort` says QUESTION, try the question, then say the same read-back again.
    No strike, no turn. Smallest change in `call.py`.
E4. Saved answers: `haqdaar/data/answer_store.py`, a JSON-lines file in `tunables.REPORTS_DIR`
    keyed by (snapshot id, language, sorted scheme ids, question text lower-cased and stripped
    of punctuation). A hit skips the model call and gives the saved text (which already passed
    the checks). Only answers that passed every check are saved. Load once per process.
E5. Tests with fakes for E1-E4; switch off -> nothing changes.

## Do not
- Do not commit, merge, push or tag. Do not edit `haqdaar-v2-brain/` or `source-docs/`.
- Do not place a phone call. Do not print or log any API key or phone number.
- Do not use ports 3000, 3210, 8001. Do not run `make pipeline-extract`, bulk renders, or Muse.
- `call.py` and `sim.py` must not contain `Thread`, `asyncio`, `Queue`, `Pool`; `call.py`
  import lines must not contain `audio`, `model`, `pipeline` (`tests/test_call.py:1009-1030`).
- Append what you learn to `.agent/NOTES.md` under your own heading as you go.
