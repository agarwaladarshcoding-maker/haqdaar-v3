# Prompt for Antigravity: finish Phase 1 (steps 1.9 to 1.14)

Copy everything below the line into Antigravity.

---

You are writing code in an existing Python repo. **The plan is already done and approved.** Do not
plan, redesign, or suggest other ways. Write the code as it is described here, run the checks, and
commit. If something here does not match the code, do the smallest change that keeps to the idea,
and write down what you did in `.agent/NOTES.md`.

## 0. Ground rules (read first, follow always)

- **Repo:** either `~/code/haqdaar-v2` or `~/Documents/haqdaar-v2` — these are two checkouts of
  ONE repo (remote `haqdaar-v3`), not two projects. Work in one at a time, `git fetch origin`
  first, and check the branch. Never hand-copy files between them; push/pull through origin.
  Branch: `step-1.9`. Never merge to `main`.
- **Python:** `.venv/bin/python`. **Tests:** `.venv/bin/python -m pytest -q` (167 pass now).
  **Lint:** `python3 -m py_compile <each changed .py file>`.
- **One commit per step**, message `step 1.N: <short what>`, then `git push`. Do the steps in order:
  1.9 → 1.10 → 1.11 → 1.12 → 1.13 → 1.14 → end.
- **Before each step:** read `.agent/TASK.md` and the last 60 lines of `.agent/NOTES.md`.
  **After each step:** tick the step in `.agent/TASK.md` (add the test count and commit hash), and
  add 2 to 6 lines to `.agent/NOTES.md`: file paths, function names, anything surprising.
- **Smallest correct change.** No renames, no clean-ups, no refactors that are not asked for here.
- **Do not change** the aliases prompt, the summary prompt, or the facets prompt text in `p2_derive.py`.
  Changing them re-runs paid calls.
- **Never invent spoken wording.** All text people will hear is given in this prompt, in
  `haqdaar-v2-brain/tickets/T23.md`, or comes from the pipeline (Groq / Sarvam). If you need a
  sentence that is not given, write `TODO-WORDING` in its place and list it in NOTES.
- **Never claim a test passed without running it.** Paste the last lines of the output into NOTES.
- **Every test must work offline.** Mock Groq and Sarvam in tests, the way
  `tests/test_groq_ledger.py` mocks `httpx.Client` (`_FakeResponse`, `_FakeHttpxClient`,
  `_patch_groq_response`).
- **Paid calls allowed in this whole task:** Groq ≤ 15 requests, Sarvam Translate ≤ 60,000
  characters. No text-to-speech at all. If you would go past a limit, stop and report.
- **Stop and report (do not work around) if:** a test you did not touch breaks and the fix is not
  obvious; the Sarvam probe in 1.10 fails; fewer than 10 of the 12 schemes pass the gates in 1.11.
- Keys in `.env`: `GROQ_API_KEY`, `SARVAM_API_KEY`. Read them with `load_dotenv()` + `os.environ`,
  same as `GroqClient`.

## 1. What already exists (so you do not have to search)

- Pipeline code: `haqdaar/data/pipeline/`. `p1_scrape.py`, `p2_derive.py`, `p6_snapshot.py`.
- Constants: `haqdaar/contracts/tunables.py` (each read from env with a default). Examples:
  `GROQ_MODEL`, `EXTRACT_CACHE_DIR="data_cache/extract"`, `DERIVED_DIR="data_cache/derived"`,
  `REPORTS_DIR="data_cache/reports"`, `RAW_CACHE_DIR="data_cache/raw"`, `MIN_SCHEMES=8`,
  `SUMMARY_WORD_TARGET=35`. Add new constants here in the same style.
- Word lists: `haqdaar/contracts/vocab.py`:
  `KEYPAD_LISTS` (box → tuple of values, in keypad order), `LABELS` (value → `{"en","hi","mr"}`),
  `FORBIDDEN` (lang → tuple of phrases), `find_forbidden(text, lang) -> str | None`.
