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

## 1 · Where we stand — 12 Sep

*Plain-words version of this whole section, for anyone coming back cold:*
[`work-with-tools/2026-09-12-summary.md`](work-with-tools/2026-09-12-summary.md)

### Done
- **Git repo** on `main`. Baseline commit holds the vault and all working code.
- **`.venv` on Python 3.11.** `pytest -q` → **10 passed**.
- **FileVault on.** Laptop-sleep setting ruled not needed by you — the laptop stays open and
  plugged in for the demo. `caffeinate -dimsu make run` covers it on the day.
- **Step 0 merged** (11 Sep night). `step-00` → `main`, `--no-ff`, pushed. `make test` → 10 passed.
  Repo now has `Makefile`, `pyproject.toml`, `.env.example`, `CLAUDE.md` and the §4 package tree.
- **Keys in `.env`:** Groq ✅ · Sarvam ✅ · Twilio SID + token ✅ · **ngrok domain ✅ (12 Sep)** ·
  **Twilio voice number ✅ (12 Sep).** All verified live, not just present:
  ngrok `attire-divorcee-spousal.ngrok-free.dev` resolves to live ngrok IPs; the Twilio API returns
  **+1 424 799 0057**, voice-capable, on an `active` **Trial** account. **Step 1 is unblocked.**
  ⚠️ But the number's **voice webhook points at `/`, not `/answer`** — Twilio will 404 on every
  call until you change it in the console. One-line fix, in `work-adarsh/2026-09-12.md`.
- **Groq key** in `.env` and tested live. **8,000 tokens/min · 1,000 requests/day · 200K tokens/day**
  per model. Steps 8, 9 and 14 are unblocked. Three findings in §9.
- **Step 2 merged and tagged** (11 Sep night). `step-02` → `main`, `--no-ff`. Root `contracts/`
  shim deleted, `log_schema.py` written, `fixtures/` built, Gate 3 added to `p6_snapshot.py`.
  Three conformance breaks found and fixed in review. `make test` → **19 passed** on merged `main`.
  **`v1-skeleton` tagged on the merge commit.** The tag already existed on the Step 0 commit —
  placed a step early — and was moved. It is local only; nothing was pushed.
- **Vault clean.** 65 files synced, 0 dirty. Map rev 27.
- **All decisions closed.** D1 Groq · D2 D-day 14 Sep · D3 minimax planner · D4/D5/D6 restored ·
  D8 lazy audio pool · D9 map is source of truth. D7 is a number Step 14 measures, not a question.
  **Nothing waits on you to decide.**

### Code that exists and passes
| Path | Lines | Step | State |
|---|---|---|---|
| `haqdaar/contracts/types.py` | 206 | 2 | types + markers + input union; `TurnResult` name added (T17) |
| `haqdaar/contracts/tunables.py` | 50 | 2 | both caps there |
| `haqdaar/contracts/log_schema.py` | 125 | 2 | T16 line schema; struck flag + unratified stops removed |
| `fixtures/` | — | 2 | 5 schemes + bad S6 · 3 personas · 9 utterances · 10 μ-law stubs |
| `tests/test_step2.py` | — | 2 | **9 passed** — shim gone, S6 rejected, fixtures load |
| `haqdaar/audio/pool.py` | 232 | 11 | tier 0 pin + mmap/LRU + tier 2 behind a flag |
| `haqdaar/data/corpus.py` | 346 | 11 | load checks the file exists + digest, returns RenderKey |
| `haqdaar/data/pipeline/p6_snapshot.py` | 484 | 11 | writes the five snapshot files |
| `tests/test_corpus.py` | 422 | 11 | **10 passed** — all 7 hard rules covered |
| `haqdaar/engine/filter.py` | — | 3 | merged into `main` 12 Sep · `tests/test_filter.py` **10 passed** |
| `haqdaar/engine/planner.py` | 260 | 4 | merged into `main` 12 Sep · `tests/test_planner.py` **14 passed** |
| `haqdaar/engine/terminals.py` | 448 | 5 | merged into `main` 12 Sep (ed69912) · `tests/test_terminals.py` passing |
| `haqdaar/data/pipeline/p1_scrape.py` | 376 | 7 | **merged** 12 Sep (e43207f) · `tests/test_scrape.py` passing · 12 schemes fetched |
| `haqdaar/data/pipeline/schemes.yaml` | 18 | 7 | **merged** 12 Sep · 12 slugs, 4 substituted for dead links, each noted in a comment |

**`pytest -q` on the working tree → 64 passed.**

### Code that does not exist yet
`server.py` · `sim.py` · `engine/call.py` · `model/` ·
`audio/telephony/twilio.py` · `audio/ear.py` `mouth.py` `turn.py` · `data/log.py` ·
`data/pipeline/p2_derive.py`

`data_cache/` now exists — 12 scraped schemes, gitignored, rebuilt from cache in ~30s.

### The one problem to know about
Step 11 got built before Steps 0–10. The code is fine and none of it is wasted, but Step 11 cannot
prove its real "Done when" (`make pipeline` end to end) until the pipeline exists. §6 puts the
order back.

### The SILENCE question — closed
**SILENCE is the seventh LOG `class`. T16 was amended; the code did not move.** `log_schema.py`
said seven, T16 §2 enumerated six, and `architecture.md:147` and `:252` both assumed SILENCE lines
get written. Two sources and the code against one, and T16's own argument for NOISE — a line is
owed or turn accounting is not auditable from the LOG alone — applies to the silence ladder word
for word. So the spec lost. `source-docs/T16-amendment-silence-class.md`, synced to the vault.

