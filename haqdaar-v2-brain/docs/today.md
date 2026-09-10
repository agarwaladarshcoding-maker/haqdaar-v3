---
title: "TODAY — 10 Sep 2026"
slug: today
type: doc
module: architecture
status: reviewed
tags: ["doc", "architecture", "today"]
created: 2026-09-10
updated: 2026-09-10
author: Adarsh Agarwala
last_agent_edit: sync_vault.py
source_file: source-docs/TODAY.md
---

# TODAY — 10 Sep 2026

## Goal for tonight

**A real phone call reaches your laptop, and the repo skeleton is in git.**

That means **Steps 0, 1 and 2** of [[docs/build-plan|`BUILD-PLAN.md`]] are merged, and `v1-skeleton` is tagged.

---

## 1 · Update the brain (15 min)

1. Unzip `haqdaar-pack.zip` somewhere temporary.
2. In your Obsidian vault:
   - **Replace** `MAP` with the new `MAP.md` (rev 27).
   - **Replace** tickets T19, T20, T21, T23 with the new files.
   - **Add** the `docs/` folder: ARCHITECTURE, PRD, BUILD-PLAN, REVIEW, TODAY.
3. Open `MAP.md` in Obsidian and check the header says **rev 27**.

## 2 · Put the vault inside a git repo (15 min)

**The repo root holds the code, and the vault sits inside it as `brain/`.** That way Antigravity and Claude Code read the brain from the same folder they write code in, and every brain change is versioned alongside the code.

```bash
# on GitHub: create an empty private repo named haqdaar (no README)
mkdir haqdaar && cd haqdaar
git init -b main
mv /path/to/your/obsidian-vault ./brain       # or copy it, then re-open "brain" as the vault in Obsidian
cp /path/to/pack/AGENTS.md /path/to/pack/CLAUDE.md .
printf ".env\nlogs/\nsnapshots/*/audio/\ndata_cache/\n.venv/\n__pycache__/\nbrain/.obsidian/workspace*.json\n" > .gitignore
git add . && git commit -m "brain: vault rev 27 + agent rules"
git remote add origin git@github.com:<you>/haqdaar.git
git push -u origin main
```

**Obsidian:** Open folder as vault → choose `haqdaar/brain`.

## 3 · Accounts (60–90 min, do while agents work)

| Service | What to do | Put in `.env` |
|---|---|---|
| **Groq** | console.groq.com → API key (free, no card). Open the Limits page and note tokens/min for 2 models. | `GROQ_API_KEY` |
| **Sarvam** | dashboard → API key; note free credit balance and concurrent-stream limit | `SARVAM_API_KEY` |
| **Twilio** | Sign up (free trial credit). Buy a US number with Voice. **Trial adds a short notice before your greeting** — fine for building. Upgrading (~$20) removes it; decide by 13 Sep. | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` |
| **ngrok** | Sign up → install → `ngrok config add-authtoken <token>` → note your free dev domain | `NGROK_DOMAIN` |
| **Plivo** (background) | Udyam certificate (Aadhaar + PAN) → Plivo signup, India region → upload → submit. Then forget it. | — |

**Also:**
- `.env` stays on your laptop only. Check that `git status` never shows it.
- Laptop: sleep off while plugged in, disk encryption on.

## 4 · Step 0 — repo skeleton (Antigravity → Claude Code)

1. `git checkout -b step-00`
2. **Antigravity** — open the `haqdaar` folder and paste:
   > Implement **Step 0** of `brain/docs/BUILD-PLAN.md`. Follow `AGENTS.md`. Read `brain/docs/ARCHITECTURE.md` and every ticket the step names before writing code. Work on branch `step-00`. Do nothing outside this step. Finish by running the step's **Done when** command and pasting its output.
3. **Claude Code** — in the same folder, paste the block from `brain/docs/REVIEW.md` with `N = 0`.
4. If Claude Code says "safe to merge: yes":
   ```bash
   git checkout main && git merge --no-ff step-00 -m "step 00: repo skeleton" && git push
   ```

## 5 · Step 1 — Twilio smoke call

Same loop, with branch `step-01`. Then do the call yourself:

1. Terminal A: `make run`
2. Terminal B: `ngrok http --url=$NGROK_DOMAIN 8000`
3. Twilio console → your number → **Voice → A call comes in → Webhook** → `https://<NGROK_DOMAIN>/answer` (HTTP POST) → Save.
4. Dial the number from your phone: you hear the trial notice, then a tone. Press **1**, then **9**.
5. Terminal A should show `mark tone_end`, `dtmf 1`, and the call ends.

**Write down in `brain/docs/TODAY.md` under "Results":**
- seconds from dial to tone
- whether the mark and dtmf showed up
- how many of 3 simultaneous calls connected (borrow phones if possible; otherwise note "not measured")

## 6 · Step 2 — contracts and fixture

Same loop, with branch `step-02`. When merged:

```bash
git tag v1-skeleton && git push --tags
```

## 7 · If you have energy left

- Start **Step 7 (scraper)** on branch `step-07`. It doesn't depend on Steps 3–6, so it can run in Antigravity while you review something else.
- Send the team `brain/docs/PRD.md` §1–§5 and ARCHITECTURE §1 and §6 for the slides.

---

## Tomorrow (11 Sep) in one line

Steps 3 → 8: pure engine, console call, scraper and Groq extraction. End the day with `make sim` completing a keypad call against the fixture.

## Results

| Check | Result |
|---|---|
| Dial → tone (s) | |
| mark received | |
| dtmf received | |
| Concurrent calls connected | |
| Groq model A tokens/min | |
| Groq model B tokens/min | |
| Sarvam concurrent limit | |


---
**Wayfinder Map:** [[maps/wayfinder-map|Latest Map]] · **Brain Index:** [[glossary|Glossary]]
