# HAQDAAR v2 — full build plan (100+ schemes × Hindi, Marathi, English)

Written 18 Sep 2026. Opus designs and reviews. Sonnet `coder` agents write the code.
Each **Phase** below is one `plan-build` run. At the start of a phase Opus does four things:
- re-reads this file, `.agent/TASK.md` and `.agent/NOTES.md`;
- re-measures anything marked **(re-measure)**;
- writes each step as a self-contained coder prompt;
- gets the owner's OK.

Steps are commit-sized. This plan was stress-tested by a separate reviewer against the code; the
17 defects it found are fixed below (§7).

---

## 0 · Context

- **Product:** a phone number anyone can call from a keypad phone. It asks a few questions in
  Hindi, Marathi or English, then reads out the government schemes that fit. It never lies, never
  says "you are eligible", and never hangs up on the caller.
- **New scope (owner, 18 Sep):**
  - By the end of v2 it serves **100+ schemes**: central schemes plus Maharashtra state schemes.
  - All 3 languages are complete for every scheme.
  - New Sarvam keys are in.
  - An Indian number is on the way, provider unknown, so the phone code must work with any
    provider.
  - The repo moves out of iCloud.
  - No fixed test date: go as fast as is safe.
- **Done bar:** 10 outside callers, at least 3 per language, judged from the log only; 8 or
  more PASS.
- **Where it stands:**
  - Built and tested (109 tests): the engine (filter, planner, endings, call loop) and the
    English data for 12 schemes.
  - Missing: Hindi/Marathi text, the recorded voice, the real snapshot, playing on the phone,
    speech, the AI step, the judge, and scale.

---

## 1 · What the research found

| # | Finding | Evidence |
|---|---|---|
| F1 | **Sections are far too long to speak.** English per scheme is 4,616 chars; `benefit_text` averages 1,815 (max 3,796) and `who_can_apply` 1,017 (max 4,651). At the measured 13.2 chars/s that is 2–6 minutes per section. The demo simply cut each at 320 chars, which can drop a fact. | measured on `data_cache/derived/schemes.jsonl`; `demo-15sep:haqdaar/demo_voice.py:29,124` |
| F2 | Hindi/Marathi read-back sections are empty for all 12. The Hindi/Marathi summaries and names come from Groq with no gate. No translate or gates code exists. | `p2_derive.py:440-448,700-701,749-764` |
| F3 | Scheme ids are `S{idx+1}` in file order, and the corpus index follows file order, so adding a scheme renumbers everything. (`S6` in the tests is a fixture deliberately missing its Marathi summary. Leave it.) | `p2_derive.py:703`; `p6_snapshot.py:249-252`; `corpus.py:181`; `test_step2.py:202-241` |
| F4 | One bad scheme stops the whole scrape or derive run. | `p1_scrape.py:337-341`; `p2_derive.py:685,692,777-783` |
| F5 | **Any value not in the closed lists quietly becomes ANY.** A Gujarat-only or fishermen-only scheme would be read to everyone: a lie. The lists are duplicated in code and in the prompt. | `p2_derive.py:47-85,323-330,636-645` |
| F6 | A box with more than 9 values becomes UNKNOWN in keypad mode. For `category` the opener is dropped. `state` → UNKNOWN → the truth lock blocks every state scheme. Menu values come only from values that appear on schemes, and a missing value's mask is 0. | `call.py:119-129,160-164,198`; `filter.py:274-277`; `p6_snapshot.py:278-285`; `corpus.py:284-289` |
| F7 | Age values are raw strings. Bands are written to `vocab.json` but never read, and they are sampled when there are more than 9 cutoffs. | `p6_snapshot.py:159-200,278-285,294`; `corpus.py:210-212` |
| F8 | Key `0` counts as a strike, yet the line says "press 0 if you don't know". In read-back, `*` and `0` just leave the menu. | `call.py:302-319,500-511` |
| F9 | Overflow reads 3 schemes, ranked only by the count of specific boxes. At 100+ schemes most matches are never heard. | `terminals.py:117-124,226`; `tunables.py:26-28` |
| F10 | The log never records which schemes were spoken, so no judge or truth check is possible. | `log_schema.py:64-106` |
| F11 | Snapshot problems: `ALIAS_FLOOR` is used for `ALIAS_CATEGORY_WORD_MIN` (both 3, so a test must monkeypatch one); `evidence_quotes` is missing from the skip list; `render_stubs=True` quietly writes 120 ms of silence; `enforce_readback_gate` raises on the first bad scheme; `__main__` builds an empty snapshot; fixed-line keys hash placeholder text. | `p6_snapshot.py:85,213,236-240,259-266,372-393,434-440,540-544` |
| F12 | The audio pool keeps one open file per cached clip. That is 1,000+ files at the 512 MB cap, over macOS's limit of 256. | `pool.py:149-159,205-214` |
| F13 | There is no way to list schemes. The myscheme API returns **401**, and `sitemap-0.xml` has 0 scheme pages (both fetched 18 Sep). The Playwright scraper already renders pages. | `p1_scrape.py:43,197-200` |
| F14 | **Groq free tier = 8K tokens/min, 1,000 requests/day, 200K tokens/day per model.** This is shared with live calls. The derive cache key has no prompt version, so a changed prompt reuses stale answers. The raw page cache expires after one day, so every run re-scrapes. | `WORK.md:86`; `p2_derive.py:263-265`; `p1_scrape.py:98-160` |
| F15 | `mouth.py`, `turn.py`, `ear.py`, `model/*` and `lines.yaml` don't exist. `FIXED_LINE_IDS` has 48 ids. `make pipeline` and `make smoke` are stubs. `make sim` builds its own stub snapshot. The demo code exists only on `demo-15sep`. | `types.py:55-104`; Makefile `:62-66`; `sim.py:181-200` |
| F16 | iCloud has offloaded 36 repo files and 470 `.venv` files (dataless). The disk is 91% full. Claude's memory folder is keyed by the repo path. No code holds an absolute path. | `find -flags +dataless`; `git grep` |
| F17 | The brain docs say "8–10 schemes to start" and "state is never a keypad menu" (about 36 values). T08 already says "design N = 100". | `prd.md:170-177`; `T23.md:64-70`; `decision-log.md:38`; `T08.md:44` |