**It is a non-cap line:** it carries `silence_n` (the rung: 1, 2, 3) and leaves `turn_n` unchanged.
NOISE counts a turn; SILENCE never did, so T14's cap arithmetic is untouched. Step 6 inherits
seven classes and the `silence_n` field.

**Nothing waits on you. Step 6 is clear to start.**

Two things deliberately left alone, carried as debt:
- `compute_render_key()` lives in `contracts/types.py:189` — live logic in the one directory that
  is supposed to hold none. Pre-existing from the out-of-order Step 11, not from Step 2, so moving
  it is Step 11's recheck (§6 row 11), not Step 2's. Recorded, not fixed.
- `CallCloseRecord.mode` puts keypad-only on the closing line; T18 corrects T16 and says
  keypad-only is a **mode** that writes its own one-off line on entry. Owed before Step 6.

### Still owed by you
**Nothing blocks any step any more.** ngrok and the Twilio voice number both landed 12 Sep and I
verified both against the live APIs. What is left is one console click and one manual test:

1. **Change the Twilio voice webhook to `/answer`** (2 min, console) — otherwise Step 1's call 404s.
2. **Make the phone call (M1)** once Step 1's `server.py` exists.
3. Plivo/Udyam — background, blocks nothing this week.

Details in §3a and `work-adarsh/2026-09-12.md`.

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
| **Twilio** | ✅ **done 12 Sep**, verified live — +1 424 799 0057, voice ✅, account `active` **Trial** | ~~Step 1, Step 12~~ | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_US_PHONE_NUMBER` |
| **ngrok** | ✅ **done 12 Sep**, DNS resolves — `attire-divorcee-spousal.ngrok-free.dev` | ~~Step 1, Step 12~~ | `NGROK_DOMAIN` |
| **Sarvam** | ✅ **done**, key in `.env` | ~~Steps 10, 13~~ | `SARVAM_API_KEY` |
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
`https://attire-divorcee-spousal.ngrok-free.dev/answer`, method **HTTP POST** → Save.

⚠️ **As of 12 Sep it is set to the bare root `/`, which our server does not answer.** I read that
straight off the Twilio API. Change it to `/answer` before you dial or every call 404s.
`voice_method` is already POST — only the URL is wrong.

Now dial **+1 424 799 0057** from your phone.

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

**Before you paste the merge line, always check the branch actually has commits:**
```bash
git log --oneline main..step-NN     # if this is empty, the merge will merge nothing
```
This has bitten twice — Step 3 on 11 Sep and Step 7 on 12 Sep. Both times the files were
untracked and the branch was empty.

---

## 6 · The rest of the queue

Order: **0 → 1 → 2 → 3 → 4 → 5 → 6**, then the pipeline steps. This is the shortest path to a
full keypad call in the simulator, which is `v1-keypad` — a demoable product on its own.

| Step | What | State |
|---|---|---|
| 0 | Repo skeleton, Makefile, pyproject | **merged** 11 Sep |
| 1 | Telephony smoke call | **unblocked 12 Sep** — Twilio number ✅ + ngrok ✅ verified. Needs `server.py` written, the webhook fixed to `/answer`, and your hands |
| 2 | Contracts, log schema, fixture → tag `v1-skeleton` | **merged + tagged** 11 Sep. `v1-skeleton` on the merge commit, local only |
| 3 | Filter (pure) | **merged** 12 Sep. Review: safe to merge, 0 blockers |
| 4 | Planner (minimax) | **merged** 12 Sep, `--no-ff`. Review: safe to merge, 0 blockers. `pytest -q` → 43 passed on merged `main` |
| 5 | Terminals | **merged** 12 Sep, `--no-ff`, ed69912. Review: safe to merge, 3 fixes applied in review |
| 6 | Log, call loop, console sim | **← next, clear to start.** The single highest-value merge left — first moment it looks like a product |
| 7 | Scraper | **merged** 12 Sep, `--no-ff`, e43207f. Review: safe to merge, 0 blockers. `pytest -q` → 64 passed on merged `main`. 12 schemes in `data_cache/raw/` |
| 8–10 | Derivation → translate/gates → render | needs Groq ✅ + Sarvam ✅. Step 8 is today's second order |
| 11 | Audio pool + corpus | **already built**, recheck against real data after 7–10 |
| 12 | `v1-keypad` | **the demo milestone. If time runs short, stop here.** |

**Steps 3, 4 and 5 are the best agent work in the whole plan** — pure functions, no network,
no I/O, fully specified, provable by tests. If Antigravity is idle, that is where to point it.

**Steps 3–5 now have a fixture to test against.** `fixtures/` is the T17 §4 artifact and, per T17,
is the same artifact as T08's offline test base — do not let an agent build a second one.

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
2026-09-12 — Reviewed Step 3 (filter). Verdict safe to merge, no blockers. Ran it myself:
             pytest tests/test_filter.py -> 10 passed; pytest -q -> 29 passed; py_compile clean;
             sync --status -> 0 dirty. Checks that returned nothing, as they should: `~` (no NOT
             masks) and `[<>]=?|int\(|float\(` (no numbers, no comparisons) in filter.py.
             Imports are only contracts/. T17 signatures exact. No secrets, no concurrency (R1).
2026-09-12 — ⚠️ `step-03` has NO commits — both files are untracked. Merging the branch before
             `git add` merges nothing. The exact commands are in work-adarsh/2026-09-11.md.
2026-09-12 — Step 3 review threw up two carry-forwards; both are written into the Step 4 and
             Step 5 prompts in work-with-tools/2026-09-11.md so they cannot be lost. See §9 12-13.
2026-09-12 — Step 3 is committed and merged after all: `main` sits on `step 03: filter`. The
             earlier "no commits" warning is stale — struck.
