# PLAN-DASHBOARD — the dashboard as the front door (3 Oct 2026, round 3)

Status: **being built.** Done so far: the left bar, Home (D1) and Live call (D3).
Written in plain words on purpose. Read `HANDOFF.md` first if you are new.

**Hosting is dropped (owner, 3 Oct).** The dashboard and the engine run on this computer:
`make dashboard`, then http://127.0.0.1:3210. The build order is §8, the look is §13, the
data shapes are §14.

**Home stays.** The owner asked whether the first plan had a Home page. It did, from the first
round, so it is kept.

Round 2 changes: the engine gets hosted too (§2), an honest list of what it lacks before that
(§3), the Schemes page gets a real table and an "add a scheme" flow (§5), and the build order
now starts with the engine (§8).

---

## 1 · What we are building, in one paragraph

A website you log in to, hosted on Vercel, that is the one place to run and watch Haqdaar. It
has a button that rings your own phone and shows the call as it happens. It lists every call,
every scheme, every spoken line, every rupee and unit of API use, the health of the system,
the plan and the architecture, and the settings. You can add a scheme from it. It looks and
works like a small CRM: a sidebar on the left, tables you can filter, a detail view per row.

The phone line cannot take calls from the public yet (trial account, one verified number, no
Indian number). So the dashboard is built around **calls we start ourselves**: "call my phone"
and a free typed test call. When the line opens later, incoming calls show up in the same list.

## 2 · Hosting: dropped

Owner, 3 Oct: no hosting, for the site or for the engine. Everything runs on this computer.
`make run` starts the engine, `make dashboard` starts the dashboard. The earlier hosting
plan (Fly.io for the engine, Vercel for the site) and its list of gaps were removed from this
file; they are in git history (commit e45d2f7) if hosting ever comes back.

## 3 · (removed with hosting)

## 4 · The pages (the sidebar)

### Home
- A status light: engine on or off, the snapshot in use, how many schemes are live on calls.
- The big button: **Call my phone**.
- Today in numbers: calls, how many passed the judge, average length, slowest reply.
- "Needs a look": calls with problems, a failed judge, a missing key, Muse near its cap,
  schemes waiting for your review.
- The last 5 calls. Money spent today.

### Live call
- **Call my phone** rings the one number saved on the engine. The page never takes a number
  typed into it, so nobody can use the site to ring strangers.
- While the call runs: the back and forth as it happens (AI on the left, you on the right),
  what the engine has learned so far, how many schemes are still in play, and the timers.
- **Typed test call** for when there is no phone: type the keys or the words, and the same
  engine answers. It is free and it lands in the call list marked "sim".
- A plain note that the line does not take outside calls yet.

### Calls
- A table of every call: when, how long, language, turns, phone or sim, judge PASS or FAIL,
  problems. Filters for each. Search by call id.
- Click a row: the full back and forth with times (the page from step 5.5), the judge's
  reason, the schemes read out, and a bar view of where the time went.
- Your own verdict and a note on each call. This is the score sheet for the 10-call test.
- Download a call as a file.

### Schemes — see §5

### Voice lines
- The 46 fixed lines the AI can say, in three languages, each with a play button.

### Usage and money
- One card per service: Muse (rupees, against the Rs 60 total and Rs 30 a day caps), Sarvam
  voice (characters), Sarvam speech-to-text (seconds, success rate, speed), Groq (tokens,
  errors), Twilio (calls, minutes, and the price Twilio reports). A chart per day.
- Honest gap: today only Muse is counted in rupees. The others are counted in units until a
  price for each is added.

### Quality
- Judge pass rate. Reply time and speech-to-text time (middle and worst). "Not understood" rate
  by language. Why calls stopped asking. How often voice fell back to keypad.

### Plan and architecture
- How a call flows, as a picture. The phases with done and left. The project log. The owner's
  to-do list as a checklist. All read from the files already in the repo.

### System
- The smoke checks, code version, last restarts, the tail of the server log.

### Settings
- **API keys:** for each key, "set" or "not set", and a **Test** button that makes one free
  call to prove the key works. A key's value is never shown, not even part of it.