- `haqdaar/contracts/types.py`: `FIXED_LINE_IDS` (50 ids), `SCHEME_CHUNKS` = `name, summary,
  benefit_text, who_can_apply, documents, how_to_apply`, `compute_render_key(text, lang, ...)`.
- `p2_derive.py`:
  - `GroqClient(api_key=None, ledger_path=None)`, `.call(system_prompt, user_prompt, task="", slug="") -> dict`
    (JSON mode, retries, writes `data_cache/reports/groq_usage.jsonl`, keeps `.requests`,
    `.prompt_tokens`, `.completion_tokens`).
  - Cache: `PROMPT_VERSIONS` dict (L279), `get_cache_path(sha, task, cache_dir)`,
    `read_from_cache(sha, task, cache_dir)`, `write_to_cache(sha, task, data, cache_dir)`.
  - Derived output: `data_cache/derived/schemes.jsonl` + one `<slug>.json` per scheme. Each record
    has `scheme_id` (= slug), `source_sha256`, `scheme_name_{en,hi,mr}`, facets (`age`,
    `income_band`, ...), and `chunks[lang] = {name, summary, benefit_text, who_can_apply,
    documents, how_to_apply}`. Today en chunks hold the raw source sections; hi/mr hold only
    name and summary (the other four are `""`).
  - L783-799: reads `summary_en/hi/mr`, checks `vocab.find_forbidden` on all three, and applies the
    word cap.
- Raw source: `data_cache/raw/<slug>.json`, keys `benefits`, `eligibility`, `exclusions`,
  `documents`, `apply`, `source_sha256`, `fetched_on`.
- `p6_snapshot.py`: `build_snapshot(schemes_data, templates_data=None, snapshot_id=None,
  snapshots_dir=None, audio_dir=None, render_stubs=True, enforce_readback_gate=False)`.
  `build_range_bands` makes the age/income band codes. Fixed lines at about L450-468 are **fake**:
  they hash `f"{line_id}_{lang}"`, not real text. Chips at about L470 hash the raw value, not the
  label. Chunks at L491-544 take `scheme["chunks"][lang][chunk]`. `__main__` (L617) builds from an
  empty list.
- `p1_scrape.py` `is_cache_valid` L188-203: the raw cache expires after 1 day.
- `Makefile`: `PYTHON ?=` (uses `.venv`), targets `pipeline-scrape`, `pipeline-extract`,
  `backup`, `sim`, `test`. `pipeline` only prints a placeholder.
- `.gitignore`: `data_cache/*` is ignored except `raw/`, `derived/`, `extract/`. `reports/` is
  ignored (good). `audio/` is ignored.
- `haqdaar-v2-brain/tickets/T23.md` L103-236: fixed-line text as a markdown table
  `| # | \`id\` | *"English"* | *"Hindi"* | *"Marathi"* |` (`greeting_trilingual` has no `#` column).

---

## Step 1.9 · Spoken cards → new `haqdaar/data/pipeline/p3_cards.py`

**Goal:** for each of the 12 schemes, 4 short English cards (`benefit_text`, `who_can_apply`,
`documents`, `how_to_apply`) that are safe to speak on a phone call.

1. `tunables.py`: add `CARD_MAX_WORDS = 55`, `CARD_OVERLAP_MIN = 0.6`, and
   `CARDS_FILE = "data_cache/derived/cards.jsonl"`.