2026-09-12 — Reviewed Step 4 (planner). Verdict safe to merge, no blockers. Ran it myself:
             pytest tests/test_planner.py -> 14 passed; pytest -q on merged main -> 43 passed;
             py_compile clean; sync --status -> 0 dirty. Four stops match log_schema strings
             exactly, widen ladder is soft-box only with a skipped rung under test, hard boxes
             never widened, all numbers read from tunables.py. No secrets, no concurrency (R1).
2026-09-12 — Merged `step-04` into `main` with --no-ff (670bead). No tag — `v1-skeleton` stays
             on the Step 2 merge.
2026-09-12 — Reviewed Step 5 (terminals). Safe to merge, 3 fixes applied during review (fail-closed
             naming, OVERFLOW_READ_CAP moved into tunables.py, no fabricated scheme ids). Merged
             --no-ff as ed69912.
2026-09-12 — Reviewed Step 7 (scraper). Verdict safe to merge, 0 blockers, all six checks PASS.
             Ran it myself: `make pipeline-scrape` -> 12 schemes, all cached <1 day, all on
             myscheme.gov.in, all four required blocks non-empty (4 of 12 have empty exclusions,
             which is allowed). `pytest -q` -> 64 passed. py_compile clean. sync --status -> 0
             dirty. No "twilio" anywhere in haqdaar/ or tests/. No runtime import of
             data/pipeline/. data_cache/ ignored and never listed by git status.
2026-09-12 — ⚠️ `step-07` has NO commits — all three files are untracked. Merging the branch
             merges nothing. Same trap as Step 3 on 11 Sep. Commit lines are Order 0 of
             work-with-tools/2026-09-12.md. Adding a `git log --oneline main..step-NN` check to
             the review block so this cannot happen a third time.
2026-09-12 — Wrote work-with-tools/2026-09-12.md (Order 0 commit Step 7, Order 1 Step 6, Order 2
             Step 8) and work-with-tools/2026-09-12-summary.md — a plain-words account of what is
             built, what each file does, what the thing can do today, and when it actually works.
2026-09-12 — YOU: added NGROK_DOMAIN and TWILIO_US_PHONE_NUMBER to .env. I verified both live,
             not just present: dig resolves attire-divorcee-spousal.ngrok-free.dev to five ngrok
             IPs, and the Twilio API returns +1 424 799 0057, voice-capable, account `active`,
             type Trial. Step 1 and Step 12 are unblocked. §1, §3a and §6 updated.
2026-09-12 — ⚠️ The Twilio number's voice webhook is
             `https://attire-divorcee-spousal.ngrok-free.dev/` — the bare ROOT, not `/answer`.
             voice_method is POST, which is right; only the path is wrong. Every call will 404
             until you change it in the console. Written up as the one blocker in
             work-adarsh/2026-09-12.md. Read off the live Twilio API, not guessed.
2026-09-12 — I hand-fixed .env line 7. It read `TWILIO_US_PHONE_NUMBER = +1424...` with spaces
             around the `=`. python-dotenv tolerates that; a shell does not — `set -a; . ./.env`
             printed `command not found: TWILIO_US_PHONE_NUMBER` and left the variable empty. The
             §3b Step 1 recipe sources .env in a shell, so it would have bitten mid-call. Spaces
             stripped from every line, re-sourced, both variables read correctly. chmod 600 kept,
             git status still does not list .env. Added TWILIO_US_PHONE_NUMBER to .env.example.
2026-09-12 — Committed and merged Step 7. git add the three untracked files + Makefile +
             pyproject + .env.example -> e12b246 on step-07, merged --no-ff into main as e43207f.
             The "step-07 has no commits" warning above is now stale — struck. `pytest -q` on
             merged main -> 64 passed, py_compile clean, sync --status -> 66 files 0 dirty.
2026-09-12 — Wrote work-adarsh/2026-09-12.md. It was missing — 12 Sep had a tool file but no
             hands file, so the webhook problem had nowhere to live.
2026-09-12 — Reviewed Step 6 (log, call loop, sim). Verdict **safe to merge: NO**. One blocker:
             the widening ladder is not implemented, so P2 never reaches a nearest-two and the
             Done-when is not met. See §9 18. Ran it myself: pytest -q -> 77 passed; py_compile
             clean; `make sim` runs to closing_farewell and writes a good log. The three review-
             focus items all pass (Log.write never raises, no telephony import, turn 0 and
             SILENCE accounting correct). No secrets, no concurrency (R1 holds), no "twilio"
             outside audio/telephony/, nothing from Step 8 started.
2026-09-12 — ⚠️ The P2 test is a **false green**. `test_persona_p2_dead_end_ladder_end_to_end`
             passes while producing the exact-match terminal. I re-ran its own inputs and
             printed them: it plays `results_exact_preamble` + `name:S4` and closes with
             `stop: survivors_le_4, ladder_rung: 0`. It passes only because it asserts
             `"ladder_rung" in close_line`, which is true at 0. Details in §9 18.
2026-09-12 — ⚠️ `step-06` has NO commits — all four files are untracked. Third time
             (Step 3, Step 7, now Step 6). The `git log --oneline main..step-NN` check earns
             its place in the review block.
2026-09-12 — `make demo-fixture` is still the Step-6 placeholder echo. The Step 6 file list and
             T17 §4 both name it, so Step 6 is not done until it runs.
2026-09-12 — **T17 §2 needs an amendment.** It freezes `Log.close(reason: str)`, but T16's
             `CallCloseRecord` and Step 6's Done-when both need `ladder_rung` and `mode` on the
             closing line. Step 6 widened it to `close(reason, ladder_rung, mode)`. The code is
             right and the ticket is stale — amend the ticket, do not narrow the code.
