# STEP 6.3 — The Calls page of the dashboard (Antigravity work order)

Build one page of the local dashboard: **Calls**. A plain table of every call, and a page per
call that shows it line by line. Keep the design simple and clear. Reuse what exists; add no
new colours, fonts or libraries.

---

## 0 · Setup

- Base: branch `step-6.1-dashboard-home`, at the commit that adds this file. Check with
  `git log --oneline -1`. If this file is not in that commit, STOP and reply "wrong base".
- New branch: `git switch -c step-6.3-calls-page`.
- Python: always `.venv/bin/python` (3.11). Node is installed; the site lives in `dashboard/`.
- Read first, in this order:
  1. `AGENTS.md` (the rules) and `dashboard/AGENTS.md` (this Next.js is version 16: read
     `dashboard/node_modules/next/dist/docs/` before writing Next code; page `params` is a Promise).
  2. `PLAN-DASHBOARD.md` §4 "Calls", §13 (the look), §14 (data shapes).
  3. `.agent/NOTES.md`, last three sections (dashboard D1, the second look, Live call D3).
- **The owner is running `make dashboard` himself on ports 3210 and 8001.** Do not stop it,
  restart it, or bind those ports. Another app of his uses port 3000: leave it alone. To look
  at your work, run a private copy on 3211 and 8011 (see §5).
- Rules that stay: tests never call a paid API (`tests/conftest.py` guard stays); no Muse,
  Sarvam, Groq or Twilio calls at all in this step; no phone calls; nothing hosted; no merge,
  no push, no tag. Smallest correct change.

## 1 · What exists that you build on

| Thing | Where | What it gives you |
|---|---|---|
| Call list + one call | `tools/call_viewer.py`: `Calls.all()`, `build_call()` | every call as `{info, items}`, newest first |
| Data door | `tools/dashboard_api.py` (port 8001) | `GET /api/calls`, `GET /api/calls/{key}`, `GET /api/home`, `GET /api/live`; `from_dashboard` guard for actions; `strip()` makes the call tape marks |
| Site relay | `dashboard/app/api/door/[...path]/route.ts` | the browser's only way to the door; whitelists paths; POST needs same origin |
| The look | `dashboard/app/globals.css` | all colours and pieces: `.card`, `.chip-*`, `.btn`, `.calls` table, `.talk`, `.say`, `.bubble`, `.pairs` |
| Call tape | `dashboard/app/ui/CallTape.tsx` | the little strip per call (AI bars, caller ticks) |
| The call, line by line | `dashboard/app/ui/LiveCall.tsx` | the talk list and the "This call" panel, today only on Live call |
| Left bar | `dashboard/app/lib/nav.ts` | `calls` is listed, `built` not set yet |
| Home | `dashboard/app/page.tsx` | still links calls to the old page on port 8001 |

## 2 · Build

### 2a · Data door (`tools/dashboard_api.py`)

