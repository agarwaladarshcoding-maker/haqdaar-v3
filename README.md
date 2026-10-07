# Haqdaar

A phone line that tells a caller about government schemes they may have a right to.

- The caller **talks** in their own language (Hindi, Marathi, English, Gujarati, Tamil), or uses **keys**.
- A **photo** (a crop, a paper) can come in by **SMS** from a keypad phone. The model reads it. A person answers when the model is not sure.
- A **call-back** that is not picked up, is cut, or drops sends the answer by SMS, as text plus a sound link.
- The line knows **51 schemes**: 17 live ones (keys and talk) and 34 new ones from the team (talk only).

Start with `HANDOFF.md`. The design is the flow charts in `flow/`. The order of work is in `PLAN.md`.

## Try everything: one command

```
make full
```

This is the universal command. It starts everything with every switch on, on this Mac (mic and
speakers, no phone, no Twilio). **Use headphones.** It asks which call-back case to play:
1 = picked up, 2 = not picked up, 3 = picked up but the call drops.

What `make full` turns on:

| Part | What it does |
|---|---|
| 51 schemes | the 17 live + 34 new talk-only schemes, from `data_cache/intake/` (`LIVE=1` goes back to the old 17) |
| Talk | the model talks in the caller's language; English in the middle, so the model works in English |
| Language switch | the caller can ask for a language in words; the greeting offers five languages |
| Keys | key 6 offers keys; keys also work inside a talk call |
| Cut-in | the caller can speak over the voice (headphones only; `CUT=0` turns it off) |
| Photo desk (port 8002 page, 8003 desk) | photo by SMS (door 0), the web link and the old H: way; Muse reads the photo; auto approve when sure |
| Phone page (port 8080) | the keypad-phone SMS photo sender |
| Call-back | rings back on the Mac when the photo answer is ready; the sound link goes out by tunnel |
| Call-back watcher | starts only if `.env` has `PHOTO_BACK_URL` (real phone). Not needed on the Mac |

Switches: `LIVE=1` old 17 schemes, `CUT=0` no cut-in, `PORT=8001` the call port, `BACK_WAIT=0` seconds to wait before the call-back.
Stop the helpers with `make full-stop`. Logs go to `logs/` (`server.log`, `photo-desk.log`).

Muse costs a few paise a photo and has a day cap of Rs 30. Run `make muse-status` first.
`PHOTO_READER=stand-in` reads photos for free (a fake reader).

## How a call goes

1. A greeting in short Hindi, Marathi and English. Press 6 for keys.
2. Talk: the model asks the caller about themselves (state, work, age, family). It asks one thing at a time and takes only what it needs. A picker (a small search over the schemes) cuts the list down. The caller can also name a scheme and ask about it.
3. The model says the schemes that fit, what each gives, and what to do next. It speaks from the scheme card, never from memory.
4. A photo: the caller gets an SMS link or sends a photo from a keypad phone. The call ends after the link. When the answer is ready, the system rings back (or sends an SMS with a sound link).

One caller at a time. This is built for one phone line, not for many callers at once.

## Photo by SMS (the doors)

- **Door 0**: the keypad-phone app cuts the photo into small SMS pieces (`P:` packets). The server joins them (`haqdaar/keypad_sms/`). Pieces can come late, twice, or never; a lost photo goes to a person at once.
- **Door 1**: the web link `/p/<token>`, and the old `H:` way. They work as before.
- A case lives in `haqdaar/photo/cases.py` (one lock, saved on disk). A case that waits for a person lives up to 72 hours.
- On restart the desk picks up stuck cases (`_recover_stuck`).
- The desk (`tools/photo_desk.py`) shows each case: the photo, what the model read, and a button to approve or write the answer.

## Commands

| Command | What it does |
|---|---|
| `make full` | everything on (see above) |
| `make full-stop` | stops the photo desk, phone page, watcher and tunnel |
| `.venv/bin/python -m pytest -q` | all tests (3636 pass) |
| `make talk-eval` | scripted talk calls: side talk, cut-in, noise, a key, a hang-up at every place; no network, no money |
| `make stress` | random keypad callers; 0 crashes and 0 wrong answers is the bar |
| `make mac-call` | talk on this Mac, nothing else started |
| `make sms-door` / `make sms-try PHOTOS="a.jpg b.jpg"` | try door 0 with a stand-in phone; open http://127.0.0.1:8013 |
| `make stage-check` | says what is ready before a demo call; places no call |
| `make call-me` / `TALK_ONLY=true make call-me` | rings the owner's phone (needs a valid Twilio token in `.env`) |
| `make calls-ui` | each call as a back and forth with timings (port 8001) |
| `make muse-status` | the Muse money guard |
| `make intake` | rebuilds the 34 new schemes into their own snapshot (free, no network) |
| `make render YES=1 SNAP=...` | makes the real voice for a snapshot (spends Sarvam money; always give `SNAP`) |

## Adding schemes

The team's schemes are written down in `data_cache/intake/`. `make intake` checks each one (every
quote must be found in the source, every code must be valid) and builds an isolated snapshot in
`data_cache/intake/snaps/`. It never changes `snapshots/CURRENT`, the old 17.
New schemes are **talk only**: they are not offered by keys. Schemes for organisations (six of them) are not listed to a person
unless the caller says organisation, startup, company or NGO, or names the scheme.
The format is in `.agent/INTAKE-FORMAT.md`.

## Known limits

- Age bands are coarse: a few schemes (PMJJBY, PMSBY, PM-Vikas, National Youth Award) can be listed to a caller whose age band only overlaps; the model says the exact limit from the card.
- Half-joined SMS photos are lost on a restart (the join is in memory).
- `/sms` has no login yet (no real SMS gateway); the stand-in route trusts the sender in the request.
- A real phone call needs a valid `TWILIO_AUTH_TOKEN` in `.env` (the last `make call` got HTTP 401).
- The embed model (`paraphrase-multilingual-MiniLM-L12-v2`) downloads on first start; the first start can take about a minute.

## Folders

- `haqdaar/`: the app. `audio/` (voice clips), `engine/` (talk loop, question picker, filter), `model/`, `prompts/`, `data/` (schemes, search, snapshots), `keypad_sms/` (SMS join), `photo/` (cases, reader, in-call, call-back message), `server.py`.
- `keypad_app/`: the keypad-phone SMS photo sender (one page, under 20 KB).
- `tools/`: helper programs (`mac_call`, `photo_desk`, `photo_back`, `intake_build`, evals).
- `tests/`, `fixtures/`: checks and test data.
- `snapshots/`, `data_cache/`, `audio/`: the scheme data the app reads and the voice clips. `snapshots/CURRENT` is the old 17; `data_cache/intake/snaps/CURRENT` is the 51.
- `flow/`: the flow charts (talk, cut-in, keys, photo, call cost) and the script that draws them.
- `docs/old-design/`: five design papers from September. Background only; `PLAN.md` wins.
- `.agent/`: the task list and notes of the work.