2026-09-12 — Fixed the Step 6 blocker. It was not "the ladder is missing". The ladder was
             there; four things in front of it made it dead. (1) call.py forced
             `state = UNKNOWN` unconditionally, claiming cardinality > 9 — fixtures have 2
             states, so this was simply wrong. (2) Every fixture scheme names a real state,
             so with state UNKNOWN nothing was speakable and every ladder rung returned 0.
             (3) call.py hid that by passing `pre_vetted=True`, telling Terminals the Engine
             had already run the truth lock when it had not, and then handed
             `Terminals.sequence` the empty survivor list, which threw away whatever the
             ladder did find. (4) The real one: the Planner applies T10's speaking-rule
             exception only on the "<=4 survivors" branch, so on zero survivors it stopped
             asking, left `gender` and `social_category` unasked, and the ladder bought
             candidates the truth lock then refused to name. All four fixed.
2026-09-12 — P2 now genuinely runs the ladder. `make demo-fixture` prints
             `terminal_widened_preamble -> drop_income_band -> results_widened_lead -> name:S3`
             and closes `{"stop": "zero_survivors", "ladder_rung": 1, "mode": "keypad_only"}`.
             The false-green P2 test is replaced: it now asserts the preamble, the exact
             `drop_*` list, T18's ordering, at least one named scheme, and `ladder_rung >= 1`.
2026-09-12 — ⚠️ **The fix moved Step 4.** The speaking-rule exception now applies on the
             zero-survivor branch too. Four `tests/test_planner.py` tests asserted `Widen`
             from vectors with hard boxes unasked; they now answer the hard boxes and assert
             the same rungs, plus one new test pinning the new behaviour. T10 / T15 need the
             amendment. See §9 21.
2026-09-12 — ⚠️ **Delivery shape 4 (NEAREST) cannot ever fire.** Architecture §8 routes
             "ladder exhausted -> any scheme with a soft-only miss-set -> NEAREST", but
             `WIDENING_ORDER` covers all four soft boxes, so "exhausted" means every soft box
             was dropped and still nothing survived — which is the same condition as "no
             scheme has a soft-only miss-set". The two branches are the same test. Proven by
             enumerating all 1351 keypad-reachable fixture vectors: direct_match, overflow,
             widened_match and empty all occur; nearest never does. So Step 6's Done-when
             ("P2 reaches a labelled nearest-two") and T17 §4 are unsatisfiable as written.
             This is a decision, not a bug. See §9 22.
2026-09-12 — Also fixed in the same pass: `Speech` was a bare `pass` that spun the loop
             forever (now spends a cap turn and logs UNCLEAR); the read-back menu read a
             digit and discarded it (now plays 1-4 behind `section_source_frame`, 9 advances
             with `next_scheme_intro` / `no_more_schemes`, each section once per scheme);
             `anything_else == 1` was a dead write (now a real Door B, one per call, on the
             same budget); the call-open `lang_source` said "default" forever (the Engine now
             writes a `LangSwitchRecord` at turn 0 with what the caller actually pressed);
             a box dropped for cardinality now writes a log line instead of vanishing.
2026-09-12 — `make demo-fixture` implemented: three personas against the four fakes, each
             printing its LOG. `sim.py` gained `--persona p1|p2|p3`, `--canned`, `--call-id`
             and `--logs-dir`; the old non-interactive fallback answered "1" forever.
2026-09-12 — Gates after the fixes: `pytest -q` -> **80 passed**; `py_compile` clean on
             call.py, planner.py, sim.py, log.py, sync_vault.py; `sync_vault.py --status` ->
             66 files, 0 dirty; `make sim` and `make demo-fixture` both run to
             `closing_farewell`. Still nothing committed on `step-06`.
2026-09-13 — YOU: chose option (a) on §9 22 — take `category` out of the widening ladder.
             Done. `WIDENING_ORDER` is now `income_band -> age -> occupation`. Shape ④
             NEAREST is reachable: over the fixture corpus, 396 vectors now land on a
             nearest terminal and 36 of them name two schemes. Before the change: zero.
2026-09-13 — ⚠️ The change alone was not enough, and the reason is worth knowing. The
             enumeration said nearest was reachable but **no digit sequence through the
             Engine could get there.** `category` is box 0, the **opener** (Door A,
             architecture §6), and nothing was asking it — the Planner only picks a box
             when it wins on minimax, and in a 5-scheme corpus `income_band` always wins
             first, so the caller was never asked what they had phoned about. Door A is
             now asked before any planning and stays in front of the caller until it is
             answered or struck out. Door B re-opens it.
2026-09-13 — The speaking-rule exception is now one helper used on all three paths — the
             `<=4` stop, the widened set, and the **nearest** candidates. Without the
             nearest arm P2 named one nationwide scheme where two better nearest existed.
             T10 D3 amended for it. See §9 21.
2026-09-13 — **Step 6's Done-when is now met.** From `make demo-fixture`, persona p2:
             `opener_prompt -> keypad_state -> keypad_gender -> keypad_social_category ->
             terminal_nearest_preamble -> name:S1 -> name:S2 -> anything_else ->
             closing_farewell`, closing
             `{"stop": "zero_survivors", "ladder_rung": 3, "mode": "keypad_only"}`.
             Two nearest, labelled as non-matches, preamble first, no `section_menu`,
             auto-advance. That is T18 §2 and T17 §4 as written.
2026-09-13 — Four sim personas now: p1 direct match, p2 nearest-two, p3 Door B second
             subject, `widened` for shape ③. Shape ③ is only reachable in this corpus when
             Door A is struck out to UNKNOWN — with the opener answered, five schemes
             narrow to <=4 or 0 before any soft box is asked. Fixture-size artefact, not an
             engine limit; kept as its own test so the shape stays covered.
