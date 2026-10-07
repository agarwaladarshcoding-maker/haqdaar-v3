# Cost analysis for the deck: slide content and the plan to get government to adopt it

Date: 6 Oct 2026. Companion to COST-MODEL.md (all numbers come from there; tags [M] measured, [L] list price,
[E] estimate). Each block below is one slide: the line to put on it, the numbers, and what to say.
"Current solution" means what the government runs today for a farmer who needs help.

---

## Slide 1 — The problem in one number

**On the slide:** A farmer's question costs the state about **₹88** to answer well, and only if the farmer can
reach a person. Haqdaar answers it for about **₹18**, from any phone, in 11 languages.

- ₹88.5 = call ₹28.5 + look at the photo ₹50 + SMS ₹5 + voice note ₹15 [E; the call figure is staffing math,
  the rest are estimates]. 80% cheaper.
- **Say:** "We could not find a published cost per call for the government's own lines, so this is what the same
  work costs a desk of paid people. Show us the real figure and we will redo it."

## Slide 2 — What exists today, and where it stops

| | Kisan Call Centre 1551 | PM-Kisan helpline 155261 + Kisan e-Mitra | CSC (about 5 lakh centres) | **Haqdaar** |
|---|---|---|---|---|
| How the farmer reaches it | phone | app / portal, smartphone and data | walk to the centre | **any phone, keypad too** |
| Who answers | live agent (144 in an older source, 525 seats in the 2023 tender) | chatbot, PM-Kisan questions only (49 kinds) | the centre's operator | **AI, a person checks the doubtful ones** |
| Languages | local dialects, by agent | 11 | by operator | **11** |
| Photo of a sick crop | not found | not found | operator looks | **read by model if confidence low, also checked by a person** |
| Calls at once | about the seats | any | one person at a time | **set by money, not people** |
| Cost per case, published | not found | not found | commission, not a cost | **₹17.6, open** |

