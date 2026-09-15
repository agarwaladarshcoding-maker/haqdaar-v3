# HAQDAAR — demo script (15 Sep)

A person calls a phone number, presses keys, and hears which government schemes fit them.
The schemes are 12 real ones from myscheme.gov.in. Every fact comes from the official page.

## Before the demo (5 min)

```bash
cd ~/Documents/haqdaar-v2 && git checkout demo-15sep
make test                      # expect: 109 passed
make demo KEYS=3,1,0,2         # quick check: prints a whole call, ends "Goodbye"
caffeinate -dimsu make demo-run   # tunnel + number -> demo server. Leave this window open.
```

Wait for the line `voice ready: 146 lines, 0 failed` (about 1 min the first time, a few seconds after that).
Then dial the number yourself once as a test run. Use speakerphone so the room can hear.

## The call (about 2 min). Keys to press:

| Press | You hear | What to say to the room |
|---|---|---|
| — | Welcome, pick a language | "Works on any phone. No app, no internet, no reading." |
| **3** (English) or **1** (Hindi) | Privacy notice, then "What do you need help with?" + 7 choices | "The choices come straight from the scheme data." |
| **1** farming | "Good news" + Kisan Credit Card, PM-KISAN, Fasal Bima, SMAM, each with a one-line summary | "It narrowed 12 schemes to the 4 that fit." |
| **1** benefits | "According to the official myScheme website…" | "Every fact is quoted from the government page." |
| **2** how to apply | Steps to apply | |
| **0** finish | "Anything else? 1 yes, 2 no" | |
| **2** | "Thank you for calling Haqdaar. Goodbye." Call ends. | |

Other good choices: **6** pension (Atal Pension Yojana), **3** health (Ayushman Bharat), **5** jobs (3 schemes).
You can press a key while it is talking: it stops and moves on.

The server window shows each line as it happens (`SAY …`, `dtmf 1`). You can show it on the screen.

## If something goes wrong

| Problem | Fix |
|---|---|
| Call rings but no voice / "application error" | The tunnel changed. Stop `make demo-run` (Ctrl+C) and run it again; it points the number at the new tunnel. |
| Cannot dial in | `make call` (the server rings your phone). |
| Phone or internet dead | **Backup:** `make demo SPEAK=1`. Same call in the terminal, spoken by the laptop. You type the keys. |
| Silent for a long time | It waits 12 s for a key, then asks "Are you still there?". After 3 waits it says goodbye and hangs up. |

## What to say honestly if asked

- Keypad only today. Speech understanding comes next (Steps 13–16).
- The voice is the laptop's built-in voice, used for the demo. The real voice (Sarvam, Indian languages) is Step 10.
- Marathi uses the Hindi voice for now.
- 12 schemes today. The pipeline that fetched them works for more.
