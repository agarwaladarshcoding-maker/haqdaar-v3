# WORK.md — what to do next

This file is the handshake between **you**, **Antigravity (Gemini)** and **Claude Code (me)**.
It is not part of the vault. `RULES.md` does not govern it. It holds the running plan:
what to run next, what to paste where, and what already happened.

| Who | Does what |
|---|---|
| **You** | Make the branch. Paste the prompt into Antigravity. Run the check commands. Do the things only a human can do (§3). Write anything off-script into §8. |
| **Antigravity** | Writes code for one step. Nothing else. Never touches this file. |
| **Claude Code (me)** | Reads §8, reruns your checks, reviews the step, updates §1 and §6, writes the next prompt. |

**Your day lives in two files, one per folder.** This file is the plan. Those two are today.

| Folder | Who acts | What is in it |
|---|---|---|
| [`work-adarsh/`](work-adarsh/) | **you** | accounts, the phone call, decisions, merges — hands only |
| [`work-with-tools/`](work-with-tools/) | **Antigravity + me** | the prompt to paste, the check to run, the review block |

| File | What it is |
|---|---|
| [`work-adarsh/2026-09-10.md`](work-adarsh/2026-09-10.md) | **Closed.** Git, venv, FileVault, Groq key. Nothing left. |
| [`work-adarsh/2026-09-11.md`](work-adarsh/2026-09-11.md) | **← today, your hands.** Accounts, and 5 min per merge. |
| [`work-with-tools/2026-09-11.md`](work-with-tools/2026-09-11.md) | **← today, the tool.** Six orders: Steps 0, 2, 3, 4, 5, and 7 in parallel. |
| `*/TEMPLATE.md` | Copy both to `<date>.md` for a new day. |

**Open `work-with-tools/` first** — paste the first prompt so a tool is busy — then work down
`work-adarsh/` while it runs.

---

## 0 · The rules

**R1 · One caller at a time.** v1 serves **one person on one phone**. Build nothing for many
callers — no queues, no worker pools, no concurrency tuning, no load tests. Serving a crowd needs
resources we do not have, and every hour spent there is an hour the call itself does not get.
Map rev 27 already lists "one caller at a time" as an accepted risk, so this matches the vault.
*If a step starts drifting toward concurrency, stop it. Tell me and I will cut it.*

**R2 · Every step gets its own branch.** Always `git checkout -b step-NN` **before** you paste
anything into Antigravity. Never let an agent write on `main`. A bad run is then one
`git checkout .` away from gone.

**R3 · One step in flight.** Do not paste prompt N+1 until step N is reviewed and merged.

**R4 · `.env` never gets committed.** It is in `.gitignore`. Check with `git status` if unsure.

**R5 · Anything you do by hand goes in §8.** A key, a hand edit, a decision, a command that
failed. If it is not in this file or on disk, I do not know it happened.

**R6 · You edit `source-docs/`, then run `python3 sync_vault.py --sync`.** Never hand-edit the
vault. Agents read the vault, so an unsynced edit means they build against old docs.

**R7 · Every terminal starts with:**
```bash
cd /Users/adarshagarwala/Documents/haqdaar-v2 && source .venv/bin/activate
```

> **Path note:** `build-plan.md` and `today.md` were written for a repo with the vault at `brain/`.
> Here it sits at `haqdaar-v2-brain/`. Rev 27 allows both names. **The prompts in §4 already use the
> right path — paste them as they are**, do not copy the ones inside the docs.

---

## 1 · Where we stand — 11 Sep

### Done
- **Git repo** on `main`. Baseline commit holds the vault and all working code.
- **`.venv` on Python 3.11.** `pytest -q` → **10 passed**.
- **FileVault on.** Laptop-sleep setting ruled not needed by you — the laptop stays open and
  plugged in for the demo. `caffeinate -dimsu make run` covers it on the day.
- **Step 0 merged** (11 Sep night). `step-00` → `main`, `--no-ff`, pushed. `make test` → 10 passed.
  Repo now has `Makefile`, `pyproject.toml`, `.env.example`, `CLAUDE.md` and the §4 package tree.
- **Keys in `.env`:** Groq ✅ · Sarvam ✅ · Twilio SID + token ✅ · **ngrok domain still missing.**
  Twilio keys do not prove a voice number was bought — check that before Step 1.
- **Groq key** in `.env` and tested live. **8,000 tokens/min · 1,000 requests/day · 200K tokens/day**
  per model. Steps 8, 9 and 14 are unblocked. Three findings in §9.