- **Replace a key** (only if you say yes): a box you can only type into. It can never be read back.
- **My phone:** the number the button rings, shown with only the last 2 digits.
- **Muse guard:** today's spend, and the block and unblock buttons.
- **Tunables:** the engine's numbers (caps, timings), shown read-only.
- **Access:** who can log in.

## 5 · Schemes: the table, and adding one

### The table
One row per scheme. Search box on top, filters beside it.

| Column | What it shows |
|---|---|
| Name | English name, Hindi name under it |
| Topic | one of the 9 topics (farming, health, housing ...) |
| From | central or state, and the ministry |
| Who it is for | short tags: gender, group, age band, income band, work |
| Hindi · Marathi · English | a tick or a cross per language, from the safety checks |
| Voice | clips made or not |
| State | **Live on calls** · Ready, no voice · Waiting for your review · Failed a check · Set aside |
| Source | link to the myscheme page, and how old our copy is |
| Actions | Open · Take off calls · Fetch again |

Today that table would show 30 rows: 11 live, 16 ready with no voice, 3 set aside.

Click a row for the detail: the spoken card in all three languages, who it is for, why a
check failed, the source text beside the card, and a play button for every clip.

### Adding a scheme
You do not type a scheme in. You **pick it from the government list** and the pipeline does
the rest, one stage at a time, with you in the loop. The site already holds the list of all
746 central schemes from myscheme (name, ministry, tags).

1. **Pick.** Search the 746, click Add. (Or paste a myscheme address.)
2. **Fetch.** The page is read from myscheme. Free.
3. **Write the card.** Muse turns the page into a short spoken card, then it is put into
   Hindi and Marathi. Paid: about half a rupee per scheme so far. The site shows the cost
   before it spends, and the Rs 30 a day guard still applies.
4. **Safety checks.** The five checks run by themselves: numbers match the source, no
   promises, no padding, right script, nothing empty. Free. A fail shows the reason.
5. **Your review.** You read the card in the three languages and press Approve. Today the
   code does not force this step. The dashboard will.
6. **Make the voice.** Sarvam speaks the card: about 18 clips, about 3,200 characters per
   scheme. Paid. You listen in the browser and press Approve.
7. **Publish.** A new snapshot is built. The 1,000-caller check runs by itself and must show
   0 crashes and 0 untrue answers. Then the engine switches to the new snapshot between calls.
   The old snapshot is kept, so **Undo** is one click.

Each scheme shows where it is in these seven stages, like a deal moving through a pipeline in
a CRM. A scheme can wait at a stage for days. Nothing reaches a caller without both of your
approvals.

**Take off calls** does the reverse: the scheme is set aside and a new snapshot is published
without it.

### What has to change in the code for this (it is real work)
- Every pipeline step runs over the whole list today. Each needs a "just this scheme" mode.
  The voice step matters most: today it would also make the clips for all 16 waiting schemes.
- The list of chosen schemes is a file edited by hand. It becomes data the engine owns.
- The switch to a new snapshot must be safe mid-day: all or nothing, and the engine must pick
  it up without a restart.
- **Where the truth lives.** Today scheme data is in git. Once you add schemes from the site,
  the server's disk is the truth, and git is behind. So the server makes a backup you can
  download, every night and before every publish.

### Limits to know now
- **Topics are fixed at 9.** A scheme that fits none cannot be added from the site.
- **A new answer choice** (say, a kind of work the engine has never asked about) needs new
  spoken lines. The site will say so and stop, and that scheme needs a code change.
- **Fetching from the server may be blocked.** myscheme may refuse a data-centre address. If
  so, the fetch stage runs on your laptop and the rest on the server. We find out in step S1.
- **Money.** Adding schemes spends Muse and Sarvam. Voice for the 16 waiting schemes alone is
  about 49,000 characters.

## 6 · How it works under the hood

- **The dashboard** is a Next.js site in the `dashboard/` folder of this repo. For now it runs
  on this computer only (port 3210). The browser only talks to the dashboard, and the
  dashboard talks to the data door. A login and a token come back with hosting.
- **The data door** is `tools/dashboard_api.py` (port 8001), grown from
  `tools/call_viewer.py`. It answers "what does Home show", "list the calls" and so on from
  files the project already writes. It only reads, and it runs apart from the call server, so
  a slow page can never touch a live call.