**What makes the obvious approach wrong.** The current Step 9/10 is "translate every section and
record it". That produces 2–6 minute clips nobody can listen to on a phone. It costs about 3×
the credits and cannot be checked by a person at 100+ schemes. The fix is **spoken cards** (D3):
short, fact-checked versions of each section. They are written once in English, then translated
and gated. Every later step builds on cards.

---

## 2 · Design decisions (binding for every coder prompt)

- **D1 · Scheme id = myscheme slug.** The scheme list is **sorted by slug** before any
  enumeration: derive output, snapshot masks, `Corpus` index. Logs use slugs, never bit positions.
- **D2 · Quarantine, don't crash.**
  - A scheme that fails any stage is set aside with a reason in
    `data_cache/reports/<stage>.json`.
  - A run fails only if fewer than `MIN_SCHEMES` survive.
  - A scheme is served only if it passes every gate in **all 3 languages**.
  - The snapshot uses `apply_readback_completeness_gate` (quarantine), never
    `enforce_readback_gate` (raise).
- **D3 · Spoken cards.** One Groq JSON call per scheme writes four English cards: benefit, who can
  apply (with the exclusions folded in), documents, how to apply.
  - Each card is at most `CARD_MAX_WORDS=55` words (about 25 s), in plain words.
  - The documents card lists up to 6 items. **Code**, not the model, appends "and N more; the CSC
    centre will tell you", with N counted from the source.
  - Gates on the English cards:
    - every number in a card appears in its source (after normalising commas, "Rs" and "₹", and
      "lakh");
    - **every age and income number from the facets appears in the who-can-apply card**;
    - no forbidden phrase;
    - each sentence overlaps the source by at least `CARD_OVERLAP_MIN` (tuned on the 12).
  - The name and summary stay as they are.
  - Audio ≈ 120 s ≈ 1 MB per scheme per language, so about 400 MB and about 650k TTS chars for
    130 × 3 **(re-measure)**.