Sources: [KCC](https://sameti.assam.gov.in/sites/default/files/swf_utility_folder/departments/sameti_medhassu_in_oid_8/menu/information_and_services/KCC.pdf),
[Kisan e-Mitra](https://apolitical.co/en/navigator/case-studies/kisan-e-mitra-indias-voice-enabled-ai-support-for-farmers),
[CSC count](https://indiaobservers.com/digital-india-cscs-rural-services-expansion/).
Cells marked "not found" mean I did not find it on the web, not that it does not exist. Check with the department before showing them.



## Slide 3 — Price side by side (per case)

| | Per call only (no photo, no SMS) | Whole case (call + photo + SMS + voice) |
|---|---|---|
| Person at a desk | ₹28.5 [E] | ₹88.5 [E] |
| **Haqdaar, today's plan** | **₹16.3** (43% cheaper) | **₹17.6** (80% cheaper) |
| **Haqdaar, lean plan** | **₹7.3** (74% cheaper) | **₹8.6** (90% cheaper) |

Lean plan = the model speaks the language itself (no translate step) and the cheaper v2 voice. Not tested yet.
- **Say:** "On the plain call the saving is moderate. The big saving is the photo, the written advice and the voice
  note, which a desk does by hand."

## Slide 4 — Where the ₹17.6 goes (pie or bar)

Voice out 46% (₹8.15) · Translate 26% (₹4.66) · Phone line 13% (₹2.25) · Speech to text 4% · Groq 3% · Audio message 3% ·
SMS 2% · Human check 2% · Servers and databases **0.2%** (₹0.04).

- **Say:** "Servers are not the cost. Three vendor lines are 85% of it, and each can be swapped or bought in bulk."

## Slide 5 — The 11 languages (table or map)

Use the table in COST-MODEL.md §3: Hindi 17.7, Bengali 17.1, Marathi 17.3, Telugu 18.0, Tamil 19.8, Gujarati 16.9,
Kannada 18.5, Odia 17.7, Malayalam 19.3, Punjabi 18.0, English 11.8.
- Spread is 17% (Tamil dearest, Gujarati cheapest) because scripts need different numbers of letters [M, 8 sentences]
  and Indian scripts use more SMS parts [L].
- **Say:** "Adding a language adds no new cost line, it moves the price by a few rupees."

## Slide 6 — Back-end bill (servers, databases, small costs)

At the stress size of 1,000 calls a second: servers ₹4.7 Cr + database ₹0.7 Cr + second site ₹2.7 Cr + data out ₹0.4 Cr +
storage ₹0.05 Cr + small costs ₹1.3 Cr + run team ₹0.6 Cr = **₹10.5 Cr a month** [E sizing]. For a district pilot
(300 calls a day) it is under ₹0.5 lakh a month.
- The scheme and language data is small (under 100 MB) and sits on every server; databases keep only case records,
  the review queue and labels. Photos are wiped when answered; no call audio and no phone numbers are stored.

## Slide 7 — What it saves, by size

| Calls a day | Haqdaar a year | Person a year | Saving a year |
|---|---|---|---|
| 300 (one district pilot) | ₹0.2 Cr | ₹1.0 Cr | ₹0.8 Cr |
| 1 lakh (one big state) | ₹64 Cr | ₹323 Cr | **₹259 Cr** |
| 10 lakh | ₹643 Cr | ₹3,230 Cr | **₹2,590 Cr** |

Use the 1 lakh row as the headline. The 1,000-a-second case (₹2.2 lakh Cr a year saved) is a stress test,
not a forecast: do not put it on the main slide.

## Slide 8 — What is proven and what is not (put this on the deck, it builds trust)

- **Proven on our line:** speech in and out in Hindi, Marathi, English; SMS delivered; photo read by a model;
  an operator desk that approves answers; 3,300+ automated tests pass.
- **Not yet:** real farmers calling; the other 8 languages on a live call; the keypad-SMS photo on a real phone;
  more than one caller at a time; any call to the telecom carrier on a paid account.
- **Say:** "That is why we ask for a pilot, not a national contract."

---

# How to get government to say yes and carry it on

## What they will worry about, and the answer

| They ask | Our answer |
|---|---|
| "Who owns the data? Is it in India?" | Cloud in Mumbai; no audio, no phone numbers kept; photos wiped on answer; only written labels kept. **Gap:** the talk model today runs at Groq (outside India). Its line is 3% of the cost, so move it to an in-India model (Sarvam or IndiaAI compute) before any government pilot. |
| "Are we locked in to a company?" | Every engine is swappable: speech, translate, voice, model. Government's own **Bhashini** can replace Sarvam for speech, translate and voice (76% of our cost). Bhashini's free use is [for proof of concept only, and production is by quote](https://www.cdomagazine.tech/aiml/indian-govt-ai-translation-platform-bhashini-gears-up-for-monetization), so ask them for the production rate. |
| "What if it gives wrong advice?" | A dose guard removes dose sentences; a person checks the doubtful photo answers; the caller can press 6 to reach the keys, and the human KCC stays as the fallback. |
| "Who is accountable?" | One price per resolved call, a monthly cap, a report of every call type and how often a person overruled the model (`tools/review_counts.py`). |
| "Will it replace our staff?" | No: it takes the overflow, the night hours and the photo work, and gives KCC agents the hard cases with the photo and the first-call words already attached. |

## The steps

**Step 0 — be able to sell to them (weeks 0–4, near zero cost).**
Get DPIIT startup recognition and register on GeM: recognised startups can be [exempt from prior-experience, turnover and
earnest-money rules](https://www.startupindia.gov.in/content/sih/en/reources/startup_india_notes/regulations_and_policies/MakeTheGovernmentYourPrimeCustomer.html)
(only if the tender says so), and can take a trial order. Move the model to an in-India host. Fix the numbers marked [E] by
getting three quotes: phone line, Groq or the in-India model, Sarvam enterprise.

**Step 1 — one district, 60 days, paid (months 1–3).**
- Offer: 300 calls a day, 2 languages (the district's language + Hindi), photo by link and by SMS, a person checks
  80% of photos. Government pays about **₹25 a call** (about ₹2.3 lakh a month); a desk would cost about ₹8 lakh for the same calls.
  My cost for it is about ₹2.2 lakh a month (₹20 a call with heavy review + ₹0.4 lakh for servers) [E].
- Where: a Krishi Vigyan Kendra or the state agriculture department's extension wing; they have the farmers and the
  authority to run a trial. Ask the KCC for their call-type counts so we show we answer the same questions.
- Success is agreed **before** we start, in writing: share of calls that reach an answer, how often a person
  overruled the model, farmer satisfaction on a call-back, cost per resolved call.

**Step 2 — the state (months 4–9).** Take the pilot's numbers to the state Agriculture Secretary. Ask for: the 1551 overflow
number, the other 3–4 languages of the state, 20,000–50,000 calls a day. Price falls to about ₹22 a call as we sign
a bulk deal with the vendors.

**Step 3 — plug into the national stack (months 9–18).** The Budget 2026-27 proposed
[Bharat-VISTAAR](https://ianslive.in/ai-booster-763-crore-farmer-ids-created-235-crore-crop-plots-surveyed--20260214111354),
a local-language AI advisory on AgriStack, under the about ₹2,820 Cr Digital Agriculture Mission (₹28.2 billion). Our fit: **the phone and keypad
front door** to it, for farmers who will never open an app. Ask the Digital Agriculture Mission / NIC team to list us as a channel and read
the Farmer ID (with consent) so an answer can use the farmer's own plot and crop. Also open talks with IndiaAI's
application-development and start-up financing programme and Bhashini for production rates.

**Step 4 — "carry it forward": make it hard to drop.**
- Hand over **a report each month**: calls by language, by scheme, cost per resolved call, savings against the desk.
- Offer the agency a **price cap** and a **cost-sharing clause** (we pass on vendor price falls).
- Give them a copy of the scheme data and the review labels (they are the government's own advice), and a written
  exit plan: they can run the same system on their own cloud.
- A named champion inside the department, not a vendor: one joint secretary or district officer who reports the
  pilot results upward.

## What to ask for on the last slide

1. A 60-day, one-district trial order (₹2–3 lakh a month), run with a KVK or the state agriculture department.
2. The call-type counts and the published cost per seat from KCC, to put real numbers beside ours.
3. An introduction to the Digital Agriculture Mission / Bharat-VISTAAR team and to Bhashini for a production rate.

## Checks I could not make

- No government cost per call for KCC or PM-Kisan was found. The ₹88.5 is a desk estimate.
- "Not found" in the Slide 2 table means my web search did not find it.
- GeM trial-order limits and the exact startup exemptions change by tender: read the tender before relying on them.
- Bharat-VISTAAR is described as **proposed** in the source I found; confirm its status.
