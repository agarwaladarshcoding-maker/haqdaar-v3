# PLAN-DASHBOARD — the dashboard as the front door (3 Oct 2026)

Status: **a proposal, waiting for the owner's go.** Nothing here is built yet.
Written in plain words on purpose. Read `HANDOFF.md` first if you are new.

---

## 1 · What we are building, in one paragraph

A website you log in to, hosted on Vercel, that is the one place to run and watch Haqdaar. It
has a button that rings your own phone and shows the call as it happens. It lists every call,
every scheme, every spoken line, every rupee and unit of API use, the health of the system,
the plan and the architecture, and the settings. It looks and works like a small CRM: a
sidebar on the left, tables you can filter, and a detail view for each row.

The phone line cannot take calls from the public yet (trial account, one verified number, no
Indian number). So the dashboard is built around **calls we start ourselves**: "call my phone"
and a free typed test call. When the line opens later, incoming calls just show up in the same
list. Nothing has to be rebuilt.

## 2 · The one big fact that shapes everything

**The website can live on Vercel. The call engine cannot, for now.**

- The engine is one long-running Python program. It holds a live audio socket with the phone
  company for the whole call, reads 37 MB of voice clips from disk, and serves one caller at a
  time. It runs on your laptop today, behind a tunnel.
- Vercel is built for web pages and short requests. Its docs now show WebSocket support, but
  nobody has proven a phone audio stream with our 1.2 s reply budget on it. That is a research
  job, not a safe step. We do not bet the dashboard on it.

So there are two parts, and the dashboard talks to the engine:

```
 your browser
      |  (login)
      v
 DASHBOARD on Vercel  ---- asks, with a secret token ---->  ENGINE on your laptop (later: a server)
 pages + a small relay                                       calls, logs, schemes, clips, keys
                                                                    ^
 phone company (Twilio)  <------------- the call audio ------------+
```

What this means for you:
- **Engine on:** everything works, live.
- **Engine off (laptop asleep):** the dashboard still opens. Schemes, spoken lines, the plan and
  the architecture still show, because they are copied into the site when it is built. Calls,
  live view, usage and settings say "engine is offline" in plain words.

## 3 · The pages (the sidebar)

### Home
- A status light: engine on or off, the snapshot in use, how many schemes are live on calls.
- The big button: **Call my phone**.
- Today in numbers: calls, how many passed the judge, average length, slowest reply.
- "Needs a look": calls with problems, a failed judge, a missing key, Muse near its cap.
- The last 5 calls. Money spent today.

### Live call
- **Call my phone** rings the one number saved on the engine. The page never takes a number
  typed into it, so nobody can use the site to ring strangers.
- While the call runs: the back and forth as it happens (AI on the left, you on the right),
  what the engine has learned so far (language, topic, age band and so on), how many schemes
  are still in play, and the timers (reply time, speech-to-text time).
- **Typed test call** for when there is no phone: type the keys or the words, and the same
  engine answers. It is free and it lands in the call list marked "sim".
- A plain note that the line does not take outside calls yet.

### Calls
- A table of every call: when, how long, language, turns, phone or sim, judge PASS or FAIL,
  problems. Filters for each of those. Search by call id.
- Click a row: the full back and forth with times (this is the page built in step 5.5), the
  judge's reason, the schemes read out, and a bar view of where the time went.
- Your own verdict and a note on each call. This becomes the score sheet for the 10-call test
  (Phase 6): 10 callers, the 7 hard cases ticked off, 8 or more PASS.
- Download a call as a file.

### Schemes
- A table of all 30 chosen schemes: name, topic, ministry, and for each of Hindi, Marathi and
  English whether it passed the safety checks. A mark for "live on calls" (11 today) and for
  "set aside" with the reason (3 today).
- Click a scheme: its spoken card in all three languages, who it is for, the source page and
  the date it was fetched, why a check failed, and **play buttons** for each clip.

### Voice lines
- The 46 fixed lines the AI can say, in three languages, each with a play button.

### Listen and review (later step)
- A queue of cards and clips with "sounds right" and "not right" buttons. This is the 3.7
  audit and the listening job, done in the browser instead of the terminal.

### Usage and money
- One card per service: Muse (rupees, against the Rs 60 total and Rs 30 a day caps), Sarvam
  voice (characters), Sarvam speech-to-text (seconds, success rate, speed), Groq (tokens,
  errors), Twilio (calls, minutes, and the price Twilio reports).
- A chart per day.
- Honest gap: today only Muse is counted in rupees. The others are counted in units. Rupees
  for them need a price for each, which is a small follow-up.

### Quality
- Judge pass rate. Reply time and speech-to-text time (middle and worst). "Not understood" rate
  by language. Why calls stopped asking. How often voice fell back to keypad.

### Plan and architecture
- How a call flows, as a picture. The phases with done and left. The project log. The owner's
  to-do list as a checklist. All read from the files already in the repo, so there is one
  source and it cannot drift.

### System
- The smoke checks (Python, snapshot and clips, keys present, logs writable, Muse).
- Tunnel address, code version, last restarts, the tail of the server log.

### Settings
- **API keys:** for each key, "set" or "not set" and a **Test** button that makes one free
  call to prove the key works. A key's value is never shown, not even part of it.