- **D4 · Translation by Sarvam Translate, not Groq.** This keeps Groq's daily budget for live
  calls.
  - p2 now writes **English only**. The summary and cards go to Hindi and Marathi through p4 and
    are gated by p5.
  - Digits are kept in international numerals.
  - Scheme names in Hindi/Marathi, from Groq, are kept as they are but pass G2 and G4, and go on
    the owner's review sheet. Aliases are used only for matching, never spoken.
- **D5 · Five gates per scheme per language** (`p5_gates.py`):
  - **G1 · Numbers.** The same number multiset as the English (the "N more" count is excluded).
  - **G2 · Forbidden phrases.** Checked against second-person phrases only ("you are eligible",
    "आप पात्र हैं", "तुम्ही पात्र आहात"…). Single words like "पात्र" or "मिलेगा" are *not*
    banned, because they appear in honest text.
  - **G3 · Length.** Hindi/Marathi at most 1.6× the English length.
  - **G4 · Script.** At least 80% Devanagari, and not identical to the English.
  - **G5 · Complete.** All 6 sections × 3 languages are non-empty.
  - One forbidden list lives in `vocab.py`. The old copy at `p2_derive.py:88-90` is removed.
- **D6 · One vocabulary file.** `haqdaar/contracts/vocab.py` holds every closed list, the labels
  for each value in all 3 languages, and the forbidden phrases.
  - **Keypad menus are built from `vocab.py`, not from the values found on schemes.**
  - A value from the LLM that is not in the list **quarantines** the scheme. It is never widened
    to ANY.
  - `state` never comes from the LLM. It is set from the scraped level: CENTRAL → ANY, Maharashtra
    → MAHARASHTRA, anything else → quarantine.
  - CATEGORY is fixed now as 9 need groups. The old 11 values map onto them:

    | Key | Need group | Old values |
    |---|---|---|
    | 1 | farming | agriculture |
    | 2 | business & loans | business, handloom |
    | 3 | jobs & skills | employment, skills, livelihood |
    | 4 | health | health |
    | 5 | housing | housing |
    | 6 | pension & old age | pension |
    | 7 | education | education |
    | 8 | women & children | new |
    | 9 | welfare & disability | social_welfare |

  - OCCUPATION (at most 9) is finalised in 3.2, once the scheme list is known.
  - The derive cache key gets a **per-task** prompt version. Existing caches are renamed, not
    thrown away.
- **D7 · State = a yes/no question:** "Do you live in Maharashtra? 1 yes, 2 no, 0 don't know".
  - The OTHER mask = schemes whose state is ANY (central schemes).
  - Prompt id `state_q_maharashtra` replaces `keypad_state` at `call.py:198`.
  - This **supersedes** "state is never a keypad menu" and gets a new entry in the decision log.
- **D8 · Ranking and paging.**
  - `priority` 1–3 is set in `schemes.yaml`.
  - Sort order: specificity (descending), then priority, then slug.
  - Overflow reads 3 schemes. At the last one, key 9 plays the next 3 instead of
    `no_more_schemes` (`call.py:500-511`).
  - In read-back, `*` changes language and `0` = "none of these" (leave the menu). Any other key
    replays the menu; it never leaves silently.
- **D9 · Log what was spoken.**
  - `log_schema.py` gains a delivery record: slug, ending type, and the sections played.
  - Key 0 logs `unknown_source="declined"`.
  - The judge and the truth check read only these.
- **D10 · Git and storage.**
  - `.gitignore` changes `data_cache/` to `data_cache/*` with exceptions for `derived/`,
    `extract/` and `raw/`, and adds `data_cache/raw/*.html`.
  - So text, LLM outputs and p2's raw JSON inputs are in git. Audio and HTML are not.
  - `make backup` writes a `.tgz` to `~/haqdaar-backup/`.
  - Audio key = sha(text, lang, voice, model, rate, pace 0.9). The slow replay (0.72) is
    **stretched at play time** (0.03 s per 11 s clip, measured), so it is never pre-rendered.
- **D11 · Paid work is gated and counted.**
  - `make pipeline-cost` prints Groq requests **and tokens**, Sarvam translate chars and TTS chars.
  - No bulk paid run starts without the owner's OK.
  - `make pipeline` skips scraping unless `--rescrape`, and the raw cache does not expire.
  - The render can resume, and stops cleanly on 402.