2. `p2_derive.py`: add `"cards": 1` to `PROMPT_VERSIONS`. No other change in p2 for this step.
3. `p3_cards.py`:
   - `CARD_FIELDS = ("benefit_text", "who_can_apply", "documents", "how_to_apply")`
   - `CSC_SENTENCE_EN = "The CSC centre will tell you the full list of papers."`
   - `build_card_prompts(raw: dict, record: dict) -> tuple[str, str]` returns (system, user) using
     the text below **exactly**.
   - `derive_cards(raw, record, client=None, cache_dir=EXTRACT_CACHE_DIR) -> tuple[dict, bool]`:
     cache on `(raw["source_sha256"], "cards")` via `read_from_cache` / `write_to_cache`; on a miss
     call `client.call(system, user, task="cards", slug=slug)`. Returns (cards, from_cache).
     Create the `GroqClient` only on the first cache miss (so a warm run needs no key).
   - After the model answers, code appends `" " + CSC_SENTENCE_EN` to `documents`.
   - `gate_card_en(field, text, raw, record) -> list[str]` returns a list of failure reasons
     (empty = pass). Gates:
     - **numbers:** every number in the card is in the source. Number = regex
       `\d[\d,]*(?:\.\d+)?`, then remove commas. Source = all five raw sections joined. Skip the
       CSC sentence (it has no numbers anyway).
     - **facet numbers** (only for `who_can_apply`): the `min` and `max` of `record["age"]` and
       `record["income_band"]` (if not None) must each appear as a number in the card. Parse the
       range with the same helper p6 uses (`_parse_range_value` in `p6_snapshot.py`; import it).
     - **forbidden:** `vocab.find_forbidden(text, "en")` is None.
     - **length:** word count of the card without the CSC sentence ≤ `CARD_MAX_WORDS`.
     - **overlap:** content words = lowercase `[a-z]+` tokens of length ≥ 4, minus this stop list:
       `{"this","that","with","from","have","will","they","their","them","which","also","into",
       "under","scheme","after","before","other","there","these","those","such","must","should",
       "would","could","about","more","than","your","when","where","what"}`. Overlap = share of
       the card's content words that are also in the source's content words. Must be
       ≥ `CARD_OVERLAP_MIN`. Skip the CSC sentence.
   - `run_cards(derived_dir=DERIVED_DIR, raw_dir=RAW_CACHE_DIR, cache_dir=EXTRACT_CACHE_DIR,
     reports_dir=REPORTS_DIR) -> int`: for each record in `schemes.jsonl`, derive + gate, write one
     line per scheme to `cards.jsonl`:
     `{"slug", "source_sha256", "prompt_version", "cards": {4 fields}, "gates": {field: [reasons]}, "ok": bool}`.
     Write `data_cache/reports/cards.json` with the failures. One scheme's Groq error must not stop
     the others (put it in the report with `ok: false`). Print: schemes, ok count, Groq requests
     made. Return 0.
   - `__main__`: `sys.exit(run_cards())`.
   - **No retry** on gate failure. Failures are for the human to read.
4. Prompt text (copy exactly):

   System:
   ```
   You write short spoken cards about one Indian government scheme. They are read aloud on a phone call to people with little schooling.
   Use only facts that are in the SOURCE. Do not add any fact, amount, date, age, limit or condition that is not in the SOURCE.
   Write plain, short English sentences. No lists, no bullet marks, no brackets, no web links.
   Write every number with the same digits as the SOURCE. Do not change 200000 to 2 lakh or the other way.
   Never tell the listener they are eligible, they qualify, or they will get anything. Describe the scheme: "Farmers get ...", "The scheme gives ...".
   Each card has at most 55 words.
   Return JSON only: {"benefit_text": "...", "who_can_apply": "...", "documents": "...", "how_to_apply": "..."}
   ```

   User (fill the `{...}`; write `none` when a value is missing or empty):
   ```
   SCHEME: {scheme_name_en}
   AGE RULE: {age min} to {age max} years
   INCOME RULE: {income min} to {income max} rupees a year

   benefit_text = what the scheme gives, with the amounts.
   who_can_apply = who can apply, in 2 or 3 sentences. If there is an AGE RULE or INCOME RULE above, say those numbers.
   documents = only the 3 to 5 most important papers.
   how_to_apply = the first steps: where to go and what to take.

   SOURCE BENEFITS:
   {benefits}

   SOURCE ELIGIBILITY:
   {eligibility}

   SOURCE EXCLUSIONS:
   {exclusions}

   SOURCE DOCUMENTS:
   {documents}

   SOURCE HOW TO APPLY:
   {apply}
   ```
