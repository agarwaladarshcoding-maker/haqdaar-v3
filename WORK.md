# WORK.md — the running dispatch file

**This file is the handshake between you, Antigravity (Gemini), and Claude Code.**
It is not part of the vault and is not governed by `RULES.md`. It is the operational layer:
what to run next, what to paste where, and what already happened.

## How we use it

| Who | Does what |
|---|---|
| **You** | Paste the work orders below into Antigravity. Run the verify commands. Write anything you did outside this file into **§8 What I did extra**. |
| **Antigravity (Gemini)** | Writes the code for exactly one step at a time. Never touches this file. |
| **Claude Code (me)** | Reads §8 + reruns the verify commands, reviews the step, updates §2 and §6, and writes the next work order. |

**Rule:** one step in flight at a time. Do not paste work order N+1 until N is reviewed.
**Rule:** if you change anything by hand — a key, a file, a decision, a path — put one line in §8.
Anything not in this file or on disk, I do not know about.

## 👉 Start here every morning: `work/<today>.md`

**This file is the plan. `work/` is your day.** Open the dated file, work top to bottom, tick boxes.
Anything needing your hands — an account, a phone, a card, a decision — is there, not here.

| File | What it is |
|---|---|
| [`work/2026-09-10.md`](work/2026-09-10.md) | **Closed 11 Sep** — git, venv, FileVault, Groq key. Nothing outstanding |
| [`work/2026-09-11.md`](work/2026-09-11.md) | **← TODAY** — Steps 0, 1, 2 + the remaining accounts + the phone call |
| [`work/TEMPLATE.md`](work/TEMPLATE.md) | Copy to `work/<date>.md` for a new day |

At the end of each day, tell me what merged and what slipped. I write the next day's file, and
update §2 and §6 here.

---

## 1 · Where the truth lives

- **Binding governance:** `haqdaar-v2-brain/RULES.md`
- **Sole source of truth for decisions:** `haqdaar-v2-brain/maps/wayfinder-map.md` (currently **rev 27**).
  `maps/history/` is version support only — gaps in it are not findings (D9).
- **Docs the agents read:** `haqdaar-v2-brain/docs/` — `build-plan.md`, `architecture.md`,
  `interfaces.md`, `review.md`, `today.md`, `data-contract.md`, `test-plan.md`
- **You edit** `source-docs/`, then run `python3 sync_vault.py --sync`. Never hand-edit the vault.

> **Path note:** `build-plan.md` and `today.md` were written for a repo where the vault sits at
> `brain/`. Here it sits at `haqdaar-v2-brain/`. Rev 27 allows both. Every prompt below already
> uses the correct local path — use them verbatim rather than the ones inside the docs.

---

## 2 · Current state — verified 2026-09-11

**Decisions: all closed.** D1 Groq free tier · D2 D-day **14 Sep** · D3 minimax planner, day one
· D4/D5/D6 restored · D8 lazy tiered audio pool · D9 map source-of-truth. D7 is a measurement
Step 14 produces, not an open question. **Nothing is waiting on you to decide.**

**Vault:** clean. 65 source files synced (27 tickets, 23 maps, 13 docs, 4 briefs), 0 dirty.

