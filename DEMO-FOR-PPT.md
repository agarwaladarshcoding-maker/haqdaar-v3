# HAQDAAR — what the demo shows (for the PPT team)

Use this to write the slides and captions and to cut the video. Everything here is true for the
demo as it runs today (15 Sep). Where a number is needed that we do not have, it says **[fill]**.

---

## 1 · The idea in one line

**Call a number, talk in Hindi or English, and find out which government schemes are for you,
and how to apply. No app, no internet, no reading.**

HAQDAAR ("the one who has a right to it") works over a normal phone call.

## 2 · The problem (slide 1–2)

- There are hundreds of government schemes, but people often don't know which ones they can get.
- The information is on websites and in forms, which is hard for someone who can't read well,
  has no smartphone, or has no internet.
- A phone call works for everyone, on any phone.

Numbers to add from a real source: how many schemes exist, how many people have a basic phone but no smartphone,
how much scheme money goes unclaimed. **[fill, with source]**. Please don't make these up.

## 3 · What happens in the demo call (slide 3, and the video)

The phone rings. A voice speaks. The caller answers by **pressing a button or speaking**.

| Step | The caller hears | The caller does |
|---|---|---|
| 1 | "Namaste, welcome to HAQDAAR. For Hindi press 1, for English press 2." | Presses 1 |
| 2 | "To hear anything again slowly, press 9 at any time." | — |
| 3 | "What do you need help with? Farming 1, pension 2, health 3, jobs 4." | Presses a button, or says "पेंशन" |
| 4 | If they spoke: "You chose pension. If that is right press 1, if not press 2." | Presses 1 |
| 5 | Two short questions, e.g. "Is your age between 18 and 40?" "Do you have a savings account?" | 1 = yes, 2 = no, **3 = I don't know** |
| 6 | The scheme that fits, with the key facts from the government website | Listens (9 = repeat slowly) |
| 7 | "Shall I tell you how to apply?" | 1 → step-by-step how to apply |
| 8 | "Anything else?" | 1 → back to the menu, 2 → goodbye |

A full call takes about 2–3 minutes.

## 4 · The 4 areas and 7 real schemes (slide 4)

All facts are taken from the official scheme pages on **myscheme.gov.in**.

| Area | Questions it asks | Schemes it can tell you about |
|---|---|---|
| Farming | Land in your name? Need a loan? | PM-KISAN (₹6,000 a year), Kisan Credit Card (farm loan), PM Fasal Bima Yojana (crop insurance) |
| Pension | Age 18–40? Savings account? | Atal Pension Yojana (₹1,000–₹5,000 a month after 60) |
| Health | SC/ST, or landless daily-wage family? | Ayushman Bharat PM-JAY (₹5 lakh cashless treatment a year) |
| Jobs | Own business, or apprenticeship? | PMEGP (up to 35% subsidy on the loan), NAPS (stipend while you learn) |

The answers change the result. For example, if the land is not in your name, PM-KISAN is not offered,
but crop insurance still is. If you are over 40, it says honestly that there is no pension scheme for you.

## 5 · What makes it good (slide 5: one line each)

1. **Works on any phone.** A normal call, with no app and no internet.
2. **Speak or press.** Buttons for choices; speaking works too.
3. **It checks what it heard.** Anything taken from your voice is read back: "You chose pension, right? Press 1."
   It never goes the wrong way silently.
4. **Repeat slowly.** Press 9 at any time and it says the last thing again, slower.
5. **"I don't know" is an answer.** Press 3. It does not force a yes or no. It explains, for example
   "Your date of birth is on your Aadhaar card", and carries on.
6. **Honest.** It says when a scheme is not for you, and says "the final decision is from the government list" where that is true.
7. **Tells you how to apply,** not just the name of the scheme.
8. **Hindi and English.**

## 6 · How it works, simply (slide 6: a simple picture)

```
Caller's phone ──call──▶ Phone network (Twilio) ──live audio──▶ HAQDAAR server
                                                                  │
                     buttons ────────────────────────────────────▶│ picks the next question
                     voice ──▶ speech-to-text (Sarvam / Whisper) ─▶│
                                                                  │
Caller hears  ◀── voice lines (Sarvam Hindi/English voice) ◀──────┘
Scheme facts: myscheme.gov.in pages, saved and checked before the call
```

## 7 · Video notes

- **Show:** the phone ringing, the caller on speaker, and the server window where each line appears
  (`BOT` = what it says, `CALLER` = what it heard or the key pressed). Seeing both side by side works well.
- **Good 2-minute take:** Hindi (1) → pension, spoken "पेंशन", then 1 to confirm → age: **3** (don't know) →
  account: **1** → scheme facts → press **9** once to show the slow repeat → apply: **1** → anything else: **2**.
- **Second take (farming):** farming (1) → land: **2** → loan: **1** → it offers Kisan Credit Card and crop insurance →
  pick one → how to apply.
- **Captions to use:** "Speak or press a button", "It reads back what it heard", "Press 9: repeat slowly",
  "Press 3: I don't know", "Facts from myscheme.gov.in".
- **Voice:** some lines use a second voice (the laptop voice) until our voice-service credits are topped up.
  Record the final video after the top-up, so the whole call is one voice.

## 8 · Say honestly (if someone asks, or for a "limits / next steps" slide)

- The demo covers **4 areas and 7 schemes** with fixed questions. The full engine has 12 schemes and picks
  questions by itself, but it's keypad only for now.
- Speech over a phone line mishears short words, which is why every spoken answer is confirmed with a button.
- Hindi and English today. More languages (Marathi first) come next.
- Next steps **[fill with the team's plan]**: more schemes, more languages, a real number people can call.