- **D12 · Phone code works with any provider.**
  - `telephony/base.py` defines the events and builders.
  - `twilio.py` implements them.
  - `PHONE_PROVIDER` picks the provider.
  - An Indian provider is one more file.
- **D13 · Keys follow the PRD.**
  - `#` repeats; a second `#` repeats slowly.
  - `*` changes language.
  - `0` = don't know.
  - `9` = next / more.
  - The demo's keys (9 = repeat, 3 = don't know) are **not** carried over.
- **D14 · One caller at a time** (owner rule).
- **D15 · Branches.**
  - One branch per phase off `main` (`v2-p<N>-<name>`), one commit per step, pushed after each.
  - Merge `--no-ff` only with the owner's OK.
  - The demo code is read with `git show demo-15sep:<path>`; it is not on `main`.
- **D16 · Honest limits.** A card is never presented as the full rules. The closing line points
  to the CSC centre or myscheme.

---

## 3 · Phases and steps

**Legend**
- **[C]** coder (Sonnet) · **[O]** Opus · **[A]** Adarsh
- **∥** can run in parallel, in its own worktree
- Test: `.venv/bin/python -m pytest -q`
- Lint: `python3 -m py_compile <changed files>`

### Phase 0 · Fix the ground (½ day)

0.1 **[O] Move the repo out of iCloud safely.** A plain `mv` is wrong here, because 36 repo files
    and 17 files inside `.git` are dataless (placeholders with no content on disk).
  1. Download them: run `brctl download .`, then loop until
     `find . -flags +dataless -not -path './.venv/*' | wc -l` is 0.
  2. Copy: `rsync -a --exclude .venv` to `~/code/haqdaar-v2`.
  3. Check: `git fsck --full` is clean.
  4. Rebuild the venv with python3.11 and `pip install -e .`.
  5. Copy the Claude memory folder to the new path key.
  6. Move the old folder to the Trash only after the tests pass.

  **Verify:** `pytest` shows 109 passed in < 60 s, and `git status` matches the old copy.
  **[A]** reopens VS Code on the new folder.
0.2 **[O] Cleanup** as in NEXT-PLAN §4, everything to the Trash.
  - What goes: `_staging/`, 15 unused clips, the stray fixtures folder, junk files.
  - **Verify:** 109 tests still pass.
0.3 **[O] Commit the loose demo work on `demo-15sep`, push it, freeze the branch.**
  - What is committed: Makefile, `run_demo.py`, PROJECT-UPDATE, REFERENCES-FOR-PPT, and the 100
    clips.
0.4 **[C] Data under git + backup.** Apply the `.gitignore` change from D10 and add
    `make backup`.
  - **Verify:** `git ls-files data_cache | wc -l` shows 62 (12 raw JSON + 14 derived + 36
    extract), and `make backup` writes a `.tgz`.
0.5 **[C] Bring the demo tools to `main`.**
  - `git checkout demo-15sep -- tools/tunnel.py tools/run_demo.py tools/call_me.py`.
  - The default `APP` becomes `haqdaar.server:app`, because `voice_demo` is not on `main`.
  - Add the Makefile target `call-me`.
  - **Verify:** `py_compile` passes, and `make -n call-me` shows `haqdaar.server:app`. **Do not
    run `run_demo.py`: it rings the phone.**
0.6 **[C] Docs, with the exact text Opus supplies.**
  - New decision entries D1, D3, D6, D7, D8.
  - "Corpus = 100+, central + Maharashtra."
  - Supersede "state never keypad" (do not delete it).
  - Update WORK.md §1/§6 and PROJECT-UPDATE.
  - **Verify:** `sync_vault.py --sync`, then `--status` is clean.

### Phase 1 · Pipeline and engine ready for 100+ (proven on the 12; ~3–4 days)

1.1 **[C] Stable ids (D1).**
  - `p2_derive.py:703` sets `scheme_id = slug`, and the list is sorted.
  - `p6_snapshot.py:249-252` and `corpus.py:181` use the sorted order.
  - Do **not** touch S6 (see F3).
  - **Verify:**
    - the tests pass;
    - derive run from cache makes **0 Groq requests**;
    - `jq -r .scheme_id` prints 12 sorted slugs.