5. `Makefile`: target `pipeline-cards: $(PYTHON) -m haqdaar.data.pipeline.p3_cards` (add to `.PHONY`).
6. New `tests/test_cards.py` (mock Groq): each gate fails on a bad card and passes on a good one;
   the CSC sentence is appended once; a warm second run makes 0 requests; one scheme erroring still
   writes the others.
7. **Real run (paid, 12 Groq requests):** `make pipeline-cards`. Then run it again: must print
   0 requests. Check `wc -l data_cache/derived/cards.jsonl` = 12 and the ledger grew by exactly 12
   `cards` lines. Put in NOTES: ok count, and each failing slug with its reasons. Commit
   `cards.jsonl` and the new `data_cache/extract/*_cards_v1.json` files.

---

## Step 1.10 · Translation → new `haqdaar/data/pipeline/p4_translate.py`

**Goal:** Hindi and Marathi for each scheme's English summary and 4 cards, from Sarvam Translate.

1. **Probe first.** New `tools/probe_translate.py`: one POST to `https://api.sarvam.ai/translate`
   with headers `api-subscription-key: <SARVAM_API_KEY>`, `Content-Type: application/json`, and body
   ```json
   {"input": "Farmers get 6000 rupees a year in three parts.", "source_language_code": "en-IN",
    "target_language_code": "hi-IN", "model": "sarvam-translate:v1", "mode": "formal",
    "numerals_format": "international"}
   ```
   Print the status code and the JSON. Use `httpx` (already a dependency). Run it once.
   - If status is 200 and there is a `translated_text` field with Devanagari text and the digits
     `6000`: write the model name, the request and response fields, and the character limit
     (2000 for `sarvam-translate:v1`) into NOTES, then continue.
   - **Otherwise stop** and report the full response. Do not try other models on your own.
2. `tunables.py`: add `SARVAM_TRANSLATE_MODEL = "sarvam-translate:v1"`,
   `SARVAM_TRANSLATE_MAX_CHARS = 2000`, `SARVAM_TIMEOUT_S = 30.0`, `SARVAM_POLITE_DELAY_S = 0.5`,
   `TRANSLATE_CACHE_DIR = "data_cache/translate"`,
   `TRANSLATIONS_FILE = "data_cache/derived/translations.jsonl"`.
3. `.gitignore`: add `!data_cache/translate/` next to the other `!data_cache/...` lines.
4. `p4_translate.py`:
   - `class SarvamTranslateClient(api_key=None, ledger_path=None)`: `.translate(text, lang, key="") -> str`
     where `lang` is `"hi"` or `"mr"` (→ `hi-IN` / `mr-IN`). Up to 3 tries on 429/5xx with a
     2 s sleep. Raises `ValueError` if `len(text) > SARVAM_TRANSLATE_MAX_CHARS`. Appends
     `{"ts","task":"translate","key","lang","chars","model"}` to
     `data_cache/reports/sarvam_usage.jsonl`. Keeps `.requests` and `.chars`.
   - Cache: file `data_cache/translate/<sha>.json`, `sha = sha256(text + "\n" + lang + "\n" + model)`,
     content `{"text","lang","model","translated"}`. Write to `<file>.part` then `os.replace`.
     Create the client only on the first cache miss.
   - `run_translate(...) -> int`: for each record in `schemes.jsonl` whose line in `cards.jsonl`
     has `ok: true`: translate `summary_en` (from `record["chunks"]["en"]["summary"]`) and the 4
     cards, into hi and mr (that is 10 texts per scheme). Write one line per (slug, field, lang) to
     `translations.jsonl`: `{"slug","field","lang","text","en_text","model"}`, with `field` one of
     `summary` + the 4 card fields. Also expose `translate_text(text, lang) -> str` (cached) for
     step 1.12. One scheme's error must not stop the others. Print: texts, requests made, chars sent.