- **Vault clean.** 65 files synced, 0 dirty. Map rev 27.
- **All decisions closed.** D1 Groq · D2 D-day 14 Sep · D3 minimax planner · D4/D5/D6 restored ·
  D8 lazy audio pool · D9 map is source of truth. D7 is a number Step 14 measures, not a question.
  **Nothing waits on you to decide.**

### Code that exists and passes
| Path | Lines | Step | State |
|---|---|---|---|
| `haqdaar/contracts/types.py` | 204 | 2 (part) | types + markers there, **`log_schema.py` missing** |
| `haqdaar/contracts/tunables.py` | 50 | 2 (part) | both caps there |
| `haqdaar/audio/pool.py` | 232 | 11 | tier 0 pin + mmap/LRU + tier 2 behind a flag |
| `haqdaar/data/corpus.py` | 346 | 11 | load checks the file exists + digest, returns RenderKey |
| `haqdaar/data/pipeline/p6_snapshot.py` | 484 | 11 | writes the five snapshot files |
| `tests/test_corpus.py` | 422 | 11 | **10 passed** — all 7 hard rules covered |

### Code that does not exist yet
`server.py` · `sim.py` · `contracts/log_schema.py` · `engine/` (filter, planner, terminals, call) ·
`model/` · `audio/telephony/twilio.py` · `audio/ear.py` `mouth.py` `turn.py` · `data/log.py` ·
`fixtures/` · `Makefile` · `pyproject.toml` · `.env.example` · `snapshots/` · `data_cache/` · `audio/`

### The one problem to know about
Step 11 got built before Steps 0–10. The code is fine and none of it is wasted, but Step 11 cannot
prove its real "Done when" (`make pipeline` end to end) until the pipeline exists. §6 puts the
order back.

### Still owed by you
**ngrok** (`NGROK_DOMAIN`, blocks Step 1 + Step 12) · a **Twilio voice number** (keys are in,
the number is unverified) · Plivo/Udyam (blocks nothing this week). Sarvam and Twilio keys are done.
Details in §3a.

---

## 2 · What to do next — in this order

**11 Sep is a tool-heavy day** — you said Antigravity is doing the work. So **Step 1 is pulled
out of today**: it needs a Twilio account, an ngrok tunnel and your thumb on a dial pad. Nothing
else waits on it. Today runs **0 → 2 → 3 → 4 → 5**, with **7 in parallel**. Full orders, with every
prompt written out, are in [`work-with-tools/2026-09-11.md`](work-with-tools/2026-09-11.md).

**Step 0 is done and merged.** The next thing to paste is **Step 2**.

| # | Do this | Where |
|---|---|---|
| ~~1~~ | ~~Step 0~~ — **merged 11 Sep night** | tool file, order 1 |
| ~~2~~ | ~~Twilio / Sarvam keys~~ — **in `.env`**; ngrok still missing | §3a |
| ~~3~~ | ~~Review `N = 0` → merge~~ — **done** | §5 |
| **4** | Step 2 → verify → review `N = 2` → merge → `git tag v1-skeleton` | tool file, order 2 |
| **5** | Step 3 (Filter) → merge. **Start Step 7 in a second window now.** | tool file, orders 3 and P |
| **6** | Step 4 (Planner) → merge | tool file, order 4 |
| **7** | Step 5 (Terminals) → merge | tool file, order 5 |
| **8** | **Step 1 and the phone call move to 12 Sep** — the day you have Twilio + 30 free minutes | §3b |

**Merge command, same every time:**
```bash
git checkout main && git merge --no-ff step-NN -m "step NN: <name>"
```

**If the day runs out:** Steps 0, 2 and 3 merged is a good day. Steps 4 and 5 move to 12 Sep and
cost nothing. **Step 1 must not slip past 12 Sep** — Step 12, the demo, is built on it.

---

## 3 · Only you can do this

Antigravity cannot open an account, hold a phone, or make a judgement call. This section is
everything that needs your hands.

### 3a · Keys and accounts