1.2 **[C] Quarantine (D2)** in `p1_scrape.py:297,337-341` and `p2_derive.py:685,692,777-783`.
    Add `MIN_SCHEMES` to `tunables.py`, and write the reports.
  - **Verify:** new tests: 1 of 3 fails → 2 kept, 1 reported, exit 0; below the floor → exit 1.
1.3 **[C] `vocab.py` + honest closed lists (D6).**
  - Nothing unknown becomes ANY (`p2_derive.py:636-645`).
  - State comes from the level.
  - CATEGORY becomes the 9 groups.
  - The forbidden phrases move here.
  - The prompt is built from this file.
  - Per-task prompt versions; existing cache files are renamed.
  - **Verify:**
    - `test_vocab.py`: every keypad box has at most 9 values, and each has labels in 3
      languages;
    - an unknown occupation or state → quarantined (test);
    - re-derive the 12 → only the facets task calls Groq (12 requests, logged).
1.4 **[C] Engine keypad fixes (D6, D7, F7, F8).** Runs after 1.3.
  - Keypad menus come from `vocab.py`.
  - The OTHER state mask.
  - `state_q_maharashtra` at `call.py:198`.
  - Key 0 = declined, not a strike (`call.py:302-319`).
  - `corpus.py:210-212` reads the bands. A scheme's bit is set only if **the band lies wholly
    inside** its range; the edges are the schemes' own cutoffs.
  - Fixture edits, listed by Opus in the prompt: states BIHAR/KARNATAKA become MAHARASHTRA/ANY,
    and `test_step2.py:169` gets S7.
  - **Verify:**
    - a Maharashtra scheme is spoken only after "yes";
    - "no" keeps the central schemes;
    - 0 → UNKNOWN with no strike;
    - band tests.
1.5 **[C] Delivery log (D9)** in `log_schema.py` and `call.py`.
  - **Verify:** a sim call's log lists the spoken slugs and the sections played.
1.6 **[C] Snapshot fixes (F11).**
  - Box discovery uses a **SEVEN_BOXES allow-list** (replacing the skip list at `:259-266`).
  - The `ALIAS_*` constant fix at `:85`.
  - **Verify:** tests; the alias test monkeypatches one constant so it fails before the fix.
1.7 **[C] Ranking and paging (D8).** `priority` in `schemes.yaml` flows to the record and the
    snapshot. Changes in `terminals.py:117-124` and `call.py:500-511`, plus the new line
    `results_more_prompt`.
  - **Verify:**
    - 10 matches → heard as 3 + 3 + 3 + 1, sorted by specificity, then priority;
    - `*` in read-back changes the language.
1.8 **[C] Spoken cards (D3)**, new `p3_cards.py` writing `cards.jsonl`. It logs **tokens per
    call**.
  - **Verify:** 12 × 4 cards, at most 12 requests. **[O]** reads all 48 cards against the source
    and tunes `CARD_OVERLAP_MIN` and the prompt.
1.9 **[C] Translation (D4)**, new `p4_translate.py`.
  - First a 1-request probe: the current model name, the char limit, and the numeral option go
    into NOTES. **Stop if they differ from the plan.**
  - p2 stops writing the Hindi/Marathi summary.
  - **Verify:** 12 × 5 texts × 2 languages; a second run makes 0 requests.
1.10 **[C] Gates (D5)**, new `p5_gates.py` + `make pipeline-gates`.
  - **Verify:** one unit test per gate, and `"पात्रता"` must **not** trip G2. On the 12: at
    least 10 pass **(re-measure)**.
1.11 **[C] Fixed lines, chips and band labels.** `haqdaar/audio/lines.yaml` holds the 48
    `FIXED_LINE_IDS` + `results_more_prompt` + `state_q_maharashtra`. Chips come from the
    `vocab.py` labels. Band labels use a template ("18 to 40 years").
  - English written by **[O]**.
  - Hindi/Marathi via p4 + p5.
  - `tools/lines_sheet.py` writes a `.md` sheet; **[A]** corrects it. Corrected lines are pinned.
  - **Verify:** a loader test: every id is present in 3 languages and passes the gates.
