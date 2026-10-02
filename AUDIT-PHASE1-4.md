# Haqdaar-V2 Code Audit — Phases 0–4 (1 Oct 2026)

Method: 4 parallel read-only audit tracks (engine+contracts, audio+model+server,
pipeline+snapshot, tests+hygiene), each opening every cited file body; one synthesis
pass. Full track reports were session scratch (`/tmp/audit-1..4-*.md`); this file is
the durable record. Caveat: the critic pass produced no usable output, so cross-track
gaps below are the synthesiser's, not a second reviewer's.

Reviewer spot-verification (this session, targeted checks — all CONFIRMED):
- F1: `ab-pmjay` is in live `snap_20261001_084303` (12 schemes) AND in
  `scrape.json` quarantine ("Page not found. Writing nothing.").
- F2: stale `data_cache/raw/ab-pmjay.json` (12 Sep) still on disk; `p2_derive.py`
  globs `raw/*.json` and never reads `scrape.json`'s quarantine list; p1's "leaves
  no raw file" docstring is false when a stale file predates the quarantine.
- F3: zero `door_a`/`DoorA` references in `call.py`/`server.py`/`sim.py` — Door A is
  dead code in prod (tests + `door_a_check.py` only).
- F6 mechanism: `server.py:232` spawns a thread per websocket with no one-caller guard.

## TOP 10 findings (ranked by risk)

