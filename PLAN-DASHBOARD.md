# PLAN-DASHBOARD — the dashboard as the front door (3 Oct 2026, round 2)

Status: **a proposal, waiting for the owner's go.** Nothing here is built yet.
Written in plain words on purpose. Read `HANDOFF.md` first if you are new.

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

## 2 · Two parts, both hosted

```
 your browser
      |  (login)
      v
 DASHBOARD on Vercel  ---- asks, with a secret token ---->  ENGINE on a small rented server
 pages + a small relay                                       calls, logs, schemes, clips, keys
                                                                    ^
 phone company (Twilio)  <------------- the call audio ------------+
```

- **The dashboard goes on Vercel.** Your account is reachable from here.
- **The engine goes on a small always-on server, not on Vercel.** It is one long-running
  program that holds a live audio line for the whole call and reads its voice clips from disk.
  Vercel is built for web pages and short requests.
- **Where:** Fly.io, in its Mumbai region. Reasons: you already ran your TSS agent's backend
  there, the `fly` tool is already on this laptop, it keeps a machine on all the time, it does
  the secure audio socket Twilio needs, and Mumbai is close to the callers and to Sarvam.
  About 4 to 7 US dollars a month. It has no free plan and needs a card.
- **Not Render's free plan:** it sleeps after 15 quiet minutes, and a call that hits a sleeping
  server gets silence.
- **What hosting buys:** the site is live all day, the laptop can be shut, and the engine has a
  fixed address, so the "tunnel address changes every start" problem goes away.
- **Caller words** then sit on the server's own disk in Mumbai, behind the token. They are not
  copied anywhere else.

## 3 · Is the engine ready to be hosted today? Not yet. Close.

The call code itself moves cleanly: it is plain Python and needs no special system software.
But an audit on 3 Oct found these gaps. The first four are code, and I can close them. The
last three only you can close.

**Code gaps (about a day of work, step E1 and E2):**

1. **No lock on the open doors.** Anyone who finds the address can open the audio socket. That
   lets a stranger hold the one call slot for ever, so every real caller hears "busy". A
   stranger can also run fake calls that spend your Sarvam and Groq credit. A crafted call id
   can also write files outside the logs folder. On a laptop behind a random tunnel address
   this was a small risk. On a fixed public address it is not.
   Fix: check that each request really comes from Twilio, hand the socket a one-time pass,
   time out a socket that says nothing, clean the call id, and remove the test routes.
2. **No packaging.** There is no recipe for building the server. Fix: one Dockerfile, Python
   3.11 pinned (the audio code needs 3.11 or 3.12).
3. **The voice clips are not in git** (37 MB). A fresh copy of the code cannot start a call.
   Fix: ship the clips inside the server build.
4. **Three loose ends.** The "longest call" limit is written down but never enforced. The
   health check says "ok" even when the clips are missing. Logs sit on a disk that a host
   wipes on every update. Fix: enforce the limit, make the health check real, keep logs on a
   disk that survives.

**Gaps only you can close:**

5. **The Twilio login looks wrong.** The last `make run` logged "401 Unauthorized" when it
   tried to point the number. Until that is fixed, no call can be placed at all.
6. **The Groq key cannot use the model the engine asks for** (known since 1 Oct). Until it is
   fixed, every call works by keypad only: after two spoken answers the caller is told to
   use the keypad.
7. **A Fly.io account**, logged in on this laptop (`fly auth login`). The laptop is not logged
   in now.

**And one honest warning.** The current engine has never taken a real phone call. Tests, the
typed test call, 1,000 simulated callers and a live speech-to-text check all pass. Real calls
on 13 and 15 Sep were on the older code. So the first hosted call is also the first real call.
Hosting makes that test easier (no tunnel, no laptop), but expect to fix things after it.

**Also true today:** only 11 of the 27 checked schemes can be spoken. The other 16 have no
voice clips yet. That waits on your voice choice and Sarvam credit, as before.

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

- **The dashboard** is a Next.js site in a `dashboard/` folder in this repo. Vercel builds it
  from GitHub on every push to `main`. It has a login, the pages, and a small relay: the
  browser only talks to the dashboard, and the dashboard talks to the engine. The engine's
  token never reaches the browser.
- **The engine's data door** is a second small program on the server, grown from
  `tools/call_viewer.py`. It answers "list the calls", "list the schemes" and so on. It runs
  apart from the call server so a slow page can never touch a live call. It refuses any
  request without the token.
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
| **E1** | The doors locked (§3 gap 1 and 4), with tests | No |
| **E2** | The engine on Fly.io: build recipe, clips shipped, logs kept, real health check | Fly login, keys put on the server, Twilio login fixed |
| **E3** | The engine's data door with the token | No |
| **D0** | The look: a design pass with the design skill, one page mocked for you to accept | A yes on the look |
| **D1** | The dashboard live on Vercel: login, sidebar, Home, Calls, engine light | A password |
| **D2** | Live call: Call my phone, the live view, the typed test call | **The first real call** |
| **S1** | Schemes table and detail, Voice lines, play buttons. Test: can the server fetch from myscheme? | No |
| **S2** | "Just this scheme" mode for each pipeline step, safe snapshot switch, backup | No |
| **S3** | Add a scheme from the site, stage by stage, with Undo | Your two approvals per scheme; Muse and Sarvam money |
| **D3** | Usage and money, Quality | No |
| **D4** | Plan and architecture, System | No |
| **D5** | Settings: key status and Test, Muse guard; Replace a key if you say yes | A yes on replacing keys |
| **D6** | The Phase 6 score sheet, listen and review | Your ears |

E1 can start now and needs nothing from you. E2 is the first step that does.

## 9 · What it costs

- **Fly.io:** about 4 to 7 US dollars a month for one small always-on machine and a small disk.
- **Vercel:** the free plan is enough. It is for personal, non-commercial use; a paid service
  would need the paid plan.
- **Twilio:** each "call my phone" uses call minutes.
- **Adding a scheme:** about half a rupee of Muse and about 3,200 characters of Sarvam voice.
- **The dashboard itself** spends nothing on Muse, Sarvam or Groq.

## 10 · Choices only you can make

Each has the default I would pick. "Go with the defaults" is a full answer.

1. **Host the engine on Fly.io, Mumbai?** Default: yes. This also settles the "server location"
   item in `OWNER-END-TODO.md`.
2. **Who uses the site?** Default: you run it; one other person can look but not change.
3. **May keys be replaced from the website?** Default: not at first. Status and Test only.
4. **Voice for new schemes:** the same voices as the 11 live ones? Default: yes. This is the
   voice choice already waiting in `OWNER-END-TODO.md`.
5. **Make the voice for the 16 waiting schemes** as part of S3? Default: yes, once you have
   heard and approved one.

## 11 · What this plan does not include

- Running the call engine on Vercel.
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