1.12 **[C] One text list for render and snapshot**, new `haqdaar/data/pipeline/texts.py`.
  - `all_texts()` yields (audio key, lang, text) from `lines.yaml`, the chips, and the
    cards/summary/name per language.
  - p6 builds its `chunks` and fixed-line keys from it (fixing `:372-393`).
  - `__main__` builds from the real inputs.
  - `render_stubs=False` unless `--stubs` (the sim and fixtures only).
  - **Verify:** a test shows p6 and `all_texts()` produce the same key set.
1.13 **[C] `make pipeline` + `make pipeline-cost`** (D11).
  - The order is p1 (only with `--rescrape`) → p2 → p3 → p4 → p5 → p6.
  - Paid steps need `--yes`.
  - **Verify:** the cost printout on the 12, and a warm run makes 0 paid requests.

### Phase 2 · Real voice + a real keypad call on the 12 → tag `v1-keypad` (~3 days)

2.1 **[C] `haqdaar/audio/render.py`.**
  - Port the Sarvam TTS client and the stretch from `git show demo-15sep:haqdaar/voice_demo.py`
    (`:233-258`, `:265-285`).
  - One speaker per language, in `tunables`.
  - 3 requests at a time; can resume; stops on 402; reads `all_texts()`.
  - `tools/listen.py <lang> <n>`.
  - **Verify:** 0 missing, and a second run makes 0 requests.
  - **[A] listens** to 5 hi, 5 mr, 5 en and all the Marathi fixed lines. If the Marathi voice is
    bad, swap the speaker and re-render Marathi only.
2.2 **[C] Pool fix (F12):** mmap, then close the fd (`pool.py:149-159`).
  - Measure `Corpus.load`; change the hashing only if boot takes more than 3 s.
  - **Verify:** a test loads 400 clips with RLIMIT_NOFILE set to 256.
2.3 **[C] Real snapshot + `sim --snapshot`.**
  - `sim.py:181-200` gets a `--snapshot snapshots/CURRENT` flag.
  - Commit the snapshot text.
  - **Verify:** a full sim call in each language on the real snapshot; a deleted `.ulaw` makes
    the load fail (test).
2.4 **[C] `telephony/base.py` + Twilio conforms (D12).**
  - **Verify:** `test_twilio_codec.py` passes unchanged, plus a new conformance test.
2.5 **[C] `haqdaar/audio/mouth.py`.**
  - Queue, 1 s frames + mark, `clear` on a key press.
  - `#` repeats; a second `#` slows it (stretch at play time).
  - Port `PhoneAudio` from `demo-15sep:haqdaar/demo_voice.py:261-333`, keeping the deadlock fix
    (`clear()` → `loop.create_task`).
  - **Verify:** a fake-socket test: a key stops the line in < 200 ms, with no 10 s freeze.
2.6 **[C] `haqdaar/audio/turn.py`.**
  - Keys + silence timer.
  - A key pressed during a retry or "not understood" line is kept (the NOTES bug).
  - **Verify:** `test_turn.py`.
2.7 **[C] Wire `server.py`.**
  - `/answer` → stream → engine thread + mouth + turn.
  - The log keeps only a sha256 of the number.
  - **Verify:** a scripted fake call reaches `closing_farewell`.
  - **[A]** makes 3 real keypad calls (hi, mr, en); **[O]** reads the logs.
  - With the owner's OK: merge, **tag `v1-keypad`.**

### Phase 3 · Scale to 100+ schemes (~1–2 days of work; the elapsed time depends on the Groq decision)

3.1 **[C] Discovery**, new `p0_discover.py`.
  - Playwright on myscheme search: central, and state = Maharashtra.
  - Output: `candidates.csv` (slug, name, level, state, tags), 2 s between pages.
  - **Verify:** row counts printed **(re-measure)**.
3.2 **[O] Choose 110–130 schemes, the priorities and the final OCCUPATION list. [A] approves.**
  - Rules: for individuals, open now, a direct benefit, fits rural and informal-work families.
  - Bump the facets prompt version.
3.3 **[C] Scrape level, state and department** (replaces `p2_derive.py:706-708`), then run p1 on
    the full list.
  - **Verify:** the scrape report shows at least 100 kept.