| Service | State | Blocks | Goes in `.env` as |
|---|---|---|---|
| **Groq** | ✅ **done 11 Sep**, tested live | ~~Steps 8, 9, 14~~ | `GROQ_API_KEY` |
| **Twilio** | ❌ **today, ~15 min** — blocks nothing today, blocks 12 Sep | Step 1, Step 12 | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` |
| **ngrok** | ❌ **today, ~5 min** — same | Step 1, Step 12 | `NGROK_DOMAIN` |
| **Sarvam** | ❌ needed by 12 Sep | Steps 10, 13 | `SARVAM_API_KEY` |
| **Plivo** | background, no rush | nothing before the demo | — |

**Twilio (~15 min).** Sign up. You get free trial credit. Buy a **US number with Voice**.
Copy the Account SID and Auth Token from the console home page into `.env`.
*The trial adds a short notice before your greeting. Fine for building.*

**ngrok (~5 min).** Sign up → install → `ngrok config add-authtoken <token>` → copy your free
static domain into `.env` as `NGROK_DOMAIN`.

**Sarvam (~10 min).** Dashboard → API key → `.env`. Note the free credit balance.
*You no longer need the concurrent-stream limit — R1 means one caller, so it does not matter.*

**Plivo (fire and forget).** Udyam certificate (Aadhaar + PAN) → Plivo signup, India region →
upload → submit. Then forget it until after the demo.

**After adding any key:**
```bash
git status --porcelain | grep -i '\.env$' && echo "STOP — .env is exposed" || echo ".env is safe"
```

### 3b · Manual tests — things no test suite can prove

**M1 · The phone call (Step 1). The single most important thing you do this week.**

```bash
# Terminal A
cd /Users/adarshagarwala/Documents/haqdaar-v2 && source .venv/bin/activate
make run

# Terminal B
ngrok http --url=$NGROK_DOMAIN 8000
```

Then: Twilio console → your number → **Voice → A call comes in → Webhook** →
`https://<NGROK_DOMAIN>/answer`, method **HTTP POST** → Save.

Now dial the number from your phone.

| Check | What you should see or hear | Result |
|---|---|---|
| Trial notice, then a tone | a 1-second beep | |
| Terminal A prints `mark tone_end` | | |
| Press **1** → Terminal A prints `dtmf 1` | | |
| Press **9** → the call ends | | |
| Seconds from dial to tone | count it out loud | |

**Ratify on this call:** `keepCallAlive="false"`. If calls drop at connect, flip it to `true` and
add `streamTimeout="600"`. **Put whichever one you land on in the commit message.**

**Skip the three-phones test.** T19 asked for it. **R1 cancels it** — v1 serves one caller, so the
number would change nothing we build. In the results table write **"ruled out of scope (R1)"**,
not "not measured".

**M2 · The console call (after Step 6).** `make sim`, then play all three personas by hand.
All three must reach `closing_farewell`. This is the first moment the thing is visibly a product.

**M3 · Listen to the audio (after Step 13).** Automated tests prove a file plays. Only your ears
prove it sounds like a person and says the right words in Marathi and Hindi.

**M4 · The demo dry run (13 Sep).** Full call, phone in hand, start to finish, timed. Run
`caffeinate -dimsu make run` so the laptop cannot sleep mid-call.

### 3c · Judgement calls you owe, with dates

| By when | Call to make |
|---|---|
| **13 Sep** | Pay Twilio ~$20 to remove the trial notice before the demo, or live with it? |
| **After Step 1** | `keepCallAlive` — `false` unless the call drops at connect (see M1) |
| **After Step 14** | If the model is slower than 500 ms, the 1.2 s response clock moves — not the provider (§9 item 11) |

---

## 4 · Prompts for Antigravity

**Before every one of these:** `git checkout -b step-NN` (**R2**). Paste the block between the
lines exactly as written.

### ▶ NEXT — Step 0 · Repo and rules

```
git checkout -b step-00
```

