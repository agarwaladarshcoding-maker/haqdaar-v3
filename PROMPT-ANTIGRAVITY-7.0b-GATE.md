# STEP 7.0b — The gate: keys and words at the wrong moment (Antigravity work order)

Plain goal: a caller presses keys twice, presses a random key, presses a key in a gap, or speaks
and then presses. Today some of these answer a prompt the caller never heard. This step puts
**one gate** in the audio layer so that fixed rules, in code, decide what each key or spoken turn
belongs to. The engine (`call.py`) stays one thread with fixed rules. No model is used here.

Do this step **before** 7.1. No switch: these are bug fixes on real calls. Speech cutting into a
playing clip is **not** in this step (that is 7.2); the gate must only leave room for it.

## 0 · Setup
```
cd ~/code/haqdaar-v2
git branch --show-current     # must print: step-7.0-live-answers   (wrong branch -> STOP)
make test                     # write down the pass count before you change anything
```
Leave Claude's uncommitted doc files alone. Read first: `AGENTS.md`, `HANDOFF.md`, and
`.agent/NOTES.md` from "Owner's steer: own-language transcript + cut-ins" to the end.

## 1 · What is there today (all read from code by Claude, 3 Oct; check each before you rely on it)
| Fact | Where |
|---|---|
| Keys sit in one unbounded queue, never dropped, no mark of which prompt they came at | `haqdaar/audio/turn.py:30`, 84-88 |
| If a key is waiting, `say()` skips the next clip and the key answers it | `haqdaar/audio/phone.py:75-78` |
| Key during the router call -> read-back skipped -> key taken as yes/no on the read-back | `haqdaar/engine/call.py:656-662` |
| A key stops a clip (`Turn.push_key` -> `Mouth.clear` -> Twilio `clear`) | `turn.py:34-41`, `haqdaar/audio/mouth.py:69-75` |
| Speech during a clip is buffered, then dropped | `turn.py:112-113`, `haqdaar/audio/ear.py:580-601` |
| Hangup goes into the key queue as `"h"` and can come back as `Digit("h")` | `turn.py:43-47`, `ear.py:629-633` |
| A stale dtmf event can return the wrong digit | `ear.py:674-684`, 593-594 |
| Up to 1 s of sound after a clear (`FRAME_BYTES=8000`) | `mouth.py:107-110` |
| Listening can start on a clock guess before the clip ends | `mouth.py:86-91` |
| The engine does not know how much of a clip was heard; `sections_heard` is set when queued | `phone.py:91-92`, `call.py:1114-1120` |
| Hangup paths return without `log.close` | `call.py:367-369`, 871-872, 1078-1080 |
| Input types | `haqdaar/contracts/types.py:106-117` |
| Fake audio for tests | `haqdaar/sim.py:182-268` |

## 2 · The rules (the owner agreed to these on 4 Oct)
Every prompt gets a number, `prompt_n`. It goes up by one when the next prompt **starts to
sound**. Every key and every spoken turn is stamped with the `prompt_n` it came at.

| # | Case | What must happen |
|---|---|---|
| G1 | Key while the prompt's clip plays | Clip stops, the key is the answer (as today) |
| G2 | The same key again within `KEY_REPEAT_MS` (300) | Counts once; the rest are dropped, however many |
| G3 | Other keys after a key was taken for this prompt (2, 3, 10 of them) | First one counts; **all** later ones are dropped until the next prompt sounds |
| G4 | Key in the gap: the prompt is closed and the next has not started | Dropped. The next prompt plays in full |
| G5 | Key in the first `KEY_GUARD_MS` (250) of a new prompt | Dropped (it was meant for the one before) |
| G6 | Key that is not on this prompt's menu (random key) | Play the "wrong key" line, then the same prompt again. Today's strike count stays as it is |
| G7 | Caller speaks, then presses a key before the read-back starts | The key wins. The spoken words and any router reply for them are thrown away |
| G8 | Key while the line is busy with a key answer (no speech in flight) | Dropped (same as G4) |
| G9 | `#` (repeat), `*` (language), `0` | Same rules as any key: one per prompt |
| G10 | Hangup at any moment | Its own event. Never a key. The log is closed on every hangup path |
| G11 | Clip cut by a key | The trace says which clip was cut and after how many ms. "Heard" means played to the end |

One prompt takes one answer. A key that is dropped is **never** silent: it is logged (2c).

## 3 · Build
### 3a · Tunables (`haqdaar/contracts/tunables.py`)
1. `KEY_REPEAT_MS = 300`, `KEY_GUARD_MS = 250`.

### 3b · The gate (`haqdaar/audio/turn.py`, `phone.py`, `ear.py`, `mouth.py`)
2. `Turn` keeps `prompt_n` and whether the prompt is open or closed. It goes up when `say()` starts
   a prompt clip (not for a clip that is skipped). `push_key` stamps each key with `prompt_n` and
   the time. `wait_input` gives back only a key that passes G2-G5 and G8; the rest are dropped
   and logged.