3.4 **[O] Groq budget, decided with real numbers.**
  - Phase 1 logs the tokens per call. The estimate is about 4 calls × ~2.5k tokens × 120
    schemes ≈ **1.2M tokens**, which is about **6 days** on the free tier (200K/day).
  - Recommended: Groq's paid tier, likely a few dollars (**[A]** checks the price in the
    console). It also removes the free-tier limit that live calls share.
  - Otherwise: spread the run over about 6 days, doing 4.1 and 4.2 in the meantime.
  - **Verify:** quarantine rate under 15%. If aliases push it higher, **[O]** decides whether
    the alias floor goes from 3 to 2.
3.5 **[A] approves the Sarvam spend → [O] runs translate + gates + render.**
  - **Verify:**
    - the gates table shows at least 100 schemes fully passing;
    - 0 missing;
    - audio size **(re-measure, expect about 400 MB)**;
    - `make backup`.
3.6 **[C] `tools/stress.py`.**
  - 1,000 random callers via `sim --snapshot`.
  - Report: questions, turns, endings, and a **truth check** built on the D9 delivery record.
  - **Verify:** 0 crashes and 0 truth failures. **[O]** tunes the caps and `STOP_SURVIVORS` from
    this data only.
3.7 **[O] Audit and [A] listening.**
  - [O] reads 20 random schemes' cards against the source.
  - [A] listens to 10 hi + 10 mr cards and re-reads the new chips and band labels.
  - Commit the snapshot.

### Phase 4 · Voice (~3–4 days) → tag `v1-voice`

First, **[O]** measures STT round-trip time from the laptop against a US machine, and **[A]**
picks where the server runs.

4.1 **[C] `ear.py`.**
  - Sarvam STT (re-check the model), falling back to Groq Whisper.
  - 1 s padding, hint words, energy detection of speech start/end. Port from
    `demo-15sep:haqdaar/voice_demo.py:340-385,476-524`.
  - NOISE vs SILENCE; a key press wins over speech.
  - **An STT timeout counts as a failure.**
  - **Verify:** `test_ear.py` on `fixtures/audio`, plus 3 live sentences per language.
4.2 **[C] `haqdaar/model/`.**
  - Groq, JSON output, temperature 0, 2 s timeout, never raises.
  - A 429 counts as a failure; 2 failures → keypad-only.
  - Span guard: a value is kept only if its words are in the transcript.
  - **Verify:** mocked tests ("farmer" must not add "low income"), and a 30-utterance bake-off
    with p50/p95 in NOTES.
4.3 **[C] Door A**, `engine/door_a.py`.
  - Normalise, Devanagari → Latin, a stop list of generic words, token match on the aliases.
  - 1 match → read it; 2 → pick by key; 3 or more → Door B.
  - The LLM only sees a top-10 shortlist.
  - **Verify:**
    - 3 spoken forms × 40 schemes, top-1 accuracy logged;
    - live: "PM Kisan" → the name is heard in < 20 s.
4.4 **[C] Spoken answers with confirmation** ("if right press 1") for need, occupation and the
    Maharashtra question. 2 misses → the keypad menu.
  - **Verify:** sim paths.
4.5 **[C] If voice breaks → keypad for the rest of the call.**
  - **Verify:** a test that forces STT to fail.
  - **[A]** makes 3 voice calls. **Tag `v1-voice`.**

### Phase 5 · Make it solid (~2 days)

5.1 **[C] "Anything else?" loop + read-back prefetch** (cold ≤ 50 ms).
5.2 **[C] `tools/judge.py logs/`** → PASS/FAIL from the delivery log alone (T04, T16).
  - **Verify:** tests on hand-made pass and fail logs.
5.3 **[C] Hardening.**
  - `make run` restarts after a crash.
  - `make smoke` prints the checklist.
  - **[A]** runs the drills: Wi-Fi dies, the process is killed, a call after 30 min idle.
5.4 **[C] Indian provider adapter** when the number exists: one file that passes the 2.4
    conformance test, then 1 real call.

### Phase 6 · The 10-call test → tag `v1` (1 day)

**[A]** gets 10 outside callers, at least 3 per language, and all 7 hard cases happen at least
once. **[O]** runs `judge.py` → 8 or more PASS. Tag `v1`. Save 2–3 logs as evidence.