> Implement **Step 0** of `haqdaar-v2-brain/docs/build-plan.md`. Follow `AGENTS.md`.
> Read `haqdaar-v2-brain/docs/architecture.md` §4 before writing code.
> Work only on branch `step-00`. Do nothing outside this step.
>
> Three local changes to the step text, all already agreed — apply them:
> 1. The vault is already vendored at `haqdaar-v2-brain/`, not `brain/`. **Do not move it, do not
>    copy it, do not create `brain/`.** Map rev 27 permits either name.
> 2. `AGENTS.md` already exists at the repo root and is correct. **Do not rewrite it.** Add
>    `CLAUDE.md` that imports it, as the step says.
> 3. A git repo and a `.gitignore` already exist and are correct — **add lines to `.gitignore`,
>    never replace it.** A real `.env` also exists at the repo root with a live API key in it:
>    **do not read it, do not print it, do not copy it, do not overwrite it.** `.env.example` is a
>    separate new file and must hold **only empty placeholders**:
>    `GROQ_API_KEY=` · `SARVAM_API_KEY=` · `TWILIO_ACCOUNT_SID=` · `TWILIO_AUTH_TOKEN=` ·
>    `NGROK_DOMAIN=`
>
> Everything else in Step 0 stands: `pyproject.toml` (Python 3.11), the `Makefile` with targets
> `run · sim · test · demo-fixture · pipeline · smoke`, `.env.example`, the `.gitignore` lines, and
> the empty package tree from architecture §4 — including `audio/` as a **flat top-level pool**,
> never nested under `snapshots/`.
>
> The Makefile must call `python -m pytest`, not `python3`. The system `python3` is 3.14 and has no
> pytest; the project venv is 3.11.
>
> **This project serves one phone caller at a time.** Add no queueing, no worker pool, no
> concurrency settings anywhere.
>
> Do not touch `haqdaar/contracts/`, `haqdaar/audio/pool.py`, `haqdaar/data/corpus.py`,
> `haqdaar/data/pipeline/p6_snapshot.py` or `tests/test_corpus.py` — those are built and passing.
>
> Finish by running `make test` and pasting its real output.

**Then run these yourself:**
```bash
cd /Users/adarshagarwala/Documents/haqdaar-v2 && source .venv/bin/activate
make test                                  # expect: 10 passed (not 1 — Step 11's tests exist here)
ls Makefile pyproject.toml .env.example CLAUDE.md
grep -c gsk_ .env.example                  # expect: 0 — no real key in the example file
git status --porcelain | grep -i '\.env$' && echo "STOP" || echo ".env safe"
```

**Watch for:** if `make test` says "no module named pytest", the Makefile hardcoded `python3`.
Tell Antigravity to use `python -m pytest`.

---

### Step 1 · Telephony smoke call  *(needs Twilio + ngrok first)*

```
git checkout -b step-01
```

> Implement **Step 1** of `haqdaar-v2-brain/docs/build-plan.md`. Follow `AGENTS.md`.
> Read `haqdaar-v2-brain/docs/architecture.md` and tickets `T19`, `T14`, `T05` in
> `haqdaar-v2-brain/tickets/` before writing code.
> Work only on branch `step-01`. Do nothing outside this step.
>
> Files: `server.py` (`/health`, `/answer` returning the Stream XML as `text/xml`, `/stream`
> accepting the WebSocket) · `haqdaar/audio/telephony/twilio.py` (parse `connected`, `start`,
> `media`, `dtmf`, `mark`, `stop`; build outbound `media`, `mark`, `clear`) · `tools/tone.py`.
>
> Behaviour: on `start`, send a 1-second 440 Hz tone as one `media` message, then a `mark` named
> `tone_end`. Print every inbound mark and digit. Digit `9` closes the socket.
>
> Hard rules:
> - Outbound media carries **no WAV header**.
> - The stream URL takes **no query string**.
> - The word "twilio" may appear **only** under `haqdaar/audio/telephony/`.
> - Use `keepCallAlive="false"`.
> - **One caller at a time.** No session registry, no queue, no concurrency handling.
> - Load keys with `python-dotenv` only. Never print or log a secret.
>
> Finish by running `pytest tests/test_twilio_codec.py` and pasting its real output. The live dial
> test is done by a human, not by you.

**Then:** run `pytest -q`, then do **manual test M1** in §3b. Record the results there.

---

### Step 2 · Contracts, tunables, fixture  →  tag `v1-skeleton`

```
git checkout -b step-02
```