5. `p2_derive.py`: stop using the model's Hindi/Marathi summary. Keep the prompt and the Groq
   call as they are. In the record, set `chunks["hi"]["summary"]` and `chunks["mr"]["summary"]`
   to `""` (p4 fills them), and at L783-799 run the forbidden check and word cap on `summary_en`
   only. Re-run `make pipeline-extract`: must make **0** Groq requests. Fix any test that
   expected the hi/mr summary in chunks (say which in NOTES).
6. `Makefile`: `pipeline-translate: $(PYTHON) -m haqdaar.data.pipeline.p4_translate`.
7. New `tests/test_translate.py` (mock httpx): cache hit makes 0 requests; text over the limit
   raises; ledger line written; a scheme with `ok: false` cards is skipped.
8. **Real run (paid, about 120 requests, about 40k characters):** `make pipeline-translate`, then
   again (must print 0 requests). `wc -l translations.jsonl` = (schemes with ok cards) × 10.
   Commit `data_cache/translate/` and `translations.jsonl`.

---

## Step 1.11 · Gates → new `haqdaar/data/pipeline/p5_gates.py` + `make pipeline-gates`

**Goal:** check every Hindi/Marathi text against its English before it can be spoken.

1. `tunables.py`: `GATE_LENGTH_RATIO_MAX = 1.6`, `GATE_DEVANAGARI_MIN = 0.8`.
2. `p5_gates.py`, each gate a pure function returning `None` (pass) or a short reason string:
   - `g1_numbers(en, tr)`: the set of numbers in `tr` equals the set in `en`. Before comparing,
     turn Devanagari digits `०-९` into `0-9` and remove commas. Same number regex as p3.
   - `g2_forbidden(tr, lang)`: `vocab.find_forbidden(tr, lang)` is None. ("पात्रता" must pass.)
   - `g3_length(en, tr)`: `len(tr) <= GATE_LENGTH_RATIO_MAX * len(en)`.
   - `g4_script(en, tr)`: of the letters in `tr` (chars where `unicodedata.category(c)` starts
     with `L` or `M`), at least `GATE_DEVANAGARI_MIN` are in U+0900–U+097F; and
     `tr.strip() != en.strip()`.
   - `g5_complete(record, translations)`: every one of the 6 `SCHEME_CHUNKS` has non-empty text in
     en, hi and mr (en name/summary from the record, en cards from `cards.jsonl`, hi/mr name from
     `scheme_name_{lang}`, hi/mr others from `translations.jsonl`).
   - `check_pair(en, tr, lang) -> list[str]` runs G1–G4.
   - `run_gates(...) -> int`: for each scheme, run G1–G4 on every (field, lang) text and G5 on the
     scheme. Write `data_cache/reports/gates.json`:
     `{"schemes": {slug: {"ok": bool, "failures": [{"field","lang","gate","reason"}]}}, "passed": N, "total": M}`.
     Schemes with `ok: false` cards count as failed ("cards"). Print passed/total. Return 0.
     (Step 1.12 adds the lines check to this same command.)
3. `Makefile`: `pipeline-gates: $(PYTHON) -m haqdaar.data.pipeline.p5_gates`.
4. New `tests/test_gates.py`: one pass test and one fail test per gate; "पात्रता" passes G2.
5. **Run** `make pipeline-gates`. Write passed/total and every failure into NOTES. **If fewer than
   10 of 12 pass, stop and report.** Do not loosen a gate or edit a translation to make it pass.

---

## Step 1.12 · Fixed lines → `haqdaar/audio/lines.yaml` + `tools/lines_sheet.py`

**Goal:** real text for every fixed line, in 3 languages, in one file.