**Environment (all of 10 Sep's setup is closed):** git repo live on `main` · `.venv` on Python 3.11,
`pytest -q` -> **10 passed** · FileVault on · laptop-sleep setting ruled N/A by you, replaced by
`caffeinate -dimsu make run` in the demo runbook · **`GROQ_API_KEY` in `.env`, verified live**
(8,000 TPM / 1,000 RPD / 200K TPD per model — measured, not read off the docs page).
**Still owed: Sarvam, Twilio, ngrok, Plivo.** Twilio + ngrok are the only ones blocking a step you
could otherwise start today (Step 1).

**Code that exists and passes:**

| Path | Lines | Step | State |
|---|---|---|---|
| `haqdaar/contracts/types.py` | 204 | 2 (part) | types + markers present, **`log_schema.py` missing** |
| `haqdaar/contracts/tunables.py` | 50 | 2 (part) | both caps present |
| `haqdaar/audio/pool.py` | 232 | 11 | tier 0 pin + mmap/LRU + tier-2 behind flag |
| `haqdaar/data/corpus.py` | 346 | 11 | load verifies existence + digest, returns RenderKey |
| `haqdaar/data/pipeline/p6_snapshot.py` | 484 | 11 | writes the five snapshot files |
| `tests/test_corpus.py` | 422 | 11 | **10 passed** — all 7 hard constraints covered |

**Code that does not exist yet:** `server.py` · `sim.py` · `contracts/log_schema.py` ·
`engine/` (filter, planner, terminals, call) · `model/` · `audio/telephony/twilio.py` ·
`audio/ear.py` `mouth.py` `turn.py` · `data/log.py` · `fixtures/` · `Makefile` ·
`pyproject.toml` · `.env.example` · `snapshots/` · `data_cache/` · `audio/`

**So:** Step 11 is built and unit-tested, but **Steps 0–10 are not**, and Step 11's real
*"Done when"* (`make pipeline` end to end, sim against the real snapshot) cannot run until they are.
The build went out of order. That is recoverable and no work is wasted — but the queue in §6
puts it back in order.

---

## 3 · Two things to settle before the next work order  — ✅ **BOTH CLOSED 10 Sep**

*Kept for the record only. Neither blocks anything; skip to §6.*

### 3a · Git — ✅ done, `main` has 3 commits

~~This folder is **not a git repo**.~~ The build plan's entire loop is *branch per step → review →
merge*, and its safety property is that a bad Antigravity run is one `git checkout .` away from
gone. Without it, an agent that misreads a step overwrites 1,761 working lines with no undo.
You do not need GitHub for this — a local repo gives you the whole safety net.

```bash
cd /Users/adarshagarwala/Documents/haqdaar-v2
git init -b main
printf '.env\nlogs/\naudio/\ndata_cache/\n.venv/\n__pycache__/\n*.py[cod]\n.pytest_cache/\nnode_modules/\n.agent/\n.DS_Store\nhaqdaar-v2-brain/.obsidian/workspace*.json\n' > .gitignore
git add -A && git commit -m "baseline: vault rev 27, step 11 code, 10 tests passing"
```

**If you say no to git,** say so in §8 and I will rewrite every work order to snapshot the tree
into `_backup/<step>/` with `rsync` before Antigravity starts. It is worse, but it works.

### 3b · Python — ✅ done, `.venv` on 3.11, `pytest -q` -> 10 passed

~~`python3` is Homebrew **3.14** and has no pytest. Your 10 tests only pass under
`/Library/Frameworks/Python.framework/Versions/3.14/bin/pytest`. The build plan pins **3.11**,
which you have at `/opt/homebrew/bin/python3.11`. Fix it once:

```bash
cd /Users/adarshagarwala/Documents/haqdaar-v2
/opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install fastapi 'uvicorn[standard]' websockets httpx pydantic python-dotenv pyyaml pytest pytest-asyncio
pytest -q          # expect: 10 passed
```

~~Fix it once.~~ **Still true and still the one thing you must remember: run
`source .venv/bin/activate` in every terminal, including Antigravity's.**

---

## 4 · The loop, per step

1. **You:** `git checkout -b step-NN` (after 3a)
2. **You → Antigravity:** paste the work order from §6.
3. **You:** run the **Verify** commands in the work order. Paste real output into §8 if it differs.
4. **You → Claude Code:** paste the review block from §7 with `N` filled in.
5. **On "safe to merge: yes":**
   ```bash
   git checkout main && git merge --no-ff step-NN -m "step NN: <name>"
   ```
6. **You:** tell me it merged. I update §2 and §6.

---

## 5 · Command cheat sheet

```bash
cd /Users/adarshagarwala/Documents/haqdaar-v2 && source .venv/bin/activate

pytest -q                             # tests
python3 -m py_compile sync_vault.py   # lint / syntax
python3 sync_vault.py --status        # vault parity — expect 0 dirty
python3 sync_vault.py --sync          # after ANY edit to source-docs/
python3 sync_vault.py --watch         # auto-sync daemon while you write docs
```

**After editing anything in `source-docs/`, run `--sync` before you dispatch an agent.**
Agents read the vault, not `source-docs/`. Skip the sync and they build against stale docs.

---

## 6 · The queue

Order is **0 → 2 → 3 → 4 → 5 → 6**, then the pipeline steps. This is the shortest path to a
complete keypad call in the simulator, which is the `v1-keypad` demoable product. **Step 1
(telephony smoke) is unblocked only once Twilio + ngrok exist** — see §6a; it can slot in any time.

### ▶ NEXT — Step 0 · Repo and rules

**Paste into Antigravity:**

> Implement **Step 0** of `haqdaar-v2-brain/docs/build-plan.md`. Follow `AGENTS.md`.
> Read `haqdaar-v2-brain/docs/architecture.md` §4 before writing code.
> Do nothing outside this step.
>
> Two local deviations from the step text, both already ratified — apply them:
> 1. The vault is already vendored at `haqdaar-v2-brain/`, not `brain/`. **Do not move it, do not
>    copy it, do not create `brain/`.** Map rev 27 permits either name.
> 2. `AGENTS.md` already exists at the repo root and is correct. **Do not rewrite it.** Add
>    `CLAUDE.md` that imports it, per the step.
>
> Everything else in Step 0 stands: `pyproject.toml` (Python 3.11), the `Makefile` with
> `run · sim · test · demo-fixture · pipeline · smoke`, `.env.example`, the `.gitignore` entries,
> and the empty package tree from architecture §4 — including `audio/` as a **flat top-level pool**,
> never nested under `snapshots/`.
>
> Do not touch `haqdaar/contracts/`, `haqdaar/audio/pool.py`, `haqdaar/data/corpus.py`,
> `haqdaar/data/pipeline/p6_snapshot.py` or `tests/test_corpus.py` — those are built and passing.
>
> Finish by running `make test` and pasting its real output.

**Verify:**
```bash
make test              # expect: 10 passed (not 1 — Step 11's tests already exist here)
ls Makefile pyproject.toml .env.example CLAUDE.md
```

**Watch for:** `make test` must find the venv's pytest. If the Makefile hardcodes `python3`, it
will pick up 3.14 and fail — tell Antigravity to use `python -m pytest` inside the activated venv.

---

### Step 2 · Contracts, tunables, fixture  *(queued)*

Two thirds of this is already built. What is missing:
- `haqdaar/contracts/log_schema.py` — never written
- `fixtures/` — 5 schemes (S1–S6 roles), 3 personas, 9 utterances, ~10 correct-duration audio stubs
- the S6 rejection test (missing Marathi `summary` must fail the build gate)

**Also fix here — a finding from my review, not from the plan:** the top-level `contracts/`
package (`contracts/types.py`, `contracts/tunables.py`, `contracts/__init__.py`) is a star-import
shim onto `haqdaar.contracts`. Architecture §4 puts contracts at `haqdaar/contracts/` and nowhere
else. Every runtime module currently imports the shim (`from contracts import tunables`), which
only resolves because the repo root is on `sys.path` — it will break the moment `pyproject.toml`
from Step 0 makes this an installed package. It also makes the standing review check
*"filter.py, planner.py, terminals.py import only `contracts/`"* ambiguous, right before you
write those three files. Delete the shim and rewrite the ~8 import lines to `haqdaar.contracts`.
I will write this into the work order when Step 0 merges.

### Step 3 · Filter (pure) · Step 4 · Planner (minimax) · Step 5 · Terminals  *(queued)*
Three pure modules, `contracts/` imports only, one test file each. These are the highest-value,
lowest-risk steps for an agent — no I/O, no network, fully specified, test-provable.

### Step 6 · Log, call loop, console sim  *(queued)*
Ends with all three personas reaching `closing_farewell` in `make sim`. **This is the first moment
the system is visibly a product.**

### Steps 7–10 · Scraper → derivation → translate/gates → render  *(queued)*
Needs `GROQ_API_KEY` and `SARVAM_API_KEY`. Caches to `data_cache/` so re-runs are free — and the
throttle is not optional: rev 27 puts this pass and the runtime on the same free-tier limit.

### Step 11 · **already built** — needs re-verification against real data once 7–10 run
### Step 12 · `v1-keypad` — **the demoable milestone.** If time runs short, stop here.

### 6a · Accounts blocking later steps

| Service | Blocks | Env var |
|---|---|---|
| ~~Groq~~ **done 11 Sep** | ~~Steps 8, 9, 14~~ — **unblocked** | `GROQ_API_KEY` ✅ in `.env` |
| Sarvam | Steps 10, 13 | `SARVAM_API_KEY` |
| Twilio + ngrok | Step 1, Step 12 | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `NGROK_DOMAIN` |

`.env` never leaves the laptop. After `git init`, confirm `git status` never lists it.

---

## 7 · Review block — paste into Claude Code after every step

```
Review Step N of haqdaar-v2-brain/docs/build-plan.md.

Read first, in this order:
1. AGENTS.md
2. haqdaar-v2-brain/docs/build-plan.md → Step N
3. haqdaar-v2-brain/docs/architecture.md → the sections the step touches
4. every ticket the step names, in haqdaar-v2-brain/tickets/

Report each as PASS / FAIL / FIXED:

A. Scope — only the listed files changed; nothing from a later step started.
B. Done when — run the command yourself, paste real output.
C. Architecture — audio imports nothing from engine/model/data; filter/planner/terminals import
   only contracts/; runtime never imports data/pipeline/; "twilio" appears only under
   haqdaar/audio/telephony/; contracts/ holds types and numbers only; signatures match T17
   (T17 wins over architecture.md); numbers in tunables.py, not inline.
D. v1 safety — no "eligible/qualify/entitled/you will get/you can get" (or पात्र/हकदार/मिलेगा/मिळेल)
   spoken outside a verbatim source section, except the brand in closing_farewell; no scheme name
   before a non-exact terminal's preamble; no free model text reaches Engine; a scheme failing a
   hard box (state, gender, social_category) is never spoken.
E. Secrets — no key or token in code, tests, fixtures or history.

End with: "safe to merge: yes" or "safe to merge: no" plus the blocking items.
Then update WORK.md §2 and §6.
```

---

## 8 · What I did extra  ← *you write here, I read it every turn*

Append a dated line for anything you did outside a work order: a hand edit, a key created, a
decision made, a step you ran differently, a command that failed. Do not delete old lines.

```
2026-09-10 — created WORK.md (empty)
2026-09-10 — git init -b main + .gitignore; baseline commit (vault rev 27, step 11, 10 tests)
2026-09-10 — .venv built on /opt/homebrew/bin/python3.11; deps installed; pytest -q -> 10 passed
2026-09-10 — FileVault confirmed On
2026-09-11 — YOU: ruled the "never sleep on power" setting N/A. The demo runs off this laptop,
             lid open and plugged in, never unattended. Accepted. Replaced in the runbook by
             `caffeinate -dimsu make run`, which needs no setting changed and no undo.
2026-09-11 — YOU: created the Groq key and handed it over. I wrote it to .env (chmod 600).
             git check-ignore confirms .env is ignored; git status has never listed it.
2026-09-11 — I called the Groq API with it: HTTP 200 on openai/gpt-oss-120b and -20b.
             Measured off live headers: 8,000 TPM / 1,000 RPD / 200K TPD per model.
             Findings in work/2026-09-10.md and in §9 below (items 9-11). Cost: 6 calls.
2026-09-11 — ⚠️ The key was pasted into a chat transcript, so treat it as disclosed. It is a
             free-tier key with no card attached, so the blast radius is a spent quota, not a
             bill — fine to build on all week. Rotate it at console.groq.com after the demo,
             or now if you would rather (it is a 30-second job and only .env changes).
```

---

## 9 · Open findings from my codebase review (2026-09-10)

1. **Build order was skipped** — Step 11 landed before Steps 0–10. Queue in §6 corrects it. No
   code is wasted; Step 11 just cannot prove its real *Done when* until the pipeline exists.
2. **Top-level `contracts/` shim deviates from architecture §4** and breaks under packaging.
   Scheduled for removal in Step 2. Detail in §6.
3. **`haqdaar/contracts/log_schema.py` is missing** — required by Step 2, and Step 6's LOG
   depends on it.
4. **No venv; default `python3` is 3.14 with no pytest** while the plan pins 3.11. Fix in §3b.
5. **Not a git repo** — no rollback under an agent that writes code. Fix in §3a.
6. **`.gitignore` is missing** `.env`, `logs/`, `audio/`, `data_cache/`, `.venv/`. Step 0 covers it;
   the §3a command sets it now so `.env` is never exposed.
7. **`sync_vault.py` glob was widened** for `source-docs/briefs/` and now preserves existing
   frontmatter. Working, 0 dirty. Noted so nobody "fixes" it back.
9. **`gpt-oss` on Groq are reasoning models — Step 14 must send `reasoning_effort: "low"`.**
   Measured 11 Sep. A plain call returns **empty `content`** with the whole budget spent on a hidden
   `reasoning` field; with `reasoning_effort: "medium"` plus `response_format: json_object`, Groq
   returns `json_validate_failed` with an empty `failed_generation` on **both** models. Under
   [[tickets/T18]] that is a model failure, and two drop the call to keypad-only. `low` + JSON mode
   returned valid three-field JSON in ~520–570 ms. **This is a correctness requirement, not tuning —
   and `reasoning_effort` belongs in `tunables.py` beside the model id, not inline.**
10. **The free tier's binding cap is 1,000 requests/day, not TPM.** At ~250 tokens per model call,
   8,000 TPM is ~32 calls/min ≈ 10–16 concurrent callers — **rev 27's "6,000 TPM is one and a half
   phone calls" was arithmetic against a full-history prompt the design no longer sends.** Runtime
   concurrency is not the risk. **Step 8's pipeline is** — one uncached derivation pass over the full
   corpus can spend a large slice of the day's 1,000, and a second run doubles it. Throttle + a
   working `data_cache/` are load-bearing, and re-runs must be free.
11. **D7 has its first data point and it is marginally over budget.** [[tickets/T14]]'s 300–500 ms was
   priced against Gemini Flash-Lite; Groq measured **518 ms (20b)** and **573 ms (120b)**, one cold
   sample each over home wifi. **Not a verdict — Step 14's bake-off reports p50/p95 and D7 stays
   open.** Go in expecting to look at the 1.2 s response clock, and instrument timing from the first
   bake-off run rather than bolting it on after.
12. **Clean:** all 7 hard constraints on Corpus/pool hold, boto3 imports lazily inside the tier-2
   branch, `corpus.py` never imports `pool.py`, and the frozen `Corpus` interface is verbatim —
   11 methods, none added, none renamed.
