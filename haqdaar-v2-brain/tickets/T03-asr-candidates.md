---
title: "T03 asset · ASR candidate findings"
slug: T03-asr-candidates
type: ticket
module: architecture
status: open
tags: ["ticket", "module/architecture", "status/open", "type/ticket"]
created: 2026-09-06
updated: 2026-08-24
author: Adarsh Agarwala
last_agent_edit: sync_vault.py
source_file: source-docs/T03-asr-candidates.md
blocked_by: []
blocks: []
---

# T03 asset · ASR candidate findings

Gathered 23 Aug 2026 from vendor documentation and independent benchmarks. Everything below is desk research; nothing has been tested against real 8 kHz Indian call audio. Where a number decides something, the source is named.

## The headline

**No candidate returns a usable per-utterance transcript confidence.** The three languages are all servable; the confidence number the design assumed is the thing that isn't there.

| | Marathi | 8 kHz native | Streaming | Transcript confidence | Code-mixed | Cost/min |
|---|---|---|---|---|---|---|
| **Sarvam (Saaras v3)** | yes, first-class | yes, trained on it | yes, WS, 8000 accepted | **no** — only `language_confidence` | `mode="codemix"` | ~₹0.50 (₹30/hr) |
| **Deepgram (Nova-3)** | yes, monolingual only | resamples | yes, best-in-class latency | **yes**, word-level, calibrated | Marathi **excluded** from code-switch set | $0.0077 mono / $0.0092 multi |
| **Google STT V2 (Chirp 3)** | yes, but check streaming list | telephony model is EN-centric | yes | returned but "not confidence in the conventional sense" | via auto-detect | $0.016, **15 s rounding** |
| **Bhashini** | yes | no — degrades on 8 kHz | WS exists | not documented | weak | free / negligible |
| **Whisper (hosted)** | effectively no | no | no | no (logprobs only) | poor | varies |

## Per candidate

### Sarvam — Saaras v3 / `saaras:v3-realtime`

The only candidate purpose-built for the exact conditions HAQDAAR runs in.

- Marathi (`mr-IN`) is a first-class language, not an afterthought — Sarvam markets Marathi telephony accuracy as a differentiator against global models.
- 8 kHz is native, not tolerated: models are trained on compressed call-centre audio. `sample_rate` accepts `8000` or `16000` on the realtime WebSocket; `mulaw` and `alaw` encodings are accepted directly, which means no transcode between the telephony leg and the ASR.
- Realtime endpoint `GET /speech-to-text-realtime/ws` gives true partial transcripts, `vad.speech_start` / `vad.speech_end` events, and three VAD knobs in milliseconds (`threshold`, `silence_duration_ms` default 500, `min_speech_duration_ms` default 250). `stream_type="fast"` is the documented setting for conversational agents. Mid-call `config.update` can switch language or mode at the next utterance boundary without reconnecting.
- Code-mixing is a named feature with its own output mode (`codemix`), plus `translit` for Latin-script output.
- **Confidence: not returned.** The documented `transcript.final` payload carries text, optional timestamps, and — only when `language_code="auto"` — a detected `language` plus `language_confidence`. That number scores *which language was spoken*, not *how sure the model is of the words*. Independently corroborated: the LiveKit Sarvam plugin hardcodes `SpeechData.confidence = 1.0` for every transcript, and the open issue arguing to fix it proposes threading `language_probability` through — i.e. the only number available is the language one.
- Pricing ₹30/hour (~₹0.50/min), billed per second, rounded up per request. ₹100 free credits on signup. Starter plan is 60 req/min, which is a real constraint if each turn is a separate REST call — the persistent WebSocket avoids it.
- Notable: Sarvam publishes a "Government Scheme Agent" cookbook example. Worth reading before T11 and T15.

### Deepgram — Nova-3

The only candidate with the confidence number the design wanted, and it can't cover the language set the way HAQDAAR needs.

- Marathi (`mr`) arrived on Nova-3 **monolingual** models in January 2026, with accuracy improvements shipped in May 2026. Real, recent, production-labelled support.
- The catch: Nova-3's real-time **code-switching** model covers ten languages — English, Spanish, French, German, Hindi, Russian, Portuguese, Japanese, Italian, Dutch. Marathi is not among them. So Hindi↔English mid-sentence is handled; Marathi↔English is not. A Marathi caller who says "मला scheme बद्दल माहिती पाहिजे" is exactly the case that falls between the two models.
- Confidence is word-level, well-calibrated, and returned by default — genuinely the strongest in the field, and the reason Deepgram stays on the list as a fallback.
- Streaming latency is the category benchmark; per-second billing, no rounding penalty on short turns.
- $0.0077/min streaming monolingual, $0.0092/min multilingual, $200 free credit.
- Not trained on Indian telephony specifically. Marathi accuracy on degraded 8 kHz rural audio is unmeasured and should not be assumed from the language-support table.