1. **`GET /api/call-rows`** — one list for the table. Each row is `{key, ...info, strip, mine}`:
   the same `info` as `/api/calls`, plus `strip(call)` (already written) and `mine` (the
   owner's verdict, below, or `null`). Newest first. Leave `/api/calls` as it is (the old page uses it).
2. **The owner's verdict on a call.** Kept in `logs/verdicts.json` as
   `{"<key>": {"verdict": "pass" | "fail" | "unsure", "note": "...", "at": "2026-10-03T21:40:00"}}`.
   - `GET /api/verdicts` returns that object (empty `{}` if no file).
   - `POST /api/calls/{key}/verdict` with body `{"verdict": "pass", "note": "..."}`:
     guarded by `from_dashboard`; 404 if the call does not exist; 422 for any other verdict
     word; note at most 500 characters; saves by writing a temp file and renaming it, so a
     crash never leaves half a file. Saving again replaces the old verdict.
   - The file path is a constructor argument so tests use a temp folder.
3. Add the new POST path to the relay whitelist in `route.ts` (pattern `^calls/[\w.~-]+/verdict$`).
   GET rows and verdicts are fetched server-side by the pages, like `getHome()` does.

### 2b · Shared pieces (`dashboard/app/ui/`)

4. Move the talk list and the "This call" panel out of `LiveCall.tsx` into `Talk.tsx`
   (`<Talk call={...} live={bool} />` and `<CallFacts call={...} />`). Live call must look and
   behave exactly as before. This is the only refactor allowed.

### 2c · The Calls list (`dashboard/app/calls/page.tsx`)

5. Server page. Filters live in the address, so a filtered view can be bookmarked:
   `/calls?source=phone&lang=hi&judge=fail&q=CA42`. Filters are plain links styled as pills
   (the open one is mint, like the left bar). Search is a small GET form on `q` (matches the
   call id).
   - **Source:** All · Phone · Typed test
   - **Language:** All · Hindi · Marathi · English
   - **Judge:** All · Pass · Fail · Not judged
6. One line above the table with the counts for what is shown, for example
   "12 calls · 9 passed the judge · 2 failed · 1 not judged".
7. The table (reuse `.calls`): **Call** (id as a link to its page, and under it "Phone" or
   "Typed test", turns) · **When** · **Language** · **How it went** (the call tape) · **Length**
   ("Not timed" for typed calls) · **Judge** (Pass / Fail chip, reason on hover) · **Yours**
   (your verdict chip, or a dash).
8. Show the newest 200 rows. If there are more, say "Showing the newest 200 of N".
9. Empty states say what to do: no calls at all → "No calls yet. Start one on the Live call
   page." with a link; filters match nothing → "No call matches these filters." with a
   "Clear filters" link.

### 2d · One call (`dashboard/app/calls/[key]/page.tsx`)

10. Top: a "← All calls" link, the call id as the title, and under it
    "Typed test · Hindi · 02 Oct, 23:37 · 8 turns". Unknown key → Next's `notFound()`.
11. Two columns, like Live call: left **The call** (`<Talk>`, ended, full height, no typing
    box); right **This call** (`<CallFacts>`), then **Your verdict**:
    - three buttons Pass · Fail · Not sure (the chosen one is mint), a note box with a visible
      label "Note (optional)", and **Save verdict**. After saving, the button area says
      "Saved" with the time. Errors show in the red `.alert` box with `role="alert"`.
    - under it, a link **Download this call** (`/api/door/calls/{key}`, `download` attribute,
      file name `<key>.json`).
12. If the call is still live (`info.live`), show a link "Watch it live" to `/live?call=<key>`
    instead of the verdict form.

### 2e · Joining it up

13. `nav.ts`: mark Calls `built: true` (remove `step`/`will`).
14. Home (`app/page.tsx`): the last-calls links and "Needs a look" call links go to
    `/calls/<key>` (not port 8001). Live call, when a call has ended: add "Open in Calls".
15. `PLAN-DASHBOARD.md`: §8 mark D2 done; §14 add the new routes and the verdict file shape.

## 3 · The design, in short

- Same look as Home and Live call: dark rounded cards on the grey ground, mint for the open
  filter and the chosen verdict, green / amber / red only for meaning.
- Nothing new: no new colours, fonts, icon sets or packages. Icons from `lucide-react` only.
- Plain words, sentence case, buttons say what they do. A missing value is a dash.
- Every click target at least 44 px tall, visible keyboard focus, works at 375, 768, 1024 and
  1440 px wide with no sideways scroll (the table may scroll inside its card, as on Home).

## 4 · An example, so the owner can see what is coming

These rows are the real calls on disk today.

**The list, `/calls`:**

```
Calls
Every call, newest first. Open one to read it line by line.

Source  [All] Phone  Typed test     Language  [All] Hindi  Marathi  English
Judge   [All] Pass  Fail  Not judged                      [ Search call id      ]

3 calls · 3 passed the judge · 0 failed · 0 not judged
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ Call                 When           Language  How it went            Length    Judge  Yours │
│ test_1790977071358   03 Oct, 01:58  Hindi     ▬▬|▬▬|▬|▬▬▬|▬▬        Not timed  Pass    –   │
│  Typed test, 2 turns                                                                       │
│ sim_1790964470       02 Oct, 23:37  Hindi     ▬|▬¦▬|▬|▬|▬|▬|▬|▬     Not timed  Pass    –   │
│  Typed test, 8 turns                          6 not understood                             │
│ sim_1790964228       02 Oct, 23:33  Marathi   ▬▬▬|▬▬▬|▬▬▬|▬▬▬       Not timed  Pass   Pass │
│  Typed test, 2 turns                                                                       │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**One call, `/calls/sim_1790964228`:**

```
← All calls
sim_1790964228
Typed test · Marathi · 02 Oct, 23:33 · 2 turns

┌ The call ─────────────────────────────────┐  ┌ This call ──────────── Judge: pass ┐
│ AI                                         │  │ Language  Marathi   Turns     2     │
│ ┌ Namaste. This is Haqdaar. For Hindi … ┐  │  │ Not understood 0    Problems  0     │
│                              Caller        │  │ What the engine knows               │
│                        ┌ pressed 2 ┐       │  │   Topic                 farming     │
│                        Understood          │  │ Schemes read out                    │
│ AI                                         │  │   प्रधानमंत्री कृषी मानधन निधी …          │
│ ┌ तुम्हाला कशात मदत हवी आहे ते सांगा … ┐   │  └─────────────────────────────────────┘
│                              Caller        │  ┌ Your verdict ──────────────────────┐
│          ┌ "मला कृषी योजना हवी आहे" ┐       │  │ [Pass]  Fail  Not sure              │
│          Guessed, asking to confirm: Topic │  │ Note (optional)                     │
│          = farming                         │  │ ┌ Right schemes, a bit slow ──────┐ │
│ …                                          │  │ [ Save verdict ]  Saved 21:40      │
│ stopped asking: survivors_le_4 …           │  │ Download this call                  │
└────────────────────────────────────────────┘  └─────────────────────────────────────┘
```

**What is saved when the owner presses Save verdict** (`logs/verdicts.json`):

```json
{"sim_1790964228": {"verdict": "pass", "note": "Right schemes, a bit slow", "at": "2026-10-03T21:40:00"}}
```

## 5 · Tests and checks

- `tests/test_dashboard_api.py`: call-rows gives `strip` and `mine`; save, replace and read a
  verdict; 403 without the dashboard header; 404 for an unknown call; 422 for a bad verdict
  word; a note over 500 characters is refused; the file survives a new app on the same path.
- All of these must pass, and paste the output lines into your report:
  - `.venv/bin/python -m pytest -q` (501 before this step; more after, 0 failed)
  - `make stress` → crashes 0, truth failures 0
  - `cd dashboard && npx tsc --noEmit && npm run build` → no errors
  - `python3 sync_vault.py --status` and `.venv/bin/python -m py_compile tools/dashboard_api.py`
- **Look at it** with a private copy, never the owner's:
  ```
  .venv/bin/python -m tools.dashboard_api --port 8011 &
  cd dashboard && npm run build && ENGINE_API=http://127.0.0.1:8011 npx next start --hostname 127.0.0.1 --port 3211 &
  CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  "$CH" --headless=new --disable-gpu --hide-scrollbars --window-size=1440,1100 --virtual-time-budget=8000 --screenshot=calls.png http://127.0.0.1:3211/calls
  ```
  Take screenshots of `/calls`, a filtered `/calls?lang=mr`, one call page, the same in light
  (`--blink-settings=preferredColorScheme=1`), and narrow (`--window-size=760,1300`). Look at
  each one and fix what looks wrong. Save one verdict through the page's own form and check
  `logs/verdicts.json`, then remove that test verdict. Stop your private copy at the end
  (`pkill -f "port 3211"`, `pkill -f "dashboard_api --port 8011"`).

## 6 · Records and hand-back

- `.agent/TASK.md` checklist as you go; `.agent/NOTES.md` findings as you find them.
- `PROJECT-UPDATE.md`: a new entry at the top of §3, in plain short words: what the page
  does, what the owner must do (restart `make dashboard` once), the checks.
- One commit on `step-6.3-calls-page`. Do not merge, push or tag.
- Reply with: the branch, `git log --oneline step-6.1-dashboard-home..HEAD`, the check
  output lines, the screenshot file paths, and anything you could not do and why.

## 7 · Do not

- Do not touch the call engine (`haqdaar/`), the call server, the sim, or the pipeline.
- Do not delete the old call page on port 8001.
- Do not add pagination, charts, sorting menus, bulk actions or anything not listed above.
- Do not start or stop the owner's `make dashboard`, and do not use ports 3000, 3210, 8001.