> Implement **Step 2** of `haqdaar-v2-brain/docs/build-plan.md`. Follow `AGENTS.md`.
> Read `haqdaar-v2-brain/docs/interfaces.md` in full and tickets `T17`, `T16`, `T10`, `T06` in
> `haqdaar-v2-brain/tickets/` before writing code.
> Work only on branch `step-02`. Do nothing outside this step.
>
> Two thirds of this step already exists. `haqdaar/contracts/types.py` and
> `haqdaar/contracts/tunables.py` are built and correct — **read them, do not rewrite them.**
> Add only what is missing.
>
> **1 · Delete the shim.** There is a second `contracts/` package at the repo root
> (`contracts/types.py`, `contracts/tunables.py`, `contracts/__init__.py`) that only star-imports
> `haqdaar.contracts`. Architecture §4 puts contracts at `haqdaar/contracts/` and nowhere else.
> **Delete the whole top-level `contracts/` folder** and rewrite every import that used it
> (about 8 lines, all `from contracts import ...`) to `from haqdaar.contracts import ...`.
> It only works today because the repo root is on `sys.path`; `pyproject.toml` from Step 0 breaks it.
>
> **2 · Write `haqdaar/contracts/log_schema.py`** — the schema `T16` names. Step 6's LOG needs it.
>
> **3 · Build `fixtures/`** exactly as `T17` §4 describes: 5 schemes with the S1–S6 roles, 3
> personas, 9 utterances (one per persona per language), and about 10 audio stubs — correct-length
> silence, named by render key — so the turn clock can be tested before a phone line exists.
> **S6 is missing its Marathi `summary` and the build gate must reject it.** Write that as a test.
>
> Hard rules:
> - **No logic in `contracts/`** — types and numbers only.
> - Numbers live in `tunables.py`, never inline.
> - Signatures follow `interfaces.md`, and **if `interfaces.md` and `T17` disagree, `T17` wins**.
> - The fixture and `T08`'s offline test base are **the same artifact — do not build two.**
>
> Finish by running `make test` and pasting its real output. Every fixture record must load into
> its record type with no validation error, and the S6 row must be rejected.

**Then:**
```bash
make test
python -c "import contracts" 2>&1 | grep -q "No module" && echo "shim gone — good" || echo "shim still there"
```
On a passing review:
```bash
git checkout main && git merge --no-ff step-02 -m "step 02: contracts, tunables, fixture"
git tag v1-skeleton
```

---

## 5 · Review block — paste into Claude Code after every step

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
F. One caller (R1) — no queue, worker pool, session registry or concurrency setting was added.

End with: "safe to merge: yes" or "safe to merge: no" plus the blocking items.
Then update WORK.md §1 and §6.
```

---

## 6 · The rest of the queue

Order: **0 → 1 → 2 → 3 → 4 → 5 → 6**, then the pipeline steps. This is the shortest path to a
full keypad call in the simulator, which is `v1-keypad` — a demoable product on its own.

| Step | What | State |
|---|---|---|
| 0 | Repo skeleton, Makefile, pyproject | **next** |
| 1 | Telephony smoke call | **moved to 12 Sep** — needs Twilio + ngrok + your hands |
| 2 | Contracts, log schema, fixture → tag `v1-skeleton` | queued |
| 3 | Filter (pure) | **dispatched 11 Sep** |
| 4 | Planner (minimax) | **dispatched 11 Sep** |
| 5 | Terminals | **dispatched 11 Sep** |
| 6 | Log, call loop, console sim | **first moment it looks like a product** |
| 7–10 | Scraper → derivation → translate/gates → render | needs Groq ✅ + Sarvam |
| 11 | Audio pool + corpus | **already built**, recheck against real data after 7–10 |
| 12 | `v1-keypad` | **the demo milestone. If time runs short, stop here.** |

**Steps 3, 4 and 5 are the best agent work in the whole plan** — pure functions, no network,
no I/O, fully specified, provable by tests. If Antigravity is idle, that is where to point it.

**Step 7 (scraper) needs no keys and does not depend on Steps 3–6.** It can run on `step-07` in
parallel while you review something else.

---

## 7 · Commands

```bash
cd /Users/adarshagarwala/Documents/haqdaar-v2 && source .venv/bin/activate

pytest -q                             # tests
make test                             # same, once Step 0 lands
python3 sync_vault.py --status        # vault check — expect 0 dirty
python3 sync_vault.py --sync          # after ANY edit to source-docs/
python3 sync_vault.py --watch         # auto-sync while you write docs

git checkout -b step-NN               # ALWAYS before pasting a prompt (R2)
git checkout .                        # undo everything an agent just did
git checkout main && git merge --no-ff step-NN -m "step NN: <name>"

caffeinate -dimsu make run            # demo day — laptop cannot sleep while this runs
```

---

## 8 · What I did extra  ← *you write here, I read it every turn*

Add a dated line for anything outside a prompt: a hand edit, a key, a decision, a command that
failed. Do not delete old lines.

```
2026-09-10 — created WORK.md (empty)
2026-09-10 — git init -b main + .gitignore; baseline commit (vault rev 27, step 11, 10 tests)
2026-09-10 — .venv built on /opt/homebrew/bin/python3.11; deps installed; pytest -q -> 10 passed
2026-09-10 — FileVault confirmed On
2026-09-11 — YOU: ruled the "never sleep on power" setting not needed. The laptop stays open and
             plugged in for the demo, never unattended. Accepted. Replaced in the runbook by
             `caffeinate -dimsu make run`, which changes no setting and needs no undo.