1. **Generated lines (not in yaml):** `keypad_gender`, `keypad_social_category`, `keypad_age`,
   `keypad_income_band`, `keypad_occupation`. Also `opener_prompt` gets a menu added (see 1.13).
   Every other id in `FIXED_LINE_IDS` goes in the yaml, including `opener_prompt` (its lead text).
2. Format (use `yaml.safe_load`; add `pyyaml` to requirements only if it is not installed):
   ```yaml
   consent_notice:
     en: "..."
     hi: "..."
     mr: "..."
   ```
3. **Text source, in this order:**
   - T23.md table: copy en/hi/mr exactly (strip the `*"` and `"*`). Write a one-off script
     `tools/t23_to_lines.py` that parses the table and writes the yaml, so there is no hand copying.
     Skip struck-out (`~~`) rows. Skip the 5 generated ids.
   - These 3 ids are not in T23. Use this text:

     | id | en | hi | mr |
     |---|---|---|---|
     | `state_q_maharashtra` | Do you live in Maharashtra? For yes press 1, for no press 2. If you don't know, press 0. | क्या आप महाराष्ट्र में रहते हैं? हाँ के लिए 1 दबाइए, नहीं के लिए 2 दबाइए। पता न हो तो 0 दबाइए। | तुम्ही महाराष्ट्रात राहता का? होय साठी 1 दाबा, नाही साठी 2 दाबा. माहीत नसेल तर 0 दाबा. |
     | `results_more_prompt` | Here are more schemes. | ये रहीं कुछ और योजनाएँ। | ही आणखी काही योजना आहेत. |
     | `confirm_bundle_opener` | Let me check what I heard. | मैंने जो सुना, उसे एक बार पक्का कर लेती हूँ। | मी जे ऐकलं ते एकदा पक्कं करते. |

   - Any id still missing hi or mr: fill it with `p4_translate.translate_text(en, lang)` and add
     `# machine` on that line. Any id missing en: write `TODO-WORDING` and list it in NOTES.
4. New `haqdaar/audio/lines.py`: `GENERATED_LINE_IDS` (the 5 keypad ids) and
   `load_lines(path=<repo>/haqdaar/audio/lines.yaml) -> dict[str, dict[str, str]]`. It raises
   `ValueError` if an id from `FIXED_LINE_IDS` minus `GENERATED_LINE_IDS` is missing, if there is an
   extra id, if a language is missing or empty, or if any text contains `TODO-WORDING`.
5. `p5_gates.py`: also check every line's hi and mr with `check_pair` against its en. Put results
   under `"lines"` in `gates.json`. Line failures are reported, not fatal.
6. `tools/lines_sheet.py` writes `lines_sheet.md` at the repo root. Top line:
   `Edit haqdaar/audio/lines.yaml, not this file. Run python -m tools.lines_sheet to refresh.`
   Then a table `id | English | Hindi | Marathi | gates` (gates = "ok" or the reasons), then a
   table of every `vocab.LABELS` entry (value | en | hi | mr), then the generated menus from 1.13
   in all 3 languages (add this part after 1.13 is done).
7. New `tests/test_lines.py`: the real `lines.yaml` loads; every id has 3 non-empty languages; a
   yaml missing one id raises; every hi/mr line passes G2 (G1, G3, G4 failures are allowed but
   listed in NOTES).

---

## Step 1.13 · One text list → new `haqdaar/data/pipeline/texts.py`, p6 uses it

**Goal:** one function yields every text the call can speak. p6 hashes that real text, not
placeholders.