- **`make dashboard`** starts both. Ctrl+C stops both.
- **The live view** asks for the call's timed trace once a second. No new moving parts.
- **The call button:** the dashboard asks the engine, and the engine asks Twilio to ring the
  saved number, as `make call` does today. One call at a time.
- **Scheme jobs** run on the server one at a time and never while a call is live. The call
  button is off while a paid stage is running.
- **Your laptop** becomes the workshop: you change code there and push; the server and the
  site update from GitHub.

## 7 · Keeping it safe

What callers say can include caste group, income and age. That is private.

1. **Login on every page.** One password for you. A second, view-only password for anyone you
   show it to: they can look, they cannot place calls, add schemes or touch settings.
2. **The engine trusts only Twilio and the token** (gap 1 in §3).
3. **Caller words stay on the engine's disk.** The dashboard shows them and keeps no copy.
4. **Keys are never shown.** You put them on the server yourself with one command. They do
   not pass through chat, the dashboard or git.
5. **The call button rings the saved number only**, one call at a time, with a daily limit.
6. **Every paid step shows its cost first** and obeys the money guards.
7. **Tests never spend money.** Same rule as today.

## 8 · Build steps, in order

One step at a time, on your word. Each ends with something you can check.

| Step | What you get | Needs you? |
|---|---|---|
| **D1** | **Done.** The left bar with every page, and the Home page, on real data | No |
| **D2** | Calls: the table with filters, and each call as a back and forth with times | No |
| **D3** | **Done.** Live call: Call my phone, the call line by line, the typed test call | The button is untried on a real phone: needs the Twilio login fixed and `make run` |
| **S1** | Schemes table and detail, Voice lines, play buttons | No |
| **S2** | "Just this scheme" mode for each pipeline step, safe snapshot switch, backup | No |
| **S3** | Add a scheme from the site, stage by stage, with Undo | Your two approvals per scheme; Muse and Sarvam money |
| **D4** | Usage and money, Quality | No |
| **D5** | Plan and architecture, System | No |
| **D6** | Settings: key status and Test, Muse guard; Replace a key if you say yes | A yes on replacing keys |
| **D7** | The Phase 6 score sheet, listen and review | Your ears |

D2 (Calls) is next and needs nothing from you.

## 9 · What it costs

- **The dashboard itself** costs nothing and spends nothing on Muse, Sarvam or Groq.
- **A typed test call** is free.
- **Call my phone** uses Twilio call minutes, and speech-to-text if you speak.
- **Adding a scheme:** about half a rupee of Muse and about 3,200 characters of Sarvam voice.

## 10 · Choices only you can make

Each has the default I would pick. "Go with the defaults" is a full answer.

1. (Hosting: dropped.)
2. **Who uses the site?** Default: you run it; one other person can look but not change.
3. **May keys be replaced from the website?** Default: not at first. Status and Test only.
4. **Voice for new schemes:** the same voices as the 11 live ones? Default: yes. This is the
   voice choice already waiting in `OWNER-END-TODO.md`.
5. **Make the voice for the 16 waiting schemes** as part of S3? Default: yes, once you have
   heard and approved one.

## 11 · What this plan does not include

- Hosting of any kind. Dropped by the owner.
- Calls from the public. The line is not open.
- The Indian provider (step 5.4, dropped for now).
- New topics, or new answer choices, from the site.
- Calling from the browser with a microphone. A good later idea, and a project of its own.

## 12 · Where the ideas came from

- Your earlier TSS dashboard: a call button, call history, a live transcript, a timing chart,
  a password login, and a relay to a backend on Fly.io. This plan keeps that shape.
- Voice-agent products (Retell, Vapi and tools built on them): call history with filters, a
  page per call with transcript and reply times, cost per call, pass and fail counts.
- CRMs: records that move through named stages, a table with filters, a detail view per row.
- Dashboard practice: a few key numbers on top, a list of what needs attention, then tables.

## 13 · The look (second version, 3 Oct)

The first version (a yellow signboard, wide heavy letters) was rejected by the owner as bad.
This version follows the owner's reference picture: a dark, rounded bar on the left, grey
labels with thin line icons, and the open page shown as a mint pill. Rules for the choices
came from the UI UX Pro Max skill (installed in `.claude/skills/ui-ux-pro-max/`), which
recommends a plain, minimal, dark dashboard style for this kind of tool.