2026-09-13 — Brain amended in `source-docs/` and synced (7 files updated, 0 dirty):
             T10 D6 (ladder) and T10 D3 (speaking rule), ARCHITECTURE §8 flowchart,
             BUILD-PLAN Step 4, PRD, T18, DECISION-LOG, briefs/engine.
2026-09-13 — Gates: `pytest -q` -> **83 passed** · py_compile clean · `sync_vault.py
             --status` -> 66 files, 0 dirty · `make sim` and `make demo-fixture` both reach
             `closing_farewell` on every persona.
2026-09-13 — **T17 §2 amended** and synced: `Log.close(reason, ladder_rung=None, mode=None)`.
             Both new args are optional, so the frozen `Log.close(reason)` still works.
             The last open item from the Step 6 review is closed.
2026-09-13 — ⚠️ **Found and fixed a Step 3 bug that would have hit Step 8 hard.**
             `Filter.speakable` treated a hard box with an *empty* closed set as "not ANY"
             and refused the scheme. An empty set means every scheme is ANY on that box.
             So in any corpus where, say, every scheme is nationwide (`state: ANY`), **no
             scheme could ever be spoken** — every call would end on `terminal_empty`. The
             real myScheme corpus is mostly central schemes, so this was likely to be the
             first thing Step 8's data ran into. One-line fix plus a regression test.
2026-09-13 — ⚠️ The same bug hid a **false-green test**: the wide-state test asserted
             `"WNAT" in named or not named`, which passes when nothing is named. Tightened.
             All three new or tightened tests fail on the old filter and pass on the fixed one.
2026-09-13 — Shape ③ (widened match) now proven with Door A **answered**, not only struck
             out — on a purpose-built 13-scheme corpus, since `fixtures/` is too small to
             need a second soft question. Test: `test_widened_match_with_door_a_answered`.
2026-09-13 — Gates: `pytest -q` -> **85 passed** · py_compile clean · sync --status 0 dirty ·
             `make demo-fixture` reaches `closing_farewell` on all four personas.
2026-09-13 — Step 8 prompt edited in work-with-tools/2026-09-12.md: branch from `main` (the
             old bare `git checkout -b step-08` would have based it on step-06, which is
             checked out), record `category` cardinality (Door A needs <=9 to be asked), and
             note that `ANY` on an entire hard box is valid. **Step 8: green**, once PR #1
             is merged.
2026-09-12 — Reviewed Step 8 (derivation), night of 12 Sep. Verdict: safe to merge NO, 2 blockers.
             Ran it myself: `make pipeline-extract` -> 12 schemes, 36/36 cache hits, 0 calls.
             Every non-ANY facet quote is found word for word in the eligibility text (checked
             again with a plain `quote in text`). `pytest -q` -> 74 passed (70 + 4 new).
             py_compile clean. sync --status -> 0 dirty. No twilio, no secrets, no pool (R1).
2026-09-12 — Step 8 review fixed 7 small things, no model call spent: `level` "Central" ->
             "CENTRAL" (contract); "ALL" removed from the closed sets (ANY is the only sentinel);
             fake "<slug> yojana / scheme / portal" alias padding removed (a thin scheme now fails
             loudly, as T07 says); the >=3-schemes alias rule got its own dial
             ALIAS_CATEGORY_WORD_MIN instead of borrowing ALIAS_FLOOR; retries, timeouts, waits
             and the 300-char slice moved to tunables.py; the ~35-word cap is checked in code;
             the quote invariant now runs before any file is written. Not committed.
2026-09-12 — ⚠️ `step-08` has NO commits — all Step 8 work is untracked or unstaged. Third time.
             Blocker list and commit lines are in work-adarsh/2026-09-12.md.
2026-09-13 — YOU committed Step 8 wip on step-08 (4f4a932). The "no commits" line above is stale.
2026-09-13 — Merged step-06 into main as 92dfe77. WORK.md and the 12 Sep tool file conflicted
             (both sides were notes); kept both, renumbered the Step 8 findings to §9 23-25.
             `pytest -q` on main -> 85 passed; demo-fixture reaches closing_farewell.
2026-09-13 — Fixed both Step 8 blockers on step-08 (main merged in first). Alias prompt no
             longer shows another scheme's name and says "this scheme only". `age` and
             `income_band` are now {"min", "max"}; code checks every number is written in the
             quote, else ANY + a gate_note. Moved old facets/aliases cache aside, re-ran: 24
             Groq calls, 0 failures, ~3 min. Second run 36/36 hits, 0 calls. Read aliases by
             eye: no scheme carries another scheme's name. APY age 18-40, NAPS 14-35, PMEGP
             18+. `pytest -q` -> 97 passed · py_compile clean · sync --status 0 dirty.
             Committed 9ae9af2. Needs one re-review, then merge.
2026-09-13 — Re-reviewed Step 8. Both blockers fixed, checked in the data: no scheme carries
             another scheme's name; APY age 18-40, NAPS 14-35, PMEGP 18+, rest ANY. Ran it myself:
             `pytest -q` -> 97 passed · py_compile clean · sync --status 0 dirty ·
             `make pipeline-extract` -> 36/36 hits, 0 calls. `git log main..step-08` shows 4
             commits, tree clean. Verdict **safe to merge: yes**. Two new data faults, not in the
             fix: AB-PMJAY occupation = street_vendor (§9 26), category ANY on 7/12 (§9 27). Both
             are cheap and must land before the Step 9 snapshot is built.