1. `texts.py`:
   - Menu templates (copy exactly):
     `MENU_ITEM = {"en": "For {label}, press {n}.", "hi": "{label} के लिए {n} दबाइए।", "mr": "{label} साठी {n} दाबा."}`
   - Band labels (codes come from `build_range_bands`; handle each code shape it can produce, and
     add a test for each):
     - age `lo-hi`: `{"en": "{lo} to {hi} years", "hi": "{lo} से {hi} साल", "mr": "{lo} ते {hi} वर्षे"}`
     - income `lo-hi`: `{"en": "{lo} to {hi} rupees a year", "hi": "साल में {lo} से {hi} रुपये", "mr": "वर्षाला {lo} ते {hi} रुपये"}`
     - open top (`lo` and up) and open bottom (below `hi`), if `build_range_bands` makes them:
       en `"{lo} years or more"` / `"under {hi} years"`; hi `"{lo} साल या ज़्यादा"` / `"{hi} साल से कम"`;
       mr `"{lo} वर्षे किंवा जास्त"` / `"{hi} वर्षांपेक्षा कमी"`. For income put `rupees a year` /
       `रुपये सालाना` / `रुपये वार्षिक` in place of the years word.
       The band code values are not ages (e.g. `lo` is the band's first year, `hi` its last year):
       read `build_range_bands` to get this right and say in NOTES what you found.
   - `menu_text(box, values, lang) -> str`: labels (vocab `LABELS`, or band labels for age/income)
     joined as `MENU_ITEM` in the given order, `n` = 1-based position, one space between items.
   - `all_texts(schemes, cards, translations, lines, bands) -> Iterator[tuple[str, str, str]]`
     yields `(key, lang, text)` for lang in en/hi/mr:
     - `line:<id>` for every yaml line, except `opener_prompt` = yaml `opener_prompt` + " " +
       `menu_text("category", KEYPAD_LISTS["category"], lang)`.
     - `line:keypad_<box>` for gender, social_category, occupation = yaml `q_<box>` + " " +
       menu of `KEYPAD_LISTS[box]`; for age and income_band = yaml `q_<box>` + " " + menu of
       `bands[box]`.
     - `chip:<box>:<value>` = label of that value (vocab label or band label) for every keypad value.
     - `chunk:<slug>:<chunk>` for the 6 `SCHEME_CHUNKS`: name = `scheme_name_{lang}`; summary en =
       `chunks["en"]["summary"]`; the 4 card fields en = `cards.jsonl`; hi/mr summary and cards =
       `translations.jsonl`.
     - `greeting_trilingual`: keep the special case p6 has today (same `lang` argument it uses
       now), but the text is yaml `hi + " " + mr + " " + en`.
   - `load_inputs(derived_dir, gates_path) -> (schemes, cards, translations, lines)`: reads the
     files and **drops schemes that failed gates** (print their slugs).
2. `p6_snapshot.py`, smallest change:
   - `build_snapshot` gets a new optional param `texts: dict[tuple[str, str], str] | None = None`
     (key, lang → text). When it is None, keep today's behaviour exactly (so old tests still pass).
   - When given: fixed-line render keys = `compute_render_key(texts[("line:"+id, lang)], lang)`,
     chip keys use `texts[("chip:...", lang)]`, chunk keys use `texts[("chunk:...", lang)]`.
   - Because age/income bands are computed inside p6, compute them first, then call
     `all_texts(...)` from the `__main__` path via a small helper `texts_for(schemes_data, ...)`.
     Do not add a p6 → p2 import cycle.
   - `__main__`: argparse with `--stubs` (default off). Load real inputs with `load_inputs`, build
     with `enforce_readback_gate=True`, `render_stubs=args.stubs`. Print: schemes, texts per
     language, render keys. With stubs off, missing audio is fine (audio comes in Phase 2); make
     sure nothing crashes because of it.
   - `sim` and `make demo-fixture` must still work: if they call `build_snapshot`, pass
     `render_stubs=True` (check `haqdaar/sim.py`).
3. `tools/lines_sheet.py`: add the generated menus section now.
4. New `tests/test_texts.py`: on a small fake input (2 schemes), the set of render keys p6 writes
   equals `{compute_render_key(t, lang) for (k, lang, t) in all_texts(...)}` (greeting handled the
   same way on both sides); `menu_text("gender", ...)` in hi is exactly
   `"<label1> के लिए 1 दबाइए। <label2> के लिए 2 दबाइए। <label3> के लिए 3 दबाइए।"`.
5. **Real build:** `.venv/bin/python -m haqdaar.data.pipeline.p6_snapshot`. Paste the counts into
   NOTES. Do not commit `snapshots/` or `audio/` output (add `snapshots/` to `.gitignore` if git
   shows it as new).

---

## Step 1.14 · `make pipeline` + `make pipeline-cost`

1. `p1_scrape.py` `is_cache_valid`: remove the age check (L188-203). A raw file that passes the
   other checks is valid for ever. New scrapes happen only with `--rescrape`. Update any test that
   expected expiry.
2. **Paid-call guard.** New `haqdaar/data/pipeline/paid.py`:
   `ALLOW_PAID = False`, `class PaidCallBlocked(RuntimeError)`, `def check(what: str)` raises
   `PaidCallBlocked(f"paid call needed: {what}; re-run with --yes")` when `ALLOW_PAID` is False.
   Call `paid.check(...)` at the top of `GroqClient.call` and `SarvamTranslateClient.translate`.
   Existing tests must not break: set `paid.ALLOW_PAID = True` in `tests/conftest.py` with an
   autouse fixture (tests mock the network anyway), and existing `__main__` entry points
   (`p2`, `p3`, `p4`) set it to True too, so `make pipeline-extract` etc. keep working as now.
3. New `haqdaar/data/pipeline/run.py`: argparse `--rescrape`, `--yes`. Sets
   `paid.ALLOW_PAID = args.yes`. Runs in order: p1 (only with `--rescrape`) → p2
   (`run_pipeline_extract`) → p3 (`run_cards`) → p4 (`run_translate`) → p5 (`run_gates`) → p6 real
   build (no stubs). On `PaidCallBlocked`: print the message and exit 2. At the end print the
   Groq requests and Sarvam requests/chars made in this run.
4. New `tools/pipeline_cost.py`: reads `groq_usage.jsonl` and `sarvam_usage.jsonl`; prints per
   task: requests, prompt tokens, completion tokens (Groq) and requests, characters (Sarvam); and a
   total. Missing files = zeros.
5. `Makefile`: replace the placeholder `pipeline` recipe with
   `$(PYTHON) -m haqdaar.data.pipeline.run $(if $(YES),--yes,) $(if $(RESCRAPE),--rescrape,)`, and
   add `pipeline-cost: $(PYTHON) -m tools.pipeline_cost`. Add both to `.PHONY`.
6. Tests: `tests/test_paid.py`: with `ALLOW_PAID = False`, a `GroqClient.call` cache miss raises
   `PaidCallBlocked` before any HTTP; `pipeline_cost` sums a small fake ledger right.
7. **Verify:** `make pipeline-cost` (paste output into NOTES). Then `make pipeline YES=1` on the
   warm cache: the Groq and Sarvam ledgers must not grow (count lines before and after, write both
   numbers in NOTES). Then `make pipeline` without YES must also finish (everything is cached).

---

## End of phase

1. `.venv/bin/python -m pytest -q`: all pass. Paste the last line into NOTES.
2. `python3 -m py_compile sync_vault.py`, then `python3 sync_vault.py --status`. If it lists
   changes, run `python3 sync_vault.py --sync`. Watch for `created:` dates being changed; if so,
   stop and report.
3. Re-read `.agent/TASK.md`: every Phase 1 step ticked, with commit hashes.
4. Add a short entry at the top of `PROJECT-UPDATE.md` in plain, simple words: what Phase 1 now
   does, pass counts, paid usage (from `make pipeline-cost`), and what Adarsh must do next: open
   `lines_sheet.md` and fix the Hindi/Marathi lines and menu labels in `haqdaar/audio/lines.yaml`.
5. Commit, `git push`. Do not merge. Do not start Phase 2.
6. Final report, a few lines: what changed, test count, gates passed/total, Groq requests and
   Sarvam characters used, and any `TODO-WORDING` or stop that happened.
