# HAQDAAR — demo script (15 Sep)

A person gets a phone call, **talks** in Hindi or English, answers two follow-up questions,
and hears which real government schemes fit them. The facts come from myscheme.gov.in.

## Start the demo (one command)

```bash
cd ~/Documents/haqdaar-v2 && git checkout demo-15sep
make run-demo
```

It does everything itself: tunnel, server, voice. Then **your phone rings** (CALL_ME_NUMBER in .env).
Wait for `RINGING +91…xxxx now`, pick up, and put it on speaker. Leave the window open: it shows
every line the bot says (`BOT`) and what it heard (`CALLER said: "…"`).

- Ring again after a call: `make call` (the server stays up). Or Ctrl+C and `make run-demo` again.
- Another number: `make run-demo TO=+91XXXXXXXXXX`. Start without ringing: `make run-demo NOCALL=1`.

## The call (about 2–3 min)

**Buttons choose the type of help** (small menu for now). You can also speak: anything it takes
from your voice is read back — "आपने पेंशन चुनी। सही है तो 1 दबाइए, नहीं तो 2।" — so it never
goes the wrong way silently. Yes/no questions: 1 = yes, 2 = no, or say हाँ / नहीं (it confirms).
**3 = I don't know** on the questions about the caller (land, loan, age, account, family). **9 = say that again slowly**,
at any time (or say "दोबारा"). A key pressed during a "sorry" line counts as the answer.

| Bot says | Press / say | What to tell the room |
|---|---|---|
| Namaste… Hindi or English? | 1 Hindi / 2 English (or say it) | "No app, no reading. Just a phone." |
| What do you need? 1 farming, 2 pension, 3 health, 4 jobs | a key, or say "पेंशन" → it confirms, press 1 | "Buttons for the main choice; voice is checked back." |
| (any line) | **9** | "Too fast? Press 9, it repeats slowly." |
| **Farming:** land in your name? loan needed? | 1 / 2 each | "Follow-up questions narrow it down." |
| → 1 to 3 schemes, then "which one? 1 / 2 / 3" | a key or the name | "Say no to land, and PM-KISAN drops out." |
| **Pension:** age 18–40? savings account? | 1 / 2 / **3 don't know** | "Over 40 → it says honestly there is no scheme for you." |
| **Health:** SC/ST or landless daily-wage family? | 1 / 2 | Ayushman Bharat, ₹5 lakh cashless |
| **Jobs:** 1 own business, 2 apprenticeship | 1 / 2 | PMEGP subsidy or NAPS stipend |
| Details (from the official site), then "how to apply?" | 1 | "Every fact is from the government page." |
| Anything else? | 1 → back to the menu, 2 → goodbye | Show a second path |

Results for farming: land yes + loan yes → 3 schemes; yes + no → PM-KISAN + Fasal Bima;
no + yes → KCC + Fasal Bima; no + no → Fasal Bima only.

Good 3-minute run: **1** (Hindi) → **1** farming → **1**, **1** → pick **3** by saying "फसल बीमा" and press 1 →
**1** how to apply → **1** anything else → say "पेंशन", press 1 → age **3** (don't know) → account **1** →
press **9** during the scheme facts (slow repeat) → **2** → **2** goodbye.

Slides and video: see `DEMO-FOR-PPT.md`.

If nobody answers the main menu 3 times, it says goodbye. It never picks the type of help on its own.

## If something goes wrong

| Problem | Fix |
|---|---|
| `cloudflared failed 3 times; using ngrok` | Run `ngrok http --url=<shown address> 8000` in a second window, then `make call`. |
| Phone never rings | Check the window for `RINGING`. Then `make calls` shows what Twilio did with the call. |
| Rings, then "application error" | Tunnel died. Ctrl+C, `make run-demo` again. |
| It never hears you | Speak after it stops talking. Use keys (1 yes, 2 no). |
| Internet dead | **Backup:** `make demo SPEAK=1`, the old keypad call in the terminal with the laptop voice. |

## Say honestly if asked

- The conversation is **scripted for the demo**: 4 kinds of help, 7 real schemes, fixed follow-up questions.
  The full engine (12 schemes, any path) exists, but is keypad only (`make demo-run`).
- Voice: Sarvam, made in advance. **Right now 86 of 111 lines use the Mac voice** because the Sarvam credits
  ran out. Top up Sarvam and restart `make run-demo`: it makes the missing lines in Sarvam by itself
  (the window stops saying `VOICE MIXED`).
- Hearing: Groq Whisper tonight (Sarvam credits). Short single words are hard over a phone line, which is why
  every voice answer is read back for a 1/2 confirm.
- Hindi and English only.