2026-09-13 — Fixed §9 26 and 27 on step-08. Category quote may now sit in eligibility OR benefits
             (still verbatim, checked in code, invariant too). Prompt rule: several groups listed
             -> occupation ANY. Re-ran facets for all 12 (12 calls, old cache in scratchpad).
             Result: category set on 12/12 (was 5/12); AB-PMJAY = health, occupation ANY.
             Side effect: NAPS lost `apprentice`, SMAM lost `farmer` (SMAM lists SHGs, FPOs,
             entrepreneurs too). Both now ANY = wider, never hides a scheme; occupation vocab is
             now farmer + street_vendor. Accepted, not re-run. Second run 36/36 hits, 0 calls.
             `pytest -q` -> 98 passed · py_compile clean · sync --status 0 dirty.
2026-09-13 — YOU: set the Twilio voice webhook. I checked it on the live Twilio API:
             +1 424 799 0057 -> `https://attire-divorcee-spousal.ngrok-free.dev/answer`, POST.
             The §1 warning is closed. Step 1 still needs `server.py` + `telephony/twilio.py`.
2026-09-13 — Wrote the 13 Sep day files: work-with-tools/2026-09-13.md (Step 1 + Step 9, parallel)
             and work-adarsh/2026-09-13.md (the M1 call). New standing file PROJECT-UPDATE.md —
             plain-words state, updated every chat. Prompt fixes vs §4: server lives at
             `haqdaar/server.py` (Makefile runs `haqdaar.server:app`); Step 9 gate 3 prints PENDING
             for the rendered half until Step 10, or no scheme could pass.
2026-09-13 — Step 1 implemented: `haqdaar/server.py` (/health, /answer, /stream),
             `haqdaar/audio/telephony/twilio.py` (parse 6 inbound, build 3 outbound, twilio isolation preserved),
             `tools/tone.py` (8 kHz μ-law pure python tone generator), `haqdaar/contracts/tunables.py`
             telephony tunables added. `tests/test_twilio_codec.py` 10 tests passed; `pytest -q` -> 108 passed.
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
12. **`survivors()` does not obey the speaking rule — only `speakable()` does.** Found while
   reviewing Step 3. If a caller names a state no scheme carries, the filter throws that answer
   away (correct — `T09 §6`, an out-of-set code is treated as `UNKNOWN` and appends no mask). But
   that leaves **all five fixture schemes as survivors**, and `speakable()` says **none** of them
   may be read out. So a terminal that reads `survivors()` and speaks the names would name schemes
   from the wrong state. **Step 5's terminals must run every survivor through `speakable()` before
   naming it.** Build-plan Step 4's speaking-rule exception does not cover this, because the box was
   asked, not unasked. Already written into the Step 5 prompt.
13. **An out-of-set answer is never re-asked.** Same root. The rejected value still sits in the box
   vector as plain text, so the Planner sees the box as *answered* and skips it forever. T09 §6 says
   it must be "handed to the ladder as a re-ask". **Step 4 must read a box as `UNKNOWN` when its
   value is not in `corpus.values(box)`** — or the turn that writes the vector must. Pick one and
   test it. Already written into the Step 4 prompt.
14. **Clean, Step 3:** no NOT masks, no numbers, no comparisons, imports only `contracts/`,
   `NEAREST_CAP` read from `tunables.py`, T17 signatures exact, nothing from a later step started,
   no secrets anywhere, and no queue, pool, registry or concurrency setting (**R1** holds).
15. **`architecture.md` §4 contradicts itself about what `planner.py` may import.** §4 says
   `filter.py`, `planner.py` and `terminals.py` import *"nothing but `contracts/`"*, but §7.3's
   ratification of minimax says it is *"~15 lines over a `Filter` that already exists"* — which
   only works if the Planner calls `Filter`. **T17 §2 is the binding seam and it is narrower:**
   *"`Planner` and `Filter` take no Audio, no Model and no Log."* `planner.py` imports
   `engine/filter.py` and nothing else outside `contracts/`, which satisfies T17. Read §4 as
   *nothing outside the pure core*. Recorded so nobody "fixes" the import away and duplicates
   `Filter`, and so Step 5's terminals get the same reading.
16. **`Widen(box)` does not say whether the box is *the* drop or *the last* drop.** The ladder is
   monotone (T18 §1), so at rung 2 the dropped set is `{income_band, age}` but the Planner can
   only return `Widen("age")`. The current code returns the last rung reached. If Step 6's loop
   drops only the named box it still converges — the next call returns `Widen("income_band")` —
   but it costs a turn against the 8-turn cap. **Step 6 must apply `Widen(box)` cumulatively over
   the fixed order, not as a single box.** Decide it in the Step 6 prompt; no code change owed now.
17. **Clean, Step 4:** four stop strings match `log_schema.py` exactly, hard boxes are never
   widened, `STOP_SURVIVORS` / `MAX_TURNS` / `MAX_QUESTIONS` / `KEYPAD_CARDINALITY_MAX` all read
   from `tunables.py` with nothing inline, the speaking-rule exception is under test, out-of-set
   answers re-ask (closes §9 13 for the Planner side), nothing from Step 5 started, no secrets,
   and no queue, pool, registry or concurrency setting (**R1** holds).

