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

## The call (about 2–3 min). What to say

The script is fixed: whatever you say about your need, it goes to farming. Answers you give
to the yes/no questions **do** change the result.

| Bot says | You say (or key) | What to tell the room |
|---|---|---|
| Namaste… Hindi or English? | "Hindi" / "English" (or 1 / 2) | "No app, no reading. Just talk." |
| What do you need help with? | "मुझे खेती के लिए मदद चाहिए" / "Help with farming" | |
| Two short questions. Is the land in your name? | "हाँ" / "Yes" (1 = yes, 2 = no) | "It asks follow-up questions to narrow down." |
| Do you need a loan? | "हाँ" / "Yes" | |
| I found **3** schemes: PM-KISAN, Kisan Credit Card, Fasal Bima | — | "Yes + yes = 3 schemes. Say no to land and PM-KISAN drops out." |
| Which one? | "फसल बीमा" / "Kisan Credit Card" / "the first one" | |
| Details (from the official site) | — | "Every fact is from the government page." |
| Shall I tell you how to apply? | "हाँ" | |
| Another scheme? | "नहीं" / "No" | |
| Thank you… goodbye. Call ends. | | |

Results by answer: land yes + loan yes → 3 schemes; land yes + loan no → PM-KISAN + Fasal Bima;
land no + loan yes → KCC + Fasal Bima; land no + loan no → Fasal Bima only.

If it does not catch what you said, it says "sorry, say again", then goes with the script's answer.
Keys always work: 1 = yes / Hindi, 2 = no / English. You can press a key while it is talking.

## If something goes wrong

| Problem | Fix |
|---|---|
| `cloudflared failed 3 times; using ngrok` | Run `ngrok http --url=<shown address> 8000` in a second window, then `make call`. |
| Phone never rings | Check the window for `RINGING`. Then `make calls` shows what Twilio did with the call. |
| Rings, then "application error" | Tunnel died. Ctrl+C, `make run-demo` again. |
| It never hears you | Speak after it stops talking. Use keys (1 yes, 2 no). |
| Internet dead | **Backup:** `make demo SPEAK=1`, the old keypad call in the terminal with the laptop voice. |

## Say honestly if asked

- The conversation is **scripted for the demo**: 3 farmer schemes, always the farming path. The follow-up
  answers are real branches. The full engine (12 schemes, any path) exists, but is keypad only (`make demo-run`).
- Voice: Sarvam. The lines are made in advance, not live.
- Hearing: Groq Whisper tonight, because the Sarvam credits ran out. Sarvam hearing comes back once credits are topped up (it switches by itself).
- Hindi and English only. Marathi comes later.