**We design one page at a time.** Home and the left bar are done. Each next page gets its own
pass and the owner's look before the one after.

**Colours** (dark is the main set; a light set follows the computer's setting):

| Name | Dark | Light | Used for |
|---|---|---|---|
| Ground | `#24262C` | `#F2F4F6` | the page behind everything |
| Panel | `#1B1D22` | `#FFFFFF` | the left bar and every card |
| Raised | `#2A2D34` | `#EEF1F4` | hover, icon tiles, bar tracks |
| Text | `#ECEEF2` | `#171A21` | words |
| Muted | `#9AA0AD` | `#5D6675` | labels, hints, menu items not open |
| Mint | `#BFE8DC` | `#BFE8DC` | the open page in the menu, the main button |
| Mint line | `#8FDCC6` | `#12806A` | links, meters, the caller in the call tape |
| Green / Amber / Red / Blue | | | fine · look at this · wrong · a note |

Mint is the only accent. Green, amber and red are kept for meaning, never for decoration.

**Type.** One plain font for everything: **Inter**. Hindi and Marathi words fall to **Noto
Sans Devanagari**. Numbers line up in columns. No second display font, no capitals-only labels.

**The left bar.**
- A rounded dark panel that floats beside the page.
- One item per page: a thin line icon and a name. The open page is a mint pill.
- **Fold menu** at the foot shrinks it to icons only, as in the reference. The choice is
  remembered. On a narrow screen it is always folded.
- The engine lamp sits above the fold button.

**Cards.** Rounded dark panels with no borders, 20 px apart. A card has a title, and at most
one small link or tag on the right.

**Signs that carry meaning.**
- A problem, a warning and a note each have their own icon and colour, not colour alone.
- **The call tape:** each call is drawn as a strip. A grey bar is the AI speaking (longer bar,
  longer speech). A mint tick is the caller. Amber is "not understood", red is a problem.

**Words.** Plain and short. A button says what it does. An empty or broken state says what
happened and what to do next. A missing number is a dash with the reason under it.

**Checked against the skill's list:** icons are drawn icons, not emoji · every clickable thing
is at least 44 px tall and shows a hover and a keyboard focus state · text contrast is 4.5:1
or better in both sets · reduced motion is respected · no sideways scroll at 375, 768, 1024
and 1440 px wide.

## 14 · Data shapes

The site asks the data door one question per page. Home asks `GET /api/home`:

| Part | What it holds |
|---|---|
| `engine` | `on`, `live_call` (the call going on now, or none), `snapshot`, `line`, `phone_tail` (last 2 digits only) |
| `numbers` | for the last 24 hours: `calls`, `judged`, `passed`, `avg_length_s`, `slowest_reply_s`, `reply_budget_s`; and `all_calls`, `phone_calls` |
| `needs` | a list, worst first: `level` (bad, warn, info), `title`, `detail`, `page` (where to go) |
| `schemes` | `chosen`, `checked`, `live`, `no_voice`, `set_aside`, `set_aside_slugs`, `languages` |
| `money` | `muse` (`today`, `day_cap`, `all`, `cap`, `blocked`, `open`) and `units` (name, value, unit, note per service) |
| `recent` | the last 5 calls: id, when, language, phone or sim, length, turns, problems, verdict, and `strip` (the marks for the call tape) |

"Last 24 hours", not "today": the owner works at night, and a count that resets at midnight
would be wrong at 1 a.m.

"Needs a look" is worked out from real signs, not guesses: the tunnel's last line in the
server log (Twilio login), the last three model requests in the Groq ledger, the Muse guard,
failed or troubled calls, schemes with no voice, audit verdicts still waiting, and whether a
real phone call has ever been logged.

Still served from step 5.5: `GET /api/calls` and `GET /api/calls/{key}`.

**Live call** asks `GET /api/live` once a second: `engine` (`on`, `live_call`, `phone_tail`)
and `test` (the typed test call: `key`, `active`, `waiting` for language, words or a key).
The call on screen comes from `GET /api/calls/{key}`; its `info.known` is what the engine has
learned (box and value). Three actions, each refused unless it comes from the dashboard:
`POST /api/call-me` (rings the saved number only), `POST /api/test-call` (start),
`POST /api/test-call/input` (a key, words, `silence` or `hangup`).

