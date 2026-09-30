# HAQDAAR v2 — Brief for Muse Spark 1.3 Contributor

## 1. What HAQDAAR Is
HAQDAAR is a phone helpline for rural and informal-work families in Maharashtra. A caller dials in from any phone. The system asks a few simple questions in Hindi, Marathi, or English using keypad presses (digits 0–9). It filters government schemes against the caller's answers, and reads out the matching schemes.

Core commitments:
- It never lies, never hallucinates eligibility, and never says "you are eligible" (it says "these schemes fit your profile").
- It never hangs up on the caller.
- Keypad first: callers navigate via DTMF digits.

---

## 2. Current State and Verification Results

### What is done (from HANDOFF.md §3)
- **Phase 0 & 1:** Done and merged. Pipeline turns myscheme pages into cards, keypad engine complete.
- **Phase 2:** Done in code for 12 schemes. Includes Sarvam audio (477 clips), snapshot, pool with LRU memory caching (0 leaking fds), telephony abstraction, Twilio media stream handler, Mouth playback with barge-in, Turn listener, and FastAPI `/stream` WebSocket server.
- **Phase 3 so far (30 schemes: 12 existing + 18 new central):**
  - `3.1`: `p0_discover.py` found 746 central schemes on myscheme (510 individual).
  - `3.2`: 30 schemes selected in `haqdaar/data/pipeline/schemes.yaml`.
  - `3.3`: Scraper upgraded with Chrome and listing metadata (`level`, `ministry`); 28/30 scraped (`ab-pmjay` missing from site; `pmsby` lacks documents).
  - `3.4`: Meta Muse Spark 1.3 Contributor client implemented (`muse.py`) for extraction, cards, translation with ₹60 cap and ledger.
  - `3.8`: Audio pool pins only fixed lines (6.7 MB); scheme audio loads on demand.
  - `3.6`: 1,000 caller stress simulator built (`tools/stress.py`).

### Verification checks run today (30 Sep 2026)
- **Git state:** Branch `step-3.2-choose`, clean working tree, up to date with remote origin.
- **Keys in `.env`:** `MUSE_API_KEY`, `SARVAM_API_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_US_PHONE_NUMBER`, `HF_TOKEN`.
- **Pytest:** 307 passed, 0 failed (19.86s).
- **Stress test (`make stress`):** 1,000 simulated callers:
  - `crashes 0   truth failures 0`
  - Questions per call: median 1.0, max 4
  - Schemes read per call: median 2.0, max 9, none 50
  - Stop reasons: 820 `survivors_le_4`, 124 `no_split`, 2 `zero_survivors`
  - Scheme endings: 1,711 `direct_match`, 601 `overflow`, 2 `widened_match`
- **Sim call (`make sim SNAP=snapshots/CURRENT KEYS="2 1 0 0 0 1 1 h"`):** Reached `closing_farewell`, log written to `logs/sim_1790785597.jsonl`.
- **Muse spend:** ₹3.93 spent out of ₹60 hard cap (`data_cache/reports/muse_usage.jsonl`).

---

## 3. What Is Left (in order, from HANDOFF.md §4)

### Phase 3 (30 schemes)
1. **Step 3.4-finish (Extract & Cards):**
   - Run `make pipeline-extract` (facets via Muse) and `make pipeline-cards` (English cards via Muse).
   - Check quarantine rate is under 15%.
   - Ensure the final occupation list has at most 9 values (`KEYPAD_CARDINALITY_MAX = 9`).
   - Add Hindi and Marathi translations in `vocab.LABELS` for any new occupations.
2. **Step 3.5 (Translate & Gates):**
   - Run `make pipeline-translate` (Muse; enforce standard 0–9 digits).
   - Run `make pipeline-gates` (G1 numbers, G2 forbidden phrases, G3 length, G4 Devanagari script, G5 completeness).
   - Run `make snapshot` (build snapshot from schemes with audio; missing clips must never enter snapshot).
   - Voice clips for the 18 new schemes come later once owner confirms voice choice.
3. **Step 3.7 (Audit):**
   - Check 20 cards against source pages; owner listens to audio samples.

### Phase 4 (Voice dialogue)
- Steps 4.1–4.5: Speech-to-text (Sarvam/Groq Whisper), intent model, Door A (scheme name direct entry), spoken answers with confirmation, fallback to keypad if voice fails.
- **Rule:** Muse must NEVER hear live caller speech or text (contributor tier data retention policy).

### Phase 5 (Make it solid)
- Steps 5.1–5.4: "Anything else?" loop, read-back prefetching, `tools/judge.py` automated log evaluation, crash restart, Indian telephony adapter.

### Phase 6 (Live test)
- 10 real calls from outside callers (>=3 per language), >= 8 PASS on log judge, then tag `v1`.

---

## 4. Binding Rules and Design Decisions