18. ~~**BLOCKER, Step 6: the widening ladder was never built, and the test that should have caught
   it is a false green.** `haqdaar/engine/call.py:137-139` handles `Widen(box)` by setting
   `stop_reason = zero_survivors` and **breaking out of the loop**. The box vector is never
   relaxed, no rung is walked, and `ladder_rung` is back-filled afterwards as a proxy (the count
   of answered soft boxes) instead of the rung actually reached. This is the decision §9 16 told
   Step 6 to make — apply `Widen` cumulatively over `WIDENING_ORDER` — and it was not made at all.
   Build-plan Step 6's Done-when says *"P2 reaches a labelled nearest-two through the full
   ladder."* It does not. I ran P2's own inputs and printed them: it plays
   `state_unknown_disclaimer -> results_exact_preamble -> name:S4 -> ... -> closing_farewell` and
   closes `{"stop": "survivors_le_4", "ladder_rung": 0}` — the **exact-match** terminal, byte for
   byte what P1 does, and only 2 of its 8 canned digits get consumed. The test passes because it
   asserts `"ladder_rung" in close_line`, true even at 0. **Two fixes, not one:** build the
   ladder, and make the P2 test assert `stop == zero_survivors`, `ladder_rung >= 1`,
   `TERMINAL_NEAREST_PREAMBLE` in what was played, and exactly two names. A test that cannot fail
   is worse than no test — it spent a review pass looking green.~~
   **Fixed 12 Sep, and the diagnosis above was half wrong.** The ladder existed — `classify_shape`
   walks it. Four things in front of it made it dead; see §9 21 and 22, and the 12 Sep lines in
   §8. P2 now plays `terminal_widened_preamble -> drop_income_band -> results_widened_lead ->
   name:S3` and closes `{"stop": "zero_survivors", "ladder_rung": 1}`. The false-green test is
   replaced. The one part of this finding that survives is the **nearest**-two requirement — see
   §9 22, that one cannot be built.
19. ~~**Step 6's smaller holes, none of them safety.**~~ **All five fixed 12 Sep** — see the
   12 Sep lines in §8. (e) is fixed as far as it can be: P3 is now the Door B second-subject
   caller, because T17 §4's P3 names a scheme at the opener and that is a speech path with no
   keypad equivalent. The Done-when still needs that one word changed.
   Original text:
19b. **Step 6's smaller holes, none of them safety.** (a) `call.py:282` handles `Speech` with a
   bare `pass`, so `turn_n` never advances and the `while True` spins forever — invisible in
   keypad-only, a hang the day Step 9 hands it speech. (b) The read-back menu reads a digit and
   throws it away (`call.py:319-323`); sections 1-4 are never replayed. (c) "Anything else = 1"
   sets `category = UNASKED` and then falls straight into the closing — a dead write, Door B is
   not wired. (d) The call-open line's `lang_source` is **always** `Log.open`'s default: the
   Engine learns the real value at turn 0 and never writes it back, so the sim run says
   `"lang_source": "default"` for a caller who pressed `1`. (e) There is no **P3** anywhere in
   the tests or the sim, and the sim has no persona picker at all — non-interactive runs use one
   hardcoded digit sequence. P3 names a scheme at the opener, which is a speech path, so it may
   be fairly out of a keypad-only step — **but then the Done-when needs amending, not ignoring.**
20. **Clean, Step 6:** `Log.write` never raises (6 deliberately bad lines, each written with
   `invalid: true`, under test and passing), turn 0 writes a line and does not spend a cap turn,
   SILENCE carries `turn_n` unchanged plus `silence_n` while NOISE spends a turn — all three
   review-focus items hold. `MAX_TURNS` / `MAX_QUESTIONS` / `STOP_SURVIVORS` /
   `KEYPAD_CARDINALITY_MAX` / `BOX_STRIKES_TO_KEYPAD` read from `tunables.py`, nothing inline.
   No banned word in any of the four files (they emit line ids only, so gate 4 still owns the
   wording). No free model text reaches the Engine — `model` is `None` on every path. `state` is
   forced to `UNKNOWN` and `state_unknown_disclaimer` plays, so no hard-box violation is spoken
   *on the exact path* — the other paths are untested only because of §9 18. No "twilio" outside
   `audio/telephony/`, no runtime import of `data/pipeline/` (`sim.py` imports `p6_snapshot` to
   build its fixture snapshot, which is a dev driver and allowed). No secrets in the files or in
   any of the 23 commits. No queue, pool, registry or concurrency setting — **R1** holds, and
   `test_concurrency_and_import_discipline` asserts it.

21. **The speaking-rule exception belongs on both branches, and Step 4 shipped it on one.**
   `Planner.next_action` applies T10's exception ("do not stop on <=4 while an unasked hard box
   is non-ANY on any survivor") only on the `<=4 survivors` branch. On the **zero-survivor**
   branch it goes straight to the widening ladder. The result is exactly the failure T10 wrote
   the exception to prevent, one branch over: the call stops asking, `gender` and
   `social_category` stay UNASKED, the ladder recovers a scheme that is non-ANY on both,
   `Filter.speakable` refuses to name it, and the caller hears `terminal_empty` while the corpus
   held a match. **This was the real Step 6 blocker.** Fixed in `planner.py`: before returning
   `Widen(rung_box)`, run the same exception over the **widened** survivor set and `Ask` the hard
   box first, minimax-ordered, caps respected. It terminates — each Ask fills a box.
   **T10 D3 amended 13 Sep** — the exception now reads "before any terminal", and it is one
   helper (`_hard_box_to_ask_before_speaking`) used on the `<=4` stop, the widened set and
   the nearest candidates. Four `tests/test_planner.py` tests moved (they now answer
   the hard boxes and still assert the same rungs) and one was added.

22. ~~**Delivery shape ④ NEAREST is unreachable — a contradiction in Architecture §8, not a bug.**~~
   **Closed 13 Sep — you chose (a).** `category` is out of `WIDENING_ORDER`; the ladder is
   `income_band -> age -> occupation`. Shape ④ now fires, and P2 reaches a labelled
   nearest-two. The docs are amended and synced. Original finding kept below for the
   reasoning, which the amendment quotes.