1. **HIGH — Stale quarantined scheme ships in live CURRENT.** `snapshots/snap_20261001_084303/manifest.json:1` — ab-pmjay (scrape-quarantined as page-not-found) is one of the 12 schemes in live CURRENT. User-facing wrong/stale scheme data.
2. **HIGH — Quarantine bypass root cause (p1 + p2).** `haqdaar/data/pipeline/p1_scrape.py:361` quarantines by writing nothing but never deletes a stale raw file (its "leaves no raw file" claim is false); `haqdaar/data/pipeline/p2_derive.py:592` globs `raw/*.json` and never consults `scrape.json`'s quarantine list — so the 2026-09-12 ab-pmjay cache was re-derived Oct-01, passed gates, and shipped.
3. **HIGH — Door A implemented but never invoked.** `haqdaar/engine/call.py` (whole file): `run_call` goes turn-0 → consent → forced `Ask("category")`; no `DoorA` import, no `match()` call; only referrers to `door_a.py` are `tests/test_door_a.py` and `tools/door_a_check.py`. `door_a_option_1/2/none`, `door_a_downgrade_to_b` never emitted. Violates T12/MAP-t12 "Door A is the opener".
4. **HIGH — T12 20 s bar unmeasurable.** `haqdaar/engine/call.py` (all): `t_name`/`t_end`/`candidate_count` exist in `log_schema.py:88-90` but no `haqdaar/engine/*.py` line ever writes them (consequence of #3).
5. **HIGH — Engine purity violation in Door A.** `haqdaar/engine/door_a.py:21,218-240`: imports `yaml`, reads `schemes.yaml` + `data_cache/derived/*` from disk at runtime; couples Engine to repo-layout `BASE_DIR`. Engine may import only `contracts/` (+ sibling pure modules); file I/O is Data's.
6. **MEDIUM — One-caller (D14) claimed but unenforced.** `haqdaar/server.py:193,232`: docstring says one caller at a time, but every websocket spawns its own engine thread with no guard; concurrent calls share corpus/pool and `AudioPool` LRU/OrderedDict + byte counters have no locks → corruption risk under 2 calls.
7. **MEDIUM — Stale media → ghost utterances.** `haqdaar/audio/ear.py:574`: `listen()` never drains `_events`; while the engine sits in ~10 s STT, ~500 media packets queue and the next `listen()` transcribes stale audio as a ghost utterance.
8. **MEDIUM — STT worst-case ~10 s delays barge-in.** `haqdaar/audio/ear.py:206,301`: Sarvam + Groq sequential 5 s timeouts per utterance inside `Ear.listen`; keys arriving during STT are queued and win only after (post-STT key check) — caller perceives up to ~10 s delay before barge-in is honored. Correct thread, latency risk.
9. **MEDIUM — Planner Widen payload discarded; ladders can disagree.** `haqdaar/engine/call.py:204-206`: any `Widen` → break with `STOP_ZERO_SURVIVORS`, then `classify_shape` re-runs its own ladder; worse, planner tests raw survivors (`planner.py:258-259`) while terminals test speakable-filtered (`terminals.py:370-372`), so the rung can disagree with the terminal.
10. **MEDIUM — Hardcoded yes/no word lists break language-blind Engine.** `haqdaar/engine/call.py:649,663`: confirm yes/no decided by hardcoded Hindi/Marathi/English lists ("haan","ho","sahi","nahi",…) inside Engine, violating T09 (Model owns language).

## Track 1 — engine-contracts

Verdict: no truth-lock breach — filter/planner/terminals implement the spec faithfully (caps, widening, UNKNOWN, marks, ordering, LOG schema). Two HIGH findings, one root cause: Door A never invoked (TOP-10 #3–#5 above).

Further MEDIUM findings:

- `haqdaar/engine/call.py:66` — `READBACK_REPLAY_MAX=2` hardcoded in Engine, violating T17 ("every tunable lives in `contracts/tunables.py`") and the file's own docstring.
- `haqdaar/engine/call.py:523,544,600,608` — `#`, `*`, SILENCE inside the confirm loop increment `confirm_turns`, added to `turn_n` on resolution. T14: `#` costs no turn; T14/T16: SILENCE consumes none.
- `haqdaar/engine/call.py:725-729` — NEAREST `ladder_rung = len(WIDENING_ORDER)` (3) with zero answered soft boxes; T18 (skipped rungs not counted) → should be 0.
- `haqdaar/contracts/types.py:54-106` — comment says "46 fixed line IDs", tuple holds 50; includes dead `drop_category` (category never widened per `types.py:42` + BUILD-PLAN Step 4).

LOW findings:

- `haqdaar/engine/filter.py:253-281` — `speakable(int)` with dict corpus cannot detect ANY (`values()` check skipped for dicts); every hard box treated as non-ANY: over-strict, can gag ANY-hard-box schemes.
- `haqdaar/engine/terminals.py:118-125` — `_sort_survivors` orders by (-specificity, index/id), never reads priority; D8 order holds only if snapshot pre-orders bits that way (docstring assumes; engine does not enforce).
- `haqdaar/engine/planner.py:212-221` vs `call.py:377` — inferred question count excludes `category`, Engine live `question_count` includes it; divergent accounting when counts aren't passed explicitly.
- `box_strikes` cumulative per box (`call.py:160,280,388`); interleaved SILENCE doesn't break the streak, so "two consecutive non-ANSWER turns" (T11) is approximated, not literal.
- Stale comment `call.py:824` "The next round re-opens Door A" — no Door A call exists.
- `haqdaar/engine/filter.py:43-48` — dict-corpus scheme count via OR-bit_length is a heuristic; silent undercount if a top bit is unset.
- Engine never writes turn classes CLARIFY/REPEAT/META (only ANSWER/UNCLEAR/NOISE/SILENCE/PROPOSAL) — presumably model-side; gap vs T16 "every turn, whatever its class".

Verified compliant (no action): caps (MAX_TURNS=8/MAX_QUESTIONS=6, turn 0 uncounted); widening order income→age→occupation, soft-only, first-rung-≥1-stop; UNKNOWN semantics (widens, unaskable, unsatisfied; `0`=declined no-strike; cardinality>9→keypad_dropped; double-miss→UNKNOWN; accepted once, never re-asked); keypad ≤9 (`KEYPAD_CARDINALITY_MAX=9`, vocab lists ≤9, snapshot values from `vocab.py`); keypad-only triggers (2-failure counter model-owned in `model/router.py:57`); T17 frozen signatures intact (`run_call`/`next_action`/`survivors`/`tally`/`miss_set` match INTERFACES.md); LOG schema (PROPOSAL, SILENCE with unchanged `turn_n` + `silence_n`, DeliveryRecord, LangSwitchRecord, `unknown_source`, `discarded_transcript`, `invalid`); 5 delivery shapes per BUILD-PLAN Step 5 (note: the track brief's "3 terminals" matches no spec text — code is correct); D7 yes/no prompt, D13 keys, Door B (clears category only, once, call-wide budgets), hangup-without-close per T16.

## Track 2 — audio-model-server

Socket-loop / Mouth blocking: PASS. Socket-loop handlers only `put_nowait`/lock/discard (`server.py:237-243`); `Outbox.emit` = `call_soon_threadsafe(put_nowait)`, never waits; `mouth.py` has zero sleep / zero network. Sleeps found are all off the socket loop: `turn.py:102` (20 ms engine-thread barge-in poll), `phone.py:129` (0.1 s engine-thread hangup wait, bounded by HANGUP_WAIT_S=15 s), `render.py:141,152` (offline `make render` only). Sync network on the call path is engine-thread-only: STT (see TOP-10 #8), model client (`client.py:124`, MODEL_TIMEOUT_S=2.0 s), pool disk reads in `say()` (small clips); tier2 boto3 unreachable in prod (`tier2="none"`).

Threads/queues: exactly one daemon thread per `/stream` connection (`server.py:232`); no pool/executor on the call path (`render.py` executor offline-only; `Ear.alisten` dead in prod, tests-only). Queues: `Ear._events` + `Ear._keys` (unbounded), `Outbox` asyncio.Queue (unbounded). Findings: TOP-10 #6 (one-caller), TOP-10 #7 (stale media); LOW: `_CALLER_HASH` slow leak if `/answer` arrives without `/stream`; `mouth.py:108` lock-free `_cleared` read (GIL-atomic, at most one extra/missing frame).

Never-raise paths: PASS. Sarvam/Groq `transcribe` catch Timeout + Exception → typed failure; `SpeechToText.transcribe` ledger OSError swallowed; `Ear.listen` guarded; `GroqModelClient.call` wraps post+parse → typed failures; `PhoneAudio._clip` swallows all → skip; `server._run_engine` catch-all + `finally done()->hang_up`. LOW caveats: `Model.opener/turn` rely on client never-raise without own try (a raising custom client propagates to the catch-all and kills the call); `_clips` `"scheme:"` 3-part split raises ValueError on malformed tokens (engine-generated, unreachable in practice).

STT/model fallback: PASS. STT: Sarvam primary, any failure flips circuit for the utterance → Groq fallback with hint padding, `reset_circuit()` per listen; both-fail → Noise + `stt_failed` → keypad_only (threshold 1 — aggressive but tested/intended); empty-transcript-with-success → Noise without degradation (correct garble-vs-failure split). `force_stt_failure()` → immediate keypad_only, covered by tests (`test_ear_force_stt_failure_method`, `test_call_spoken.py:500`). Model: any failure/429/timeout → `failures+=1`; ≥2 → keypad_only, network skipped (tested incl. no-further-network-call). SpanGuard: normalized containment + token-subsequence + ordered-cover, box-compat, closed-set per vocab, income_band deliberately open (documented), scheme pseudo-box non-empty; alias fast-path bypasses SpanGuard by design (verified corpus aliases). Engine wiring (`call.py:128-134,285-292,478-484`) checks keypad_only at opener, each turn, after each model call; writes `{"mode":"keypad_only"}` + plays `keypad_only_mode`. Turn0 DTMF-only via `PhoneAudio.select_language`, engine-called when present (`call.py:87-88`) — consistent.

Tests-offline: PASS. `conftest.py` blocks non-localhost `httpx.Client/AsyncClient.send` (covers top-level `httpx.post`), blocks `MuseClient._http_post`, redirects ledgers to tmp, pins providers; audio/model tests fully mocked; boto3 unguarded but no test path exercises tier2.

LOW (phone): `phone.py:137` scheme split (see never-raise); HANGUP_WAIT_S=15 s engine-thread linger after socket death.

## Track 3 — pipeline-snapshot

Corpus.load refuses missing clips — INTACT + TESTED. `haqdaar/data/corpus.py:148-171`: per manifest `render_keys` entry checks pool-index membership → file existence → streaming sha256 vs manifest digest → vs pool-index digest; raises `CorpusError` on each; never holds bytes (chunked `_stream_file_sha256`). Tests (`test_corpus.py:253-314`, `test_real_snapshot.py:52-58`) cover corrupt/deleted/missing-index cases. Live: `Corpus.load('CURRENT')` → 12 schemes; independent re-verify 477/477 keys exist, file sha256 == manifest == pool-index digest (405 extra pool entries = shared flat pool by design).

Render/texts parity — SINGLE SOURCE (one LOW caveat). Render (`render.py:299-310`) and snapshot (`p6_snapshot.py:474-525`) both walk `texts.all_texts` family; `test_texts.py:138-154` asserts manifest key set == render key set on real data. LOW: scheme-chunk keys computed inline in p6 (`p6_snapshot.py:545-566`) with legacy fallbacks + empty-string hash for missing chunks that `texts.scheme_chunk_texts` lacks — parity holds only via G5 completeness; diverges on incomplete/fixture input (reachable via `--all-schemes`).

Gates/quarantine — TOP-10 #1–#2 (HIGH). Counts verified: roster 30; scrape kept 28 + quarantined 2 (ab-pmjay page-not-found, pmsby no-documents); derive kept 28 + quarantined 1 (pm-sym); gates 28/28 ok, cards 28/28, translate 56/0-fail. MEDIUM: `data_cache/reports/gates.json:1` (and cards/translate) report survivors-only counts — quarantines invisible without hand-diffing `schemes.yaml` + `scrape.json` + `derive.json`.

Muse cap + ledger — HARD CAP, TESTED. `muse.py:98-104`: `_check_budget()` before every attempt; spent ≥ ₹60 (`tunables.py:169`) raises `MuseBudgetError` that the retry loop cannot swallow; `test_muse.py:46-53` proves refusal at cap with zero sends; reasoning tokens billed as output; ledger 381 rows, ₹12.97/₹60. `tests/conftest.py:13-69` triple guard (ledger redirect, `_http_post` block, httpx block; fakes injected). MEDIUM (billing, not safety): `run_all.print_cost` (`run_all.py:98-139`) reads only groq/sarvam ledgers — ₹12.97 Muse spend invisible to `make pipeline-cost`.

Snapshot reproducibility — SET-REPRODUCIBLE, not bit-reproducible (OK by design). CURRENT = `snap_20261001_084303` (12 schemes, 477 keys, zero undigested). `scheme_has_all_clips` over 28 derived returns exactly the CURRENT 12; other 16 lack clips (audio gate working, awaiting `make render`). Bit-identity impossible by construction (`manifest.created_at`, fresh snapshot id + CURRENT flip); `main()` enforces readback + audio filter by default; `--all-schemes` can build an unloadable snapshot (documented escape hatch).

Dead/stale code: MEDIUM — `run_all._run_snapshot` (`run_all.py:69-79`) named/docstring'd "build a snapshot" but only counts texts and returns 0; pipeline's final step never builds/flips CURRENT (only via `make snapshot`/`p6.main`). LOW (stale words): `p2_derive.py:579` "Reads 12 files"; `test_real_snapshot.py:1` "real 12 schemes". NOT dead (checked): `p0_discover` (Makefile target), `GroqClient` (LLM_PROVIDER fallback), `SarvamTranslator` (TRANSLATE_PROVIDER), `render_stubs=True` (tests-only; prod default False — correct).

## Track 4 — tests-hygiene

Suite: 372 collected, **372 passed, 0 skip/xfail, ~20–23 s** (verified by run; 368 `def test` + parametrize expansion; matches HANDOFF). Warnings: LOW `audioop` DeprecationWarning from `haqdaar/audio/ear.py:36` — breaks on Python 3.13+ (+ anyio typing warnings).

TEST-PLAN §3 property table: terminals (16 tests), filter/UNKNOWN (11), model/span-guard (21), SILENCE-vs-NOISE in test_turn.py (6), Corpus.load/no-TTS-import (17, incl. no-pool-import at :173), `make demo-fixture` — all exist. `Log.write` never-raises covered at `test_call.py:162-183` (malformed write → `invalid: True`) though `test_log.py` file missing — location deviation only. Keypad-only completion covered by `test_phone_call.py` (3 e2e websocket tests) + test_call.py though `test_call_keypad.py` missing — location deviation only. MEDIUM: no "twilio only under audio/telephony" grep test (TEST-PLAN §3 requires one every step; dir exists, test absent). Ten-calls bar (§4) + infra checks (§5): human/physical, owner cannot run (OWNER-END-TODO.md) — not automatable.

Asserts: no `assert True`/tautologies/bare `except`; 5× `is not None` legitimate (finder match-or-None + negative cases). conftest strong (ledger redirect post-pollution-postmortem, Muse block post-₹0.70 incident, httpx guard) — paid-API leakage risk LOW.

Slow/flaky: slowest `test_phone_call.py::test_a_keypad_question_is_followed_by_its_menu` 10.7 s (real snapshot + TestClient websocket + HANGUP_WAIT_S) — structural, not flaky; the timing-regression canary. Rest <0.5 s each; no network dependence — flaky risk LOW.

tools/Makefile: all `tools/*.py` have targets except `__init__.py` and `tone.py` (μ-law helper lib, imported not run — fine). `make test` = `pytest`.

Fixtures/binaries: tracked audio 2.4 MB total (fixtures 2.3 MB, largest 81 KB); JSON fixtures small. Largest tracked files: candidates.csv 365 KB, schemes.jsonl 287 KB, NOTES.md 185 KB; masks.bin <100 KB. No action.

Git/secrets/ignore: no keys in tracked files; `.env` untracked + never in history; `.env.example` clean. Ledgers (`*_usage.jsonl`), audio/ (37 MB), logs/, `data_cache/*` (raw/derived/extract re-included) correctly untracked. LOW: ~30 merged step branches (+ remote refs) never deleted; `demo-15sep` stale unmerged (5 ahead/86 behind). LOW: `.gitignore` lists `.agent/` yet `.agent/NOTES.md` (185 KB) is tracked — works (tracked wins) but confusing.

Docs: PLAN-V2/NEXT-PLAN "109 tests" stale but superseded (expected); PROJECT-UPDATE progression tops at 372, HANDOFF 372 — live docs current.

## Cross-track risks

- **Stale-data → live-call pipeline (T3→T2/T1).** The quarantine bypass (TOP-10 #2) already put stale ab-pmjay in CURRENT (#1); the engine has no freshness signal and the audio path faithfully speaks whatever the corpus loads — no downstream layer can catch this. Fix at p1/p2, plus roster-vs-survivor accounting in gate reports.
- **Two-caller corruption (T2) meets unowned ordering (T1+T3).** Concurrent calls share the lock-free AudioPool (#6) while D8 priority tiebreak and keypad-menu order depend on snapshot bit order that the engine assumes but never enforces (`terminals.py:118-125`) — data owns the proof, engine owns the assumption, neither enforces it.
- **Unmeasurable latency bars (T1+T2).** T12's 20 s bar is unmeasurable (no `t_name` stamp, #4) while STT alone can burn ~10 s per utterance (#8) — even if Door A is wired up, the bar cannot be verified against the dominant latency source.
- **Degradation hair-triggers vs silent caps (T1+T2).** Single STT failure degrades the whole call to keypad_only (tested/intended but aggressive), while `#`/`*`/SILENCE quietly consume cap turns in the confirm loop (TOP-10-adjacent MEDIUM) — the call degrades fast and the budget leaks silently.
- **Cost blind spot (T3).** `print_cost` omits the ₹12.97 Muse ledger while the hard ₹60 cap is the binding budget — the pipeline's own cost command hides the spend that can halt translation.

## Unresolved items

- Critic pass produced no usable output — cross-track gaps above are the synthesiser's, not a second reviewer's. (Reviewer note: top-3 findings + F6 mechanism independently spot-verified this session.)
- D8 priority tiebreak / keypad-menu order depend on snapshot bit order (track 1 cross-track note; data track owns proof — not closed).
- TEST-PLAN §4 ten-calls bar + §5 infra checks: human/physical; OWNER-END-TODO.md records the owner cannot run them — unverifiable by audit.

## Omitted scope

- Live Twilio/telephony integration and any real-call traffic (audited code paths only; no "twilio only under audio/telephony" grep test exists to pin the boundary).
- Ten-calls bar and infra checks (TEST-PLAN §4–§5; human/physical, not automatable).
- `demo-15sep` stale branch contents (5 ahead/86 behind, unmerged) — noted, not reviewed.
- Historical/superseded plans (PLAN-V2, NEXT-PLAN "109 tests" figures) — treated as expected staleness, not audited for correctness.
- Tier-2 audio fetch (boto3) beyond noting it is unreachable in prod; `work-adarsh/` diary and `work-with-tools/` contents.

## Suggested fix order (reviewer)

1. p1/p2 quarantine bypass (#2) + rebuild snapshot without stale ab-pmjay (#1) — one Antigravity step; re-verify gates + snapshot + stress.
2. Wire Door A into the opener (#3) with `t_name`/`t_end` stamps (#4); fix engine purity (#5) by injecting entries at the call site — one step.
3. Confirm-loop turn accounting (#-MEDIUM: `#`/`*`/SILENCE consuming cap turns) + Widen/ladder agreement (#9) — same step as #2 or its own.
4. One-caller guard (#6) + ghost-utterance drain (#7) before any 2-call or live-traffic test.
5. Small batch: yes/no word lists to Model (#10), `print_cost` Muse ledger, twilio-boundary grep test, `audioop` 3.13 warning, dead-branch cleanup.