3. `PhoneAudio.say` must **not** skip a clip because a key is waiting (`phone.py:75-78`). After
   the gate, a waiting key is either valid for the open prompt or already dropped.
4. G7: when a key stamped for the open prompt arrives while speech is being recorded, at the
   speech service, or at the router, the key is the answer. Recording and speech-service cases
   exist today (`ear.py:649-653`, 701-705, 713-718). For the router case, the engine must look
   for such a key **before** it uses the router's reply. Add one small method on the audio
   object, e.g. `pending_key() -> Digit | None`, and one check in `call.py` after `model.turn`
   and `model.opener` return (guard with `hasattr`, the test fakes do not have it).
5. G10: hangup is not put in the key queue. Fix `Digit("h")`. Add `log.close` on the hangup
   paths in `call.py`.
6. Fix the wrong-digit race at `ear.py:674-684`: return the key that was taken from the queue.
7. `Mouth`: send frames of at most 200 ms so a clear takes effect fast. Listening starts when
   the last mark comes back, with the clock guess only as a time-out. Check the clip length
   math still holds.
8. G11: `Mouth.clear` returns (or records) the clip that was playing and the ms played, from
   the marks and the clock. `PhoneAudio` writes it to the trace. Mark a results section as
   heard only when its clip played to the end. If this needs more than about 20 lines in
   `call.py`, stop and report.
9. Leave room for 7.2: `Digit` and `Speech` get optional fields with defaults, so nothing that
   builds them today breaks: `prompt_n: int = -1`, `cut_clip: str = ""`, `heard_ms: int = -1`.

### 3c · The log: every event, so the system has the full story of the call
10. One trace line per input event, taken or dropped (`haqdaar/data/trace.py`):
    `{ts, prompt_n, prompt, event: key|speech|hangup, value, took: true|false, why, cut_clip, heard_ms}`.
    `why` is one of: `ok`, `repeat`, `prompt_closed`, `guard`, `not_on_menu`, `key_beat_speech`.
    For a dropped spoken turn, `value` is the text if there is one.
11. The call page (`tools/call_viewer`) shows dropped events as a grey note. Smallest change.

### 3d · The "wrong key" line (G6)
12. Find out what a caller hears today on a key that is not on the menu, in each profile (box
    menu, read-back, results menu, anything-else). Report it.
13. If a recorded line for "that key is not on the list" exists in the pool, play it before the
    prompt comes again. If none exists, **do not render one**. Reuse the closest existing line
    and report the text needed in hi, mr and en; Claude and the owner will add the clip.

### 3e · Fake audio (`haqdaar/sim.py`)
14. `FakeAudio` must be able to script timing: a key during a clip, a key in a gap, two or five
    keys in a row, a key after speech. Keep today's scripts working unchanged.
15. `call.py` and `sim.py` must still not contain `Thread`, `asyncio`, `Queue`, `Pool`, and
    `call.py` import lines must not contain `audio`, `model`, `pipeline`
    (`tests/test_call.py:1009-1030`).

## 4 · Tests (fakes only; no real HTTP)
One test per row G1 to G11, named after the row. Plus:
- five fast presses of `1` at a box question -> one answer, four dropped, four log lines;
- `1` then `2` then `3` fast -> `1` taken, two dropped;
- key in the gap -> the next prompt's clip is played (not skipped), and the key is not its answer;
- speech, then a key while the fake router is "thinking" -> the key is the answer, no read-back
  of the spoken value;
- a random key at each of the four profiles -> the same prompt comes again;
- hangup mid-clip and mid-router -> no `Digit("h")`, log closed.
```
make test          # all pass, 0 fail, more tests than before
make sim           # ends at closing_farewell
make stress        # crashes 0, truth failures 0
python3 -m py_compile haqdaar/audio/turn.py haqdaar/audio/ear.py haqdaar/audio/mouth.py haqdaar/audio/phone.py haqdaar/engine/call.py
```

## 5 · Records and hand-back
- Append what you learn to `.agent/NOTES.md` as you go.
- Do not edit `haqdaar-v2-brain/` or `source-docs/`. Claude writes the rule changes at review.
- No commit, no merge, no push, no tag. Leave the work in the tree; Claude checks and fixes it.
- Reply with: files changed, test counts before and after, what item 12 found, and anything
  you could not do.

## 6 · Do not
- Do not let speech stop a playing clip. Do not change the voice detector thresholds. That is 7.2.
- Do not change any key map or any menu.
- Do not add a number-word map ("एक", "one").
- Do not run bulk Sarvam renders, `make pipeline-extract`, or spend Muse.
- Do not start or stop the owner's `make dashboard`; do not use ports 3000, 3210, 8001.
- Do not place a phone call. Do not print, log or commit any API key or phone number.