22b. **Delivery shape ④ NEAREST is unreachable — a contradiction in Architecture §8, not a bug.**
   §8 routes `ladder exhausted -> any scheme whose miss-set is soft-only? -> NEAREST`. But
   `WIDENING_ORDER` covers **all four** soft boxes and the ladder drops them cumulatively, so
   "exhausted" means *every soft box was dropped and still nothing survived* — at which point the
   only live constraints are hard boxes, and "no survivor" and "no scheme with a soft-only
   miss-set" are the **same statement**. Any scheme with a soft-only miss-set is caught by the
   rung that drops that box, and the ladder returns ③ WIDENED first. Verified by enumerating all
   1351 keypad-reachable vectors over `fixtures/`: `direct_match`, `overflow`, `widened_match` and
   `empty` all occur, `nearest` never once.
   So build-plan Step 6's Done-when (*"P2 reaches a labelled nearest-two through the full
   ladder"*) and T17 §4 (*"P2 through the full ladder to two nearest schemes labelled as
   non-matches"*) cannot be satisfied by any amount of Step 6 code.
   **Two ways out, and it is your call:**
   (a) **Take `category` out of `WIDENING_ORDER`.** The category is the subject the caller phoned
   about (Door A); relaxing it answers a question they did not ask. With the ladder ending at
   `occupation`, "exhausted" becomes a real state and NEAREST becomes what it was meant to be:
   same subject, hard boxes clean, misses only on soft detail. This is a Step 4 + Step 5 change.
   (b) **Amend the Done-when** to "P2 reaches a labelled widened match through the full ladder"
   and delete shape ④ from Architecture §8, T18 and `terminals.py`.
   I recommend (a) — shape ④ exists because T18 §2 says a nearest is *not a match* and must never
   borrow the widened wording, and that distinction is worth keeping. But (b) is honest and
   cheaper, and nothing in the demo depends on it.

23. ~~**Step 8 blocker**~~ **Fixed 13 Sep.** — model aliases point callers at the wrong scheme.** The alias prompt gave
   *"pm kisan loan"* as an example, and the model copied it onto other schemes: APY has
   `pm kisan loan` (hi and mr), SMAM has `pm कisan मशीन`, PMFBY has `pm kisan insurance` /
   `pm kisan bima`. Door A string-matches aliases before the model, so a caller asking for
   PM-KISAN can be offered APY. Also junk: DAY-NRLM hi `शहरी …` (urban, for a rural mission),
   PMAY-G mr `pm awas ग्रीष्म` (summer). **Fix:** drop the named example from the prompt, delete
   `data_cache/extract/*_aliases.json`, re-run (12 calls), and read the aliases by eye once.
24. ~~**Step 8 blocker**~~ **Fixed 13 Sep.** — `age` and `income_band` are one number with no direction.** APY is
   stored `age=18` (its minimum), so its upper limit is lost; NAPS is stored `age=35` (a maximum).
   The Filter cannot tell which. The data contract §1C says numbers are stored exact as a min and
   a max, and `p6_snapshot.derive_keypad_bands` already reads `{"min": .., "max": ..}`. **Fix:**
   ask for `{"min", "max"}` with a quote each, keep the quote check, delete
   `data_cache/extract/*_facets.json`, re-run (12 calls). Do 23 and 24 in one re-run: 24 calls.
25. **Step 8 non-blockers, for later.** (a) The cache key is `sha + task` only, so a changed
   prompt or model id silently reuses old answers — that is why 23 and 24 need a manual delete.
   (b) The occupation cut filters a hand-written 7-value seed list by what the corpus uses; it
   meets T07's rule but cannot find a value outside the seed. Fine at 12 schemes, cardinality 3.
   (c) `level` and `department` are hardcoded (all 12 are central, so true today). (d) HI/MR
   section chunks are empty — Step 9 fills them. (e) New aliases lean on "helpline / call / help desk" because the
   prompt frames them as helpline speech; callers name a scheme, they do not say "apy exit
   assistance". Weaker matching, not a wrong route. (f) One PM-KISAN Marathi alias says
   `कृषी मानधन` — that is PM-KMY, a different scheme (not in the corpus). (g) An income written
   as "5 lakh" becomes ANY, because the number is not in the quote as digits. Safe, but lossy.
26. ~~**Step 8, should-fix before Step 9**~~ **Fixed 13 Sep** (occupation ANY; NAPS and SMAM also went ANY, see §8). **AB-PMJAY is tagged `occupation = street_vendor`.** The source
   covers rural families on six deprivation tests plus 11 urban worker groups; street vendor is
   one of the 11. The model's own gate_note says it "selected street vendor as representative".
   The quote is verbatim, so the code check passes — the check proves the words exist, not that
   they justify narrowing. Effect: a farmer or labourer only hears Ayushman Bharat after the
   ladder drops occupation. Fix: prompt rule "if the text lists several groups, occupation is
   ANY", delete ab-pmjay facets cache, re-run (1 call). This was in the first run too; the first
   review missed it.
27. ~~**Step 8, should-fix before Step 9**~~ **Fixed 13 Sep** (category set on 12/12). **`category` is ANY on 7 of 12.** The category quote is checked
   against the eligibility text only, but "health", "pension", "business" are said in the
   benefits text. So AB-PMJAY (the only health scheme), APY, DAY-NRLM, PM-SVANIDHI, PMEGP, PMMY
   and SMAM lose their category, and a Door A category answer barely narrows anything. Fix: let
   the category quote match eligibility OR benefits (still verbatim, still in code), delete the
   facets cache, re-run (12 calls).