2026-09-11 — YOU: created the Groq key and handed it over. I wrote it to .env (chmod 600).
             git check-ignore confirms .env is ignored; git status has never listed it.
2026-09-11 — I called the Groq API with it: HTTP 200 on openai/gpt-oss-120b and -20b.
             Measured off live headers: 8,000 TPM / 1,000 RPD / 200K TPD per model.
             Findings in work-adarsh/2026-09-10.md and §9 items 9-11. Cost: 6 calls.
2026-09-11 — ⚠️ The key was pasted into a chat transcript, so treat it as public. It is a free-tier
             key with no card, so the worst case is a spent quota, not a bill — fine to build on
             all week. Rotate it at console.groq.com after the demo, or now if you prefer. 30
             seconds, and only .env changes.
2026-09-11 — YOU: ruled R1 — one caller at a time, no concurrency work in v1. This cancels T19's
             three-phones measurement. Recorded as a scope ruling, not as a gap. See §0 and §3b.
2026-09-11 — YOU: asked for simpler words in everything I write. This file was rewritten for it.
2026-09-11 — Split work/ into two dated folders: work-adarsh/ (your hands only) and
             work-with-tools/ (prompts, checks, review). Old work/ files moved with git mv,
             nothing lost. Re-cut 11 Sep as a tool-heavy day: Step 1 pulled out to 12 Sep
             because it needs an account and a phone; today runs 0 -> 2 -> 3 -> 4 -> 5 with 7
             in parallel. Prompts for Steps 3, 4, 5 and 7 written out in full.
```

---

## 9 · Open findings

1. **Build order got skipped** — Step 11 landed before Steps 0–10. §6 fixes the order. No code
   wasted; Step 11 just cannot prove its real "Done when" until the pipeline exists.
2. **The top-level `contracts/` shim breaks under packaging.** Architecture §4 puts contracts at
   `haqdaar/contracts/` only. Deleted in Step 2 — it is in the prompt.
3. **`haqdaar/contracts/log_schema.py` is missing.** Step 2 writes it; Step 6's LOG needs it.
4. ~~No venv~~ — **fixed 10 Sep.**
5. ~~Not a git repo~~ — **fixed 10 Sep.**
6. ~~`.gitignore` missing~~ — **fixed 10 Sep.** `.env` has never been exposed.
7. **`sync_vault.py`'s glob was widened** for `source-docs/briefs/` and now keeps existing
   frontmatter. Working, 0 dirty. Noted so nobody "fixes" it back.
8. **Clean:** all 7 hard rules on Corpus and pool hold, boto3 imports lazily inside the tier-2
   branch, `corpus.py` never imports `pool.py`, and the frozen `Corpus` interface is exact —
   11 methods, none added, none renamed.
9. **The Groq `gpt-oss` models think before they answer, and the default returns nothing.**
   Measured 11 Sep. A plain call came back with **empty `content`** — the whole token budget went to
   a hidden `reasoning` field. With `reasoning_effort: "medium"` plus `response_format: json_object`,
   Groq returned a hard `json_validate_failed` error on **both** models. Under T18 that counts as a
   model failure, and two of those drop the call to keypad-only. `reasoning_effort: "low"` plus JSON
   mode returned clean three-field JSON in about 520–570 ms. **Step 14 must send `low`, and
   `reasoning_effort` belongs in `tunables.py` next to the model id, not inline.**
10. **The Groq limit that bites is 1,000 requests per day, not tokens per minute.** At ~250 measured
   tokens per call, 8,000 TPM is far more than one caller will ever use (**R1**), so runtime is not
   at risk. **Step 8's pipeline is.** One uncached pass over the full scheme corpus can spend a big
   slice of the day's 1,000, and a second pass doubles it. **The throttle and a working `data_cache/`
   are load-bearing. Re-runs must be free.**
11. **D7 has its first number and it is a little over budget.** T14 priced the model call at
   300–500 ms against Gemini Flash-Lite. Groq measured **518 ms (20b)** and **573 ms (120b)** — one
   cold sample each, over home wifi. **Not a verdict.** Step 14's 30-utterance bake-off reports p50
   and p95, and D7 stays open until then. Go in expecting to move the 1.2 s response clock, and time
   the bake-off from its first run rather than adding timing later.