- **Replace a key** (last step, see §6): a box you can only type into. The value goes to the
  engine, is written to its `.env`, and the engine restarts. It can never be read back.
- **My phone:** the number the button rings, shown with only the last 2 digits.
- **Muse guard:** today's spend, and the block and unblock buttons.
- **Tunables:** the engine's numbers (caps, timings), shown read-only.
- **Access:** who can log in.

## 4 · How it works under the hood

**The dashboard (new, on Vercel).** A Next.js site in a `dashboard/` folder in this repo. Vercel
builds it from GitHub on every push to `main`. It has a login, the pages, and a small relay:
the browser only ever talks to the dashboard, and the dashboard talks to the engine. The
engine's token never reaches the browser.

**The engine's data door (new, small).** A second small program on the engine machine, grown
from `tools/call_viewer.py`. It only reads files and answers questions like "list the calls"
or "list the schemes". It runs apart from the call server, as it does today, so a slow page
can never touch a live call. It refuses every request that does not carry the token.

**Finding the engine.** The tunnel's address changes on every start. So each time the engine
starts, it tells the dashboard its new address ("check-in"), signed with the token. The
dashboard keeps that one line in a small free store and shows "last seen 10 s ago". If you
later own a web address, a named Cloudflare tunnel gives a fixed address and this step goes away.

**The live view.** The engine already writes a timed trace of each call. The page asks for it
once a second. No new moving parts.

**The call button.** The dashboard asks the engine; the engine asks Twilio to ring the saved
number, the same way `make call` does today. One call at a time: the button is off while a
call is running.

## 5 · Keeping it safe

What callers say can include caste group, income and age. That is private. The rules:

1. **Login on every page.** One password for you. A second, view-only password for anyone you
   show it to: they can look, they cannot place calls or touch settings.
2. **The engine trusts only the token.** No token, no answer. Today the engine has no lock at
   all; this adds one.
3. **Caller words stay on the engine.** No copy in the cloud. The price: no call history while
   the laptop is off. (A cloud copy is a choice for later, see §8.)
4. **Keys are never shown.** Not in the page, not in logs, not in an error.
5. **The call button cannot be turned on a stranger.** It rings the saved number only, one call
   at a time, with a daily limit.
6. **Tests never spend money.** Same rule as today.

## 6 · Build steps, in order

Each step ends with something you can open and click. One step at a time, on your word.

| Step | What you get | Needs you? |
|---|---|---|
| **D0** | Your answers to §8, and the look: a design pass with the design skill, one page mocked up for you to accept | Yes: answers, and a yes on the look |
| **D1** | The engine's data door, with the token and tests. Nothing to see yet | No |
| **D2** | The dashboard live on Vercel: login, sidebar, Home, Calls, engine on/off light | A password of your choice |
| **D3** | Live call: Call my phone, the live view, the typed test call | One real call to prove it |
| **D4** | Schemes and Voice lines, with play buttons | No |
| **D5** | Usage and money, Quality | No |
| **D6** | Plan and architecture, System | No |
| **D7** | Settings: key status and Test, Muse guard. Then, if you say yes, Replace a key | A yes on replacing keys |
| **D8** | Listen and review, and the Phase 6 score sheet | Your ears |

D1 and D2 are the base. After them the order can change to whatever you want to see first.

## 7 · What it costs

- **Vercel:** the free plan is enough. It is meant for personal, non-commercial use; if Haqdaar
  becomes a paid service, that needs the paid plan.
- **The small store** for the engine's address: free tier.
- **Twilio:** each "call my phone" uses call minutes, as a call does today.
- **Muse, Sarvam, Groq:** the dashboard itself spends nothing. A real call uses speech-to-text
  as it does today.

## 8 · Choices only you can make

Each has the default I would pick. "Go with the defaults" is a full answer.

1. **Who is "the guy who is going to use it"?** Default: you run it; one other person can look
   but not change anything.
2. **May caller words be copied to the cloud** so history shows while the laptop is off?
   Default: no.
3. **May keys be replaced from the website?** Default: not at first. Show status and Test in
   D7, and add Replace only when you say so.
4. **How the dashboard finds the engine.** Default: the check-in. Other way: a fixed address,
   if you own a web domain.
5. **Where the engine runs in the end.** This is the same open choice as in `OWNER-END-TODO.md`
   (server location). The dashboard works with either; on a laptop it is offline when the lid
   is shut.

## 9 · Where the ideas came from

- Your own earlier dashboard for the TSS voice agent: a call button, call history, a live
  transcript, a timing chart, a password login, and a relay to a backend. This plan keeps that
  shape and adds a sidebar and the rest of the pages.
- Voice-agent products (Retell, Vapi and tools built on them): call history with filters, a
  page per call with transcript and reply times, cost per call, pass and fail counts.
- Dashboard practice: a few key numbers on top, a list of what needs attention, then tables;
  the sidebar never moves; a click on a row opens the detail.

## 10 · What this plan does not include

- Running the call engine on Vercel.
- Calls from the public. The line is not open.
- The Indian provider (step 5.4, dropped for now).
- Calling from the browser with a microphone. It is a good later idea for people with no
  phone, and it is a real project of its own.
