---
title: "Module Brief — Audio"
slug: brief-audio
type: module-note
module: audio
status: reviewed
tags: [brief, audio, owner, staging]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: claude-code
source_file: source-docs/T17.md
---

# Module Brief — Audio

> One of the **four module briefs** [[tickets/T17]] §5 requires and that had never been written.
> *"Nothing authored beside the map; everything zoomed from it."* The 12 narrative segments are
> **retired, not re-cut** — a re-cut segment would be a fourth document restating the map at a
> different resolution.

**Owns:** Telephony · Mouth · Ear. Everything that touches a socket.
**Depends on: nothing.** Audio imports no Engine, no Model, no Data.
**Day-one test:** play a three-file sequence with a terminal mark, take a DTMF mid-play, return
`Digit` carrying `discarded_transcript`, report a `playedStream` timestamp.

## Signature block

```python
Audio.connect(ws)                -> Audio
Audio.select_language()          -> (Lang, LangSource)      # turn 0; two plays then default hi
Audio.say(sequence)              -> None                    # append-only, returns immediately
Audio.repeat()                   -> None                    # re-fires marks
Audio.clear()                    -> None
Audio.on_mark(mark)              -> awaitable[timestamp]    # playedStream — the ONLY completion signal
Audio.next_input(profile)        -> Digit | Speech | Noise | Silence(n) | Hangup
Audio.language                   -> Lang                    # settable
Audio.hangup()                   -> None
```

## The clauses, and the ticket behind each

| Clause | Ticket |
|---|---|
| **Audio's whole outward interface is one settled turn.** It absorbs the endpoint window, the DTMF race, the flush and the ceiling, and surfaces one `Input` | [[tickets/T17]] §1 |
| **Audio never terminates a call.** Surface `Silence(n)`; **Engine** decides | [[tickets/T17]] §2 |
| **`Audio.hangup()` plays nothing.** *Play the closing line, await its mark, then hang up* is Engine's rule — Engine knows which line | [[tickets/T14]] · [[tickets/T17]] |
| **Every line ships with a terminal mark, and every timer starts at its `playedStream`** — never at send. The playback queue holds ~60 s: *"the moment we finish sending is not the moment the caller finishes hearing"* | [[tickets/T14]] 2b |
| **Mouth is append-and-mark, never play-and-wait** | [[tickets/T14]] → [[tickets/T15]] |
| **`repeat()` replays the last sequence verbatim, marks included** — a one-slot buffer. Marks re-fire, so a re-read writes a second `t_name` beside the first | [[tickets/T15]] |
| **`clear()` is keypad-triggered only.** ~200–300 ms of overrun after the keypress, one edge round trip | [[tickets/T14]] 2 |
| **Ignore any mark cleared after a `clear`** | [[tickets/T14]] · seam note |
| **The turn closes on the first *complete* input** — a keypress is complete on arrival, speech only at endpoint | [[tickets/T14]] 5 |
| **`*` and `#` never close a turn. Digits 0–9 do.** This partition keeps `*` from ever being eaten as a box value | [[tickets/T14]] 5 |
| **`#` at turn 0 does not consume one of the two greeting plays** | [[tickets/T14]] |
| **NOISE vs SILENCE.** `vad.speech_start` + empty/span-less final = **NOISE, consumes a cap turn**. No `speech_start` = **SILENCE, does not** | [[tickets/T14]] |
| **`profile` picks the gap:** 4 s at turn 0, 6 s thereafter, **no timer during read-back** | [[tickets/T14]] 3 |
| **On DTMF during speech:** send `flush`, act on the digit, surface the finalised text as `discarded_transcript` | [[tickets/T14]] 5 |
| **Frames are forwarded unbatched** — *the largest single saving in the chain, and it costs nothing* | [[tickets/T14]] 1 |
| **`stream_type="fast"` is not optional** — `balanced` buffers ~1000 ms and puts a full second in front of every turn, invisibly | [[tickets/T14]] 1 |
| **Speech barge-in is available and declined.** *Listen always, interrupt only on keypad.* `audioTrack="inbound"` keeps our own audio off the transcribed leg | [[tickets/T14]] 2 |
| **The language pin is keypad-only, set at turn 0.** `*` re-pins via `config.update` at the next utterance boundary and **clears nothing** | [[tickets/T24]] |
| **`mode="codemix"` on for all three pins, always — and nothing may depend on the flag existing** | [[tickets/T24]] 4 |
| **Render key = `sha256(text ‖ lang ‖ voice_id ‖ tts_model ‖ 8000)`.** Audio reads the manifest; the renderer is **a Data build tool wearing Mouth's name** | [[tickets/T15]] |
| **One file per play call. No slicing.** One loudness pass, 120 ms tail on every file | [[tickets/T15]] |

## Budget you are held to

700 ms endpoint window (the caller's), then **≤1.2 s of ours** from `vad.speech_end` to first byte:
`transcript.final` 150–300 ms · model 300–500 ms · Engine ~0 · Mouth ~50 ms · network 50–100 ms.

Sarvam: `endpointing=vad` · `stream_type="fast"` · `silence_duration_ms=700` ·
`min_speech_duration_ms=250` · `mode="codemix"` · `audioTrack="inbound"`.

## Yours to change without asking

Everything inside `audio/` · the voice id and the TTS vendor (the render key made a swap a
re-render, not a redesign) · every tunable, including `silence_duration_ms`, which
[[tickets/T14]] explicitly wants **tuned on a live stream**.

## Open, and yours to close

- **`keepCallAlive="false"` is ratify-on-hardware** — the one T14 ruling that must be confirmed on
  the first real call. If it drops calls at connect, flip to `true` and bound with
  `streamTimeout="600"`.
- **Sarvam Bulbul's Marathi at 8 kHz is unheard.** A day-one listening check, not a design question.
  Also listen for a **seam between `bundle_confirm_intro` and a chip** at the 120 ms tail.
- **Does Sarvam return the original-language transcript alongside the English hop?** If it does, the
  original becomes a **second LOG field, never a replacement** ([[tickets/T16]]).
- **The 700 ms window has a direction, not a derivation** — the cheapest dial in the system.

## Related
[[03-ARCHITECTURE]] · [[04-INTERFACES]] · [[notes/audio/overview]] · [[tickets/T01]] ·
[[tickets/T03]] · [[tickets/T14]] · [[tickets/T15]] · [[tickets/T19]] · [[tickets/T24]]