**Total:** about 15–17 working days, plus the Groq wait if you stay on the free tier.
Phase 2 on its own is already an honest keypad product.

---

## 4 · Owner jobs

- **Phase 0:** reopen VS Code.
- **Phase 1:** correct the Hindi and Marathi lines (1.11).
- **Phase 2:** listen to the voices (2.1); make 3 keypad calls (2.7).
- **Phase 3:** approve the list (3.2); decide on Groq paid vs wait (3.4); approve the Sarvam spend
  (3.5); listen (3.7).
- **Phase 4:** choose where the server runs; make 3 voice calls.
- **Phase 5:** run the drills; set up the Indian number.
- **Phase 6:** find the 10 callers.

## 5 · Verification (every step and phase)

- Opus re-runs each step's own check. An agent's report is not proof.
- End of every phase:
  - `pytest` passes;
  - `python3 -m py_compile sync_vault.py`;
  - `python3 sync_vault.py --status` is clean;
  - `.agent/TASK.md` is fully ticked;
  - PROJECT-UPDATE has a new entry;
  - the branch is pushed;
  - the owner is asked before any merge.

## 6 · Top risks

- **A card bends a rule.** Covered by the gates, the must-include eligibility numbers, Opus
  reading all 48 cards on the 12 and 20 at scale, and the pointer to the official source.
- **Groq daily limits.** Tokens are counted, and the owner decides paid vs spread-out (3.4).
- **Marathi voice at 8 kHz.** Heard in Phase 2, before the big render.
- **myscheme changes or blocks us.** The raw cache never expires and is backed up; discovery runs
  once.
- **The Indian number arrives late.** Test on +1; the provider swap is one file.

## 6b · How we work: one phase at a time

- **Nothing is built all at once.** Each phase is its own session:
  1. You say "start Phase N".
  2. I re-check that phase's steps against the code and show you the step list.
  3. Coders build it one step at a time. I review and test each step.
  4. I report back and **stop**.
- No phase starts until you say so, even if the previous one went well.
- **Right after you approve this plan, I only write it down. No code yet.** I will:
  1. Save this plan in the repo as `PLAN-V2.md`, the one file every coder reads.
  2. Add a line at the top of `NEXT-PLAN.md`: "superseded by PLAN-V2.md".
  3. Rewrite `.agent/TASK.md` as the phase list, with Phase 0 next and nothing marked in
     progress.
  4. Add the findings to `.agent/NOTES.md`, and a short entry to `PROJECT-UPDATE.md`.
  5. Tell you it's done, then wait for "start Phase 0".

## 7 · Fixed by the stress test (reviewer findings, all verified in code)

1. Unknown values were widened to ANY, which would lie → now quarantined (D6).
2. "Not Maharashtra" would have wiped out every scheme → the OTHER mask (D7).
3. The fixture states clashed with the new state question → the fixture edits are listed in 1.4.
4. G2's single words would have blocked honest Hindi/Marathi → second-person phrases only (D5).
5. The ≤9 test could not pass, and the cache key change would have wasted calls → 9 groups now,
   plus per-task versions and renamed caches.
6. No step joined the text to the snapshot, and silent stubs hid missing audio → `texts.py`
   (1.12) and `render_stubs=False`.
7. The 200K tokens/day limit was missed → 3.4, and the cache no longer expires.
8. Hindi/Marathi summaries skipped the gates → p4/p5 (D4).
9. Number-gate holes → code-computed N, required eligibility numbers, exclusions folded into the
   who-can-apply card (D3).
10. Ordering → 1.4 after 1.3, 1.6 before 1.7, sort the list itself (D1).
11. The S6 premise was false → left alone.
12. Read-back `*`/`0`, no delivery log → D8 and D9.
13. The demo code is not on `main`, and `run_demo --help` would ring the phone →
    `git show demo-15sep:`, new check in 0.5.
14. `.gitignore` could not un-ignore inside an ignored folder → `data_cache/*` plus exceptions,
    count is 62.
15. `make sim` never loaded the real snapshot → `--snapshot` (2.3); the alias test monkeypatches.
16. Bands could straddle a limit → a bit is set only if the band lies wholly inside the range.
17. The slow copy would have doubled the audio → stretched at play time (D10).