### Google Cloud STT V2 — Chirp 3

- Broadest language coverage, and `asia-south1` (Mumbai) is a supported Chirp 3 region, which helps round-trip latency.
- Two documented traps. First, Chirp 3's language list for `StreamingRecognize` is **narrower** than for `BatchRecognize` — Marathi must be confirmed on the streaming list specifically via the locations API before this is viable, not from the marketing page.
- Second, confidence is a mirage. Google's own reference says the field "is not guaranteed to be accurate and users should not rely on it to be always provided," with `0.0` as a sentinel for unset. For Chirp 3 specifically, independent profiling notes word-level confidence is returned but is not confidence in the conventional sense. Building a 0.50/0.85 ladder on this is building on sand that also happens to be labelled sand.
- The legacy `telephony` model, the one actually tuned for 8 kHz, is English-centric — it does not cover this language set.
- $0.016/min, and Google bills in **15-second increments rounded up**. A caller answering "हो" costs a full 15 seconds. Across 5–6 short turns per call this is the worst per-call economics of the five despite a middling headline rate.

### Bhashini

- Covers all three languages, has a WebSocket ASR path, is free-to-negligible, and carries obvious policy alignment for a government-scheme product — a genuine consideration at sale time, though not a design input.
- Independent assessment is explicit that WER spikes significantly on heavy telephony audio (8 kHz, codec-degraded) and that aggressive code-switching where Hindi–English boundaries occur every few seconds is a weak spot. Those are precisely HAQDAAR's two operating conditions.
- Documented pipeline examples use `samplingRate: 16000`. No per-utterance confidence in the ULCA response shape.
- Verdict: keep as a political and cost story, not as the primary ear.

### Whisper (hosted)

Ruled out on evidence, not on preference.

- Marathi is a documented failure case: Whisper large-v3 measured at 73.8% WER on a Marathi test set; even on clean read speech (FLEURS) Marathi CER is 24.3. Hindi lands around 20–27% WER on real-world audio. That is before any 8 kHz degradation.
- No native streaming, no true confidence (only `avg_logprob` / `no_speech_prob`, which are not calibrated probabilities of correctness), and a documented hallucination-on-silence failure mode that is actively dangerous in an IVR where silence is common.

## What this means for the confirmation ladder

The 0.50 / 0.85 gates cannot be sourced from the ASR. Three ways out:

1. **Explicit-confirm every speech turn** (the ticket's stated fallback). Costs one extra turn per question. Against a 5–6 question budget and a 20-second read-back bar, this roughly doubles call length. Rejected.
2. **Switch to Deepgram for its confidence number.** Buys a real, calibrated score and loses Marathi code-switching plus Indian telephony training. Trading the primary language requirement for a secondary mechanism. Rejected as primary.
3. **Compute the score ourselves.** HAQDAAR never needs an open-vocabulary transcript. Every speech turn resolves to a value in a closed set — a scheme name, a state, an occupation, a yes/no. So score the *match*, not the *audio*: run the transcript against the allowed set for that slot and gate on match margin (top candidate's score, and its distance from the runner-up). This is a number we own, we can tune, we can log, and — critically — we can put in the LOG as part of the proof the acceptance bar demands. An ASR-supplied float never could.

Option 3 also degrades gracefully: an ambiguous match is a *specific* re-ask ("did you say Ladki Bahin or Ladka Bhau?") rather than a generic "sorry, say that again", which is a better call anyway.

## Recommended configuration

- `saaras:v3-realtime` over WebSocket, `sample_rate=8000`, `encoding=mulaw` (or `alaw`) matched to the telephony leg from T01.
- `stream_type="fast"`, `endpointing="vad"`, `silence_duration_ms` to be tuned in T14 — 500 ms default is likely too slow for a keypad-first IVR.
- `language_code` pinned per call to `hi-IN` / `en-IN` / `mr-IN` rather than `auto`. Pinning costs the `language_confidence` field, which is no loss since we aren't using it, and buys accuracy.
- `mode="codemix"` or `translit` for slot-filling turns, so matching happens against a stable script. To be settled in T11.
- Deepgram Nova-3 monolingual retained as the named fallback if Sarvam's Marathi disappoints on real audio.

## What desk research cannot settle

Every accuracy claim above is the vendor's or a third party's, on their audio. Marathi on genuinely degraded rural 8 kHz remains unverified. The cheapest possible check — twenty recorded Marathi utterances pushed through Sarvam and Deepgram at 8 kHz — should happen before T17 freezes the Audio interface.


---
**Module Overview:** [[notes/architecture/overview|Architecture Module]] · **Wayfinder Map:** [[maps/wayfinder-map|Latest Map]]