From `HANDOFF.md` §5 and `PLAN-V2.md` §2:
1. **One caller at a time:** Single-tenant server. No concurrency or queues.
2. **Non-blocking audio loop:** Nothing in `Mouth` or socket handlers may block.
3. **Clip existence invariant:** Every clip named in a snapshot must exist in the pool. `Corpus.load` rejects incomplete snapshots.
4. **Keypad limits:** Menus have at most 9 choices. `0` means "don't know" (or "none" in read-back) and never strikes.
5. **Paid API controls:** Every paid API has a usage ledger and hard cap. Tests mock all APIs and spend ₹0.
6. **Data quarantine (D2):** When a scheme fails, write it to `data_cache/reports/<stage>.json`. Never crash the run.
7. **Spoken cards (D3):** Max 55 words per card in plain words. All source numbers and bounds must appear accurately.
8. **Numerals rule (D4 / G1):** Hindi and Marathi translations must use digits 0–9, not Devanagari numerals.
9. **Single vocab source (D6):** `vocab.py` is the single source for categories, occupations, and labels. Keypad menus read from `vocab.py`.
10. **State filter (D7):** State is yes/no (1=Maharashtra, 2=Other, 0=Don't know). Central schemes are ANY.
11. **Stable IDs (D1):** Scheme IDs are myscheme slugs, sorted alphabetically.
12. **Audit logging (D9):** Every spoken slug, ending type, and section is recorded in `log_schema.py`.
13. **Privacy and security:** Never log or commit API keys. Never send live caller speech or transcripts to Muse.

---

## 5. Open Owner Decisions
1. **Voice for new schemes:** Free local AI4Bharat Indic Parler-TTS (`logs/voice-trial/`) vs free Bhashini API.
2. **Keypad menu length:** Menus take up to 44s (category), ~31s (age/occupation). Condense, speed up, or leave as is.
3. **Phase 2 sign-off:** 3 real calls on Twilio trial account, verify logs, merge, and tag `v1-keypad`.

---

## 6. Codebase File Map

### Contracts & Rules — `haqdaar/contracts/`
- `types.py`: Dataclasses, Enums, and interface shapes (`BoxId`, `SchemeRecord`, `TurnResult`).
- `tunables.py`: Central store for all limits, caps, timeouts, and thresholds.
- `log_schema.py`: Structured call log event records (`CallOpenRecord`, `TurnLogRecord`, `CallCloseRecord`).
- `vocab.py`: Fixed taxonomy of categories, occupations, 3-language labels, and forbidden phrases.

### Engine — `haqdaar/engine/`
- `filter.py`: Bitmask filtering of schemes against user vector, survivors, and truth locks.
- `planner.py`: Minimax question picker and soft-box widening ladder.
- `terminals.py`: Call endings (exact match, overflow, widened, nearest, empty).
- `call.py`: Turn loop orchestrating keypad dialogues and state transitions.

### Data & Pipeline — `haqdaar/data/`
- `corpus.py`: Verified snapshot loader, digest verifier, and in-memory scheme index.
- `log.py`: Runtime call log writer persisting JSONL events to disk.
- `pipeline/muse.py`: Meta Muse client and translator with token tracking and ₹60 cap.
- `pipeline/p0_discover.py`: Discovers candidate schemes from myscheme API search proxy.
- `pipeline/p1_scrape.py`: Scrapes myscheme scheme pages into raw JSON documents.
- `pipeline/p2_derive.py`: Extracts structured facets and demographic boundaries.
- `pipeline/p3_cards.py`: Generates concise English spoken cards (max 55 words) per section.
- `pipeline/p4_translate.py`: Translates cards and summaries into Hindi and Marathi via Muse.
- `pipeline/p5_gates.py`: Enforces 5 integrity gates (numbers, forbidden words, length, script, completeness).
- `pipeline/p6_snapshot.py`: Compiles validated scheme cards and audio references into snapshot files.
- `pipeline/texts.py`: Registry of all fixed and dynamic texts to render.
- `pipeline/schemes.yaml`: List of active scheme slugs and priorities.
- `pipeline/run_all.py`: Orchestrates pipeline steps from scraping to snapshot generation.

### Audio & Telephony — `haqdaar/audio/`
- `pool.py`: Audio clip loader using memory buffers to prevent open file descriptor leaks.
- `mouth.py`: Audio queue supporting barge-in cutoff and `#` replay.
- `turn.py`: Inbound DTMF digit and silence detection handler.
- `phone.py`: Adapter connecting engine prompts to audio clips and DTMF menus.
- `lines.py`: Helper loader and formatters for fixed spoken prompts.
- `lines.yaml`: Spoken text strings for fixed prompts across all 3 languages.
- `render.py`: TTS rendering script generating 8 kHz mono μ-law audio clips.
- `telephony/base.py`: Provider-agnostic telephony interfaces and abstract event types.
- `telephony/twilio.py`: Twilio Media Streams WebSocket codec.

### Server & Tools — `haqdaar/` & `tools/`
- `haqdaar/server.py`: FastAPI server handling `/answer` TwiML and `/stream` audio WebSockets.
- `haqdaar/sim.py`: Terminal-based call simulator for interactive testing.
- `tools/stress.py`: Automated 1,000-caller stress test checking crashes and truth failures.
- `tools/listen.py`: Local playback script for audio clip inspection.
- `tools/lines_sheet.py`: Markdown exporter for manual review of fixed lines.
- `tools/call_me.py`: Outbound live test dialer via Twilio and local tunnel.
- `tools/run_demo.py`: Development launcher starting tunnel, server, and outbound call.
- `tools/tone.py`: 8 kHz μ-law 440 Hz audio generator for telephony testing.
- `tools/tunnel.py`: Tunnel manager for exposing local server to Twilio webhooks.

---

## 7. Ask to Muse Spark Planner

Plan **step 3.4-finish** and **step 3.5** as small steps.
For each step give:
1. **The files to touch:** Exact file paths.
2. **The change:** Concrete code modifications and logic.
3. **The test that proves it:** Specific unit or integration test.
4. **The command to verify:** Exact shell command to execute.

**Never plan anything that sends live caller audio or text to Muse.** Muse is restricted strictly to offline pipeline tasks (extraction, cards, and translation).
