# Haqdaar — full cost analysis (one file for the slide team)

Date: 6 Oct 2026. Replaces COST-MODEL.md and COST-SLIDES.md (same numbers, now in one place, plus the
"upgrade what government already has" comparison, the profit plan and the scheme-freshness cost).
Status: pilot-stage product. **Every number carries a tag:**
**[M]** measured on our own line or code · **[L]** list price from a vendor page (links in §14) ·
**[E]** my estimate, to be settled by a quote or a test. Money is in rupees; Rs 90 to the dollar [E]; 1 Cr = 1 crore = 10 million.

**How the slide team should use this:** §1 is the story in 10 lines. §13 says which table becomes which
slide and what chart to draw. Do not change a number without changing its tag. Anything tagged [E] should
carry a small "estimate" mark on the slide.

---

## 1. The story in ten lines

1. A farmer who needs help today meets a desk of paid people (Kisan Call Centre 1551), a chatbot that needs a
   smartphone (Kisan e-Mitra), or a walk to a CSC. A full answer by a desk costs about **₹88** (call + photo + SMS + voice note) [E].
2. Haqdaar answers the same case for about **₹17.6** now, **₹8.6** on the lean plan: from any phone, in 11 languages.
3. Three vendor lines are 85% of that cost (voice out, translate, phone line). Servers are 0.2%.
4. The 11 languages cost ₹16.9 to ₹19.8 a call (English ₹11.8). Language is not the risk.
5. Government has three ways to get this: keep the desk, **upgrade its own system** (add AI to the desk, or build a voice stack
   on its open-source VoicERA), or **buy it from us as a service**.
6. Over 3 years at 1 lakh calls a day: desk ₹969 Cr · AI-assisted desk ₹580 Cr · build its own AI line ₹235 Cr + 12–18 months
   to start · **buy from us ₹241 Cr, live in months**.
7. So on price alone, buying from us is **about equal** to building the same thing; it wins on speed, no big
   upfront spend, and **schemes kept up to date by us**. Our profit comes from running, not from marking up speech.
8. At ₹22 a call we make about **₹11 Cr a year net at 1 lakh calls a day** (14%), ₹17 Cr with vendor discounts (22%),
   ₹44 Cr on the lean plan (55%). Break-even is about 31,000 calls a day.
9. A pilot loses about ₹1 Cr a year. It is the price of getting the first government customer.
10. Ask: a 60-day one-district trial order, KCC's real cost and call counts, an introduction to the Digital Agriculture Mission and Bhashini.

---

## 2. The case that is priced

- Calls: 5 minutes each. Stress size is **1,000 calls a second** (300,000 on the line at once, 86.4 million a day).
  Realistic sizes for a government are 300 a day (a district), 1 lakh a day (a big state), 10 lakh a day.
- 11 languages (Sarvam's 11): Hindi, Bengali, Marathi, Telugu, Tamil, Gujarati, Kannada, Odia, Malayalam, Punjabi, English.
  Every call goes through English in the middle: speech in → English → model → English answer → caller's language → speech out.
- One photo per call. An SMS and an audio message go back on every second call.
- Business plans: Groq, Sarvam, a carrier line and a cloud account are on business or enterprise terms. Only Sarvam
  and cloud list prices are public; Groq and Sarvam enterprise prices are by quote, so list price is a ceiling.

## 3. Unit prices used

| Item | Price | Tag | Source |
|---|---|---|---|
| Speech to text | ₹30 an hour of audio | L | Sarvam |
| Translate | ₹20 per 10,000 letters | L | Sarvam |
| Voice out, Bulbul v3 / v2 | ₹30 / ₹15 per 10,000 letters | L | Sarvam |
| Talk model, gpt-oss-120b | $0.15 in, $0.075 cached in, $0.75 out per 1M tokens | L | Groq (enterprise: by quote) |
| Phone line | ₹0.45 a minute (cloud toll-free ₹0.80–1.50; carrier SIP 60–80% less) | E | no rate card |
| SMS | ₹0.12 a part (range ₹0.12–0.30). Indian scripts: 70 letters = 1 part, 134 = 2, 201 = 3 | L | Exotel |
| Photo read (Muse) | ₹0.006 a read (5.3 s, 405 in + 145 out tokens) | M | our line |
| Server c7i.xlarge Mumbai | $0.1785 an hour | L | doit.com |
| Database (RDS Postgres) | $165 a month for 2 cores, scaled by cores | L | bytebase |
| Storage S3 / infrequent | ₹2.1 / ₹1.15 a GB-month; data out about ₹8.5 a GB | L | AWS |
| Person at a desk | ₹24,000 a month loaded | E | KCC advisers start near ₹25,000 (a recruitment notice) |

## 4. One call, line by line (weighted over the 11 languages)

| Line | How it is counted | ₹ a call | Share |
|---|---|---|---|
| Voice out | 40 reply sentences [M] × 60 letters [E] = 2,400 English letters, grown to the script length (§5) | 8.15 | 46% |
| Translate to the caller's language | the same 2,400 letters; English callers skip it | 4.66 | 26% |
| Phone line | 5 min × ₹0.45 | 2.25 | 13% |
| Speech to text | 80 s of caller speech [E] | 0.67 | 4% |
| Groq talk model | ~30,000 tokens in + 2,000 out (10 turns of ~3,000) [M]; half cached [E] | 0.55 | 3% |
| Audio message | half the calls × 350 letters spoken | 0.59 | 3% |
| Human check of the photo | 10% of photos [E] × ₹3.4 a case (₹24,000 ÷ 177 h ÷ 40 cases an hour) [E] | 0.34 | 2% |
| SMS | photo link on every call + summary on half | 0.37 | 2% |
| Photo read | one read | 0.006 | 0% |
| Servers, databases, small costs (§7) | monthly bill ÷ calls | 0.04 | 0.2% |
| **Total** | | **17.62** | |

Call only (no photo, no SMS, no audio, no check): **₹16.3**.

## 5. By language

What changes per language: (a) letters for the same sentence [M, 8 sentences through Sarvam translate, 6 Oct 2026]:
Hindi 1.12×, Bengali 1.05×, Marathi 1.07×, Telugu 1.16×, Tamil 1.37×, Gujarati 1.02×, Kannada 1.22×, Odia 1.12×,
Malayalam 1.33×, Punjabi 1.16× the English letters; (b) SMS parts: a 100-letter link text is 1 part in English, 2 in Hindi, 3 in Tamil;
(c) English skips translate. The phone line, speech to text, Groq and photo read cost the same in every language.
Share of calls = Census 2011 mother-tongue counts scaled to 97%; English 3% [E]. Hindi's count includes Bhojpuri, Rajasthani and others, so its share is a ceiling.

| Language | Share of calls | Script vs English | ₹ a call | ₹ Cr a day at 1,000/s | Desk ₹ | Saving a call ₹ |
|---|---|---|---|---|---|---|
| Hindi | 48.2% | 1.12× | 17.65 | 73.5 | 88.5 | 70.9 |
| Bengali | 8.9% | 1.05× | 17.14 | 13.1 | 88.5 | 71.4 |
| Marathi | 7.6% | 1.07× | 17.29 | 11.3 | 88.5 | 71.2 |
| Telugu | 7.4% | 1.16× | 17.96 | 11.5 | 88.5 | 70.5 |
| Tamil | 6.3% | 1.37× | 19.81 | 10.8 | 88.5 | 68.7 |
| Gujarati | 5.1% | 1.02× | 16.90 | 7.4 | 88.5 | 71.6 |
| Kannada | 4.0% | 1.22× | 18.45 | 6.4 | 88.5 | 70.0 |
| Odia | 3.4% | 1.12× | 17.67 | 5.2 | 88.5 | 70.8 |
| Malayalam | 3.2% | 1.33× | 19.33 | 5.3 | 88.5 | 69.2 |
| Punjabi | 3.0% | 1.16× | 17.99 | 4.7 | 88.5 | 70.5 |
| English | 3.0% | 1.00× | 11.76 | 3.0 | 88.5 | 76.7 |
| **All 11** | 100% | | **17.62** | **152.2** | 88.5 | 70.9 |

Spread: 17% (Tamil dearest, Gujarati cheapest among Indian languages). Adding a language adds no new cost line.

## 6. What moves the price (all 11 languages)

| Change | ₹ a call |
|---|---|
| Base | 17.62 |
| Bulbul v2 voice in place of v3 | 13.2 |
| Phone line ₹0.25 / ₹1.00 a minute | 16.6 / 20.4 |
| Human check of 20% / 80% of photos | 18.0 / 20.0 |
| SMS ₹0.30 a part | 18.1 |
| Groq ₹1.00 a call (twice my figure) | 18.0 |
| Vendor volume discount 10% (1 lakh a day) / 20% (10 lakh a day) [E] | 15.9 / 14.1 |
| **Lean plan: model speaks the language itself (no translate) + v2 voice** | **8.6** |
| Lean plan, call only | 7.3 |

The lean plan needs a model that answers well in Hindi and Marathi directly and a v2 voice villagers accept. Not tested yet.
Speech, translate and voice are 76% of cost, so **a government rate from Bhashini** (not published; production is by quote)
would move the price more than anything else.

## 7. Servers, databases and small costs

Sizing is my estimate [E]: today our server takes **one caller at a time**; calls per box are not measured.

At 1,000 calls a second:

| Item | Sizing | ₹ Cr a month |
|---|---|---|
| App servers | 300,000 ÷ 150 a box × 1.25 = 2,500 × c7i.xlarge on demand | 2.93 |
| Phone-media / SIP boxes | 300,000 ÷ 500 × 1.25 = 750 × c7i.2xlarge | 1.76 |
| Database (cases, review queue, labels) | 10 shards × 48 cores, two zones | 0.71 |
| Second site, warm | half of the three lines above | 2.70 |
| Storage | call log ~15 KB a call [M], 12 months kept | 0.05 |
| Data out | audio links, photo page, ~0.2 MB a call | 0.44 |
| Small costs: load balancers, cache, monitoring, backups, security, cloud support | 15% [E] | 1.29 |
| Run team | 40 people × ₹1.5 lakh | 0.60 |
| **Total** | = ₹0.04 a call | **10.5** |

At pilot size (300 calls a day) the whole back end is under ₹0.5 lakh a month. A 1-year server commit typically saves 30–40% [E].
The scheme and language data is small (under 100 MB: snapshot 0.4 MB, search index 5.5 MB, audio pool 65 MB) and is copied
onto every server; databases hold only case records, the review queue and labels. Photos are wiped once answered; no call audio and no
phone numbers are kept [M, by design]. If the agency wants calls recorded (~0.3 MB at 8 kbps [E]), it adds about ₹1 Cr for a year kept at 1,000/s.
Small costs not in the total: SMS sender and template registration (DLT, ~₹5,000 once), a load test, a security audit, spare vendor accounts.

## 8. What government has today, and what each upgrade costs

### 8.1 What exists
| | KCC 1551 | PM-Kisan 155261 + Kisan e-Mitra | CSC (~5 lakh centres) | VoicERA on Bhashini |
|---|---|---|---|---|
| Reach | any phone | smartphone + data | walk to centre | a toolkit, not a service |
| Answered by | live agents: 144 (older source), 525 seats (2023 tender) | chatbot; 11 languages; PM-Kisan questions only (49 kinds) | operator | open-source voice AI stack (speech, voice, chat, telephony), unveiled 19 Feb 2026 |
| Photo of crop | not found | not found | operator looks | not stated |
| Cost per case | not found | not found | commission | open source; Bhashini production use is by quote |
Sources: §14. "Not found" means my web search did not find it, not that it does not exist. Check with the department.

### 8.2 The three ways to move forward (per resolved case, whole case)
| Option | What it is | ₹ a case (running) | One-time | Time to first call |
|---|---|---|---|---|
| **A. Keep the desk** | people only | **88.5** [E] | 0 | now |
| **B1. Upgrade the desk with AI tools** | agents get translate, photo pre-read, auto SMS and voice note; handle time −25%, photo look −50% [E] | **52.4** [E] | ₹6 Cr build [E] | 6–9 months |
| **B2. Build its own AI voice line** (VoicERA / Bhashini + an integrator) | same stack as ours | **17.6** variable + ₹8.1 Cr a year to run (30 staff ₹5.4 Cr + integrator support ₹2.7 Cr) [E] | ₹18 Cr build [E] | 12–18 months (tender + build) |
| **C. Buy Haqdaar as a service** | we run it, keep schemes updated, take the review desk | **22** (price, §10) | 0 | 2–3 months |

B2 build basis [E]: 25 people × 18 months × ₹1.5 lakh = ₹6.75 Cr, doubled for an integrator's margin, test and 11-language checks, plus infrastructure, ≈ ₹18 Cr.
I found no published contract values for comparable government voice-AI builds, so this is a range to be checked: use ₹15–25 Cr.

### 8.3 Three-year cost (running + one-time), ₹ Cr
| Calls a day | A. Desk | B1. AI-assisted desk | B2. Build own | **C. Buy from us** |
|---|---|---|---|---|
| 1 lakh | 969 | 580 | 235 | **241** (₹22 a case) |
| 10 lakh | 9,691 | 5,744 | 1,971 | **2,081** (₹19 a case) |

Per case over 3 years at 1 lakh a day: B2 ₹21.5, C ₹22.
**Read this honestly:** if government builds the same thing it ends up at about our price, and a little below at 10 lakh a day.
B2 numbers leave out the 12–18 months before the first call and the risk of a late or failed build; C starts in 2–3 months.
Our case therefore rests on four things, not on the per-call price:
1. **Speed:** live in months, not a year-plus tender and build.
2. **No upfront spend:** ₹0 against ₹18 Cr; government pays per resolved call and can stop.
3. **Schemes always current** (§9): government would otherwise hire its own team and scrapers.
4. **What it does not have:** keypad-phone door, photo read with a person checking, and the call-back by SMS and voice.
If Bhashini offers a government rate well below Sarvam's list, B2's running cost falls and the gap widens in B2's favour. Our answer is to use the same Bhashini engines (we can swap) and sell the operation, schemes and review desk.

## 9. Keeping schemes always up to date (the service government is buying)

How it works today (code in `haqdaar/data/pipeline/`, steps p0–p6): find the scheme pages, scrape, derive the rules, write cards,
translate into 10 languages, run quality gates, build the snapshot the line reads. 27 schemes are derived, 17 live; the target is 100+ central schemes.

| Cost | Per full refresh of 100 schemes | A year (12 refreshes) |
|---|---|---|
| Translate (≈6,000 letters × 10 languages a scheme) | ~₹12,000 [L] | ₹1.4 L |
| Pre-recorded audio for new text (~₹110 a scheme in 10 languages) | ~₹11,000 [L] | ₹1.3 L |
| Reading and checking models | negligible (₹0.006 a read) [M] | |
| **People (the real cost):** 4 scheme analysts ₹1.5 lakh a month = ₹0.72 Cr; 2 engineers to keep the scrapers working as pages change = ₹0.36 Cr | | **₹1.1 Cr** [E] |

Scheme freshness costs about ₹1.1 Cr a year per 100 central schemes. State schemes need roughly one analyst per two states [E].
Spread over calls: ₹0.30 a call at 1 lakh a day, ₹3.0 at 10,000 a day, ₹100 at 300 a day. **So pilots need a fixed fee or a small scheme list
(27 schemes ≈ ₹0.3 Cr a year); it is only cheap at scale.**

## 10. Our price, our profit

We sit between the vendors (speech, translate, model, phone, cloud) and the government. Of every ₹22, ₹17.6 goes to vendors and people on the call;
the rest pays for the team, the scheme-freshness service and our profit.

**Price ladder** [E, to be set after vendor quotes]:
| Stage | Calls a day | Price a resolved call | Notes |
|---|---|---|---|
| Pilot (one district, 60 days) | 300 | ₹25 (₹2.25 lakh a month) | 2 languages, 80% of photos checked by a person |
| State | 20,000–1 lakh | ₹22 | bulk vendor deal; monthly minimum that covers the fixed team |
| National | 10 lakh | ₹19 | vendor discounts 20% |
Always: a price cap, vendor price falls passed on, a monthly report.

**Profit at 1 lakh calls a day (36.5 million a year), ₹22 a call** [E]:
| | List vendor prices | 10% vendor discount | Lean plan (₹8.6 a call) |
|---|---|---|---|
| Revenue | ₹80.3 Cr | ₹80.3 Cr | ₹80.3 Cr |
| Cost of calls | ₹64.3 Cr | ₹57.9 Cr | ₹31.4 Cr |
| Gross profit | ₹16.0 Cr (20%) | ₹22.4 Cr (28%) | ₹48.9 Cr (61%) |
| Fixed costs: team of 22 (8 engineers, 6 operations and support, 4 scheme analysts, 4 government and product) ₹4.0 Cr + audits, legal, tools ₹1.0 Cr | ₹5.0 Cr | ₹5.0 Cr | ₹5.0 Cr |
| **Net before tax** | **₹11.0 Cr (14%)** | **₹17.4 Cr (22%)** | **₹43.9 Cr (55%)** |

At 10 lakh a day, ₹19 a call and a 20% vendor discount: revenue ₹693 Cr, gross profit ₹179 Cr (26%), net about ₹167 Cr after ₹12 Cr of fixed costs [E].
**Break-even:** about 31,000 calls a day at ₹22 (18,500 at ₹25). **Pilot:** 300 calls a day at ₹25 is ₹27 lakh a year of revenue against ₹22 lakh of call cost, so after a
small team (~₹1 Cr a year) the pilot loses about ₹1 Cr. Treat it as the cost of getting the first customer.

**Ways to raise the margin** (in order of size): lean plan (+₹9 a call); a Bhashini or Sarvam enterprise rate; Bulbul v2 voice (−₹4.4); lower human-check share as the model's agreement is proven
(each 10 points = ₹0.34); phone line at carrier rate (₹0.25 a minute = −₹1.0).
**Where our value is defended** (so government does not simply rebuild): the scheme-freshness service, the narrowing engine and the photo and keypad doors that already exist,
the review-label data that makes the model better, and a running service with a price cap.

## 11. The plan to get government to say yes and carry it forward

**What they will worry about, and the answer**
| They ask | Answer |
|---|---|
| Is the data in India? Who owns it? | Cloud in Mumbai; no audio or phone numbers kept; photos wiped on answer. **Gap:** the talk model runs at Groq (outside India). It is 3% of cost, so move it to an in-India model (Sarvam or IndiaAI compute) before any government pilot. |
| Are we locked in? | Speech, translate, voice and model are swappable. Bhashini can replace Sarvam. We hand over the scheme data and review labels and write an exit plan. |
| What if it gives wrong advice? | A dose guard strips dose sentences; a person checks doubtful photo answers; press 6 reaches the keys; the human KCC remains the fallback. |
| Who is accountable? | One price per resolved call, a monthly cap, a report of call types and how often a person overruled the model (`tools/review_counts.py`). |
| Does it replace our staff? | No: it takes overflow, night hours and photo work, and hands KCC agents the hard cases with photo and first-call words attached. |
| Why not build it ourselves? | You can; §8.3 shows the cost is similar. We start in months with no upfront spend and keep 100+ schemes current. If you later bring it in-house we hand over the code and data. |

**Steps**
0. **Weeks 0–4, near zero cost:** DPIIT startup recognition; register on GeM (recognised startups can be exempt from prior-experience, turnover and earnest-money rules,
   only if the tender says so; trial orders are possible). Move the model to an in-India host. Get three quotes: phone line, model, Sarvam enterprise (and ask Bhashini for its production rate).
1. **Months 1–3, one district, 60 days, paid:** 300 calls a day, 2 languages, photo by link and by SMS, 80% of photos checked. About ₹2.3 lakh a month paid; a desk would cost about ₹8 lakh for the same calls.
   Run it with a Krishi Vigyan Kendra or the state agriculture department's extension wing. Agree the success measures in writing first: share of calls that end in an answer, how often a person overruled the model, farmer satisfaction on a call-back, cost per resolved call.
2. **Months 4–9, the state:** the 1551 overflow number, 3–4 more languages, 20,000–50,000 calls a day, price ₹22, monthly minimum.
3. **Months 9–18, the national stack:** be the phone and keypad front door to Bharat-VISTAAR (the Budget 2026-27 proposed AI advisory on AgriStack; the Digital Agriculture Mission is about ₹2,820 Cr). Read the Farmer ID with consent so answers use the farmer's own plot and crop. Talk to IndiaAI's application and start-up financing programmes and to Bhashini.
4. **Make it hard to drop:** a monthly savings report against the desk; price cap and vendor-price pass-through; named champion inside the department (a joint secretary or district officer); exit plan.

## 12. What is proven and what is not

- **Proven on our line:** speech in and out in Hindi, Marathi, English; SMS delivered; photo read by a model; an operator desk that approves answers; 3,300+ automated tests pass.
- **Not yet:** real farmers calling; the other 8 languages on a live call; the keypad-SMS photo on a real phone; more than one caller at a time (**today: one**);
  a paid carrier line; any of the §7 sizing.
- At scale, vendor limits matter: Sarvam translate allowed ~8–10 calls a key [M]; Groq at 1,000 calls a second needs ~100,000 tokens a second. Enterprise terms are a must.
- At 1,000 calls a second a 10% photo check needs about **36,000** reviewers (8.64 million photos a day at 40 cases an hour). Large because the scale is large.

## 13. Slide blueprint (which table becomes which slide)

| # | Slide title | Draw | Numbers from |
|---|---|---|---|
| 1 | One answer costs ₹88 today, ₹18 with Haqdaar | two big numbers | §1, §8.2 |
| 2 | What farmers have today and where it stops | comparison table | §8.1 |
| 3 | Price per case: desk, AI-assisted desk, build, buy | bar chart, four bars | §8.2 |
| 4 | Where the ₹17.6 goes | donut or stacked bar (use the 9 lines) | §4 |
| 5 | Cost by language | horizontal bars, 11 languages, mark Tamil and Gujarati | §5 |
| 6 | What changes the price | tornado chart | §6 |
| 7 | Back-end bill: servers and databases are 0.2% | one stacked bar | §7 |
| 8 | Three-year cost at 1 lakh a day | grouped bars A, B1, B2, C (₹969 / 580 / 235 / 241 Cr) | §8.3 |
| 9 | Why buy if build costs about the same: speed, no upfront, current schemes, keypad + photo | four icons | §8.3 |
| 10 | Schemes always up to date: what it costs | small table | §9 |
| 11 | The price ladder and our profit | table; profit bars for three cases | §10 |
| 12 | Savings for government (₹259 Cr a year at 1 lakh a day against a desk) | one number + table | §15 |
| 13 | Plan: pilot to state to national | 4-step timeline | §11 |
| 14 | What is proven and what is not | two columns | §12 |
| 15 | The ask | three bullets | §1 point 10 |

Keep the 1,000-a-second case to a back-up slide: it is a stress test (about one in 17 Indians calling every day), not a forecast.

## 14. Sources

- Sarvam prices (speech ₹30 an hour, translate ₹20 per 10,000, Bulbul v3 ₹30 / v2 ₹15 per 10,000): [sarvam.ai/api-pricing](https://sarvam.ai/api-pricing)
- Groq token prices and cached rates: [groq.com/pricing](https://www.groq.com/pricing)
- EC2 c7i.xlarge Mumbai: [doit.com](https://www.doit.com/compute/spot/ap-south-1/c7i.xlarge); RDS: [bytebase](https://www.bytebase.com/dbcost/rds/instance/db.m6g.large.md)
- Toll-free ₹0.80–1.50 a minute, SIP 60–80% cheaper: [ozonetel](https://www.ozonetel.com/toll-free-numbers-india), [edesy](https://edesy.in/services/sip-trunk-setup-india)
- Unicode SMS parts: [Exotel](https://developer.exotel.com/docs/sms-support/unicode-sms); SMS price: [richautomate](https://richautomate.in/blog/sms-api-pricing-india-2026)
- Mother-tongue counts: [Census 2011](https://censusindia.gov.in/nada/index.php/catalog/10224)
- KCC: [Assam SAMETI note](https://sameti.assam.gov.in/sites/default/files/swf_utility_folder/departments/sameti_medhassu_in_oid_8/menu/information_and_services/KCC.pdf); KCC adviser pay near ₹25,000: from a recruitment notice found in search (IFFCO Kisan Sanchar), not opened by me
- Kisan e-Mitra: [Apolitical](https://apolitical.co/en/navigator/case-studies/kisan-e-mitra-indias-voice-enabled-ai-support-for-farmers); PM-Kisan chatbot volume: [TelecomTalk](https://telecomtalk.info/?p=1005482)
- CSC count: [India Observers](https://indiaobservers.com/digital-india-cscs-rural-services-expansion/)
- VoicERA on Bhashini (open-source voice AI stack, 19 Feb 2026): [Angel One news](https://oga-prod.angelone.in/news/economy/voicera-on-bhashini-govt-services-helpline-will-now-speak-in-your-language)
- Bhashini free for proof of concept only, production by quote: [CDO Magazine](https://www.cdomagazine.tech/aiml/indian-govt-ai-translation-platform-bhashini-gears-up-for-monetization)
- Startup relaxations in public buying: [Startup India](https://www.startupindia.gov.in/content/sih/en/reources/startup_india_notes/regulations_and_policies/MakeTheGovernmentYourPrimeCustomer.html)
- Bharat-VISTAAR, Digital Agriculture Mission: [IANS](https://ianslive.in/ai-booster-763-crore-farmer-ids-created-235-crore-crop-plots-surveyed--20260214111354) (Bharat-VISTAAR is described as proposed; confirm)
- Script lengths: measured with `sarvam-translate:v1` through `haqdaar/model/translate.py` (about ₹10 spent).

## 15. Savings against the desk, by size (for slide 12)

| Calls a day | Haqdaar a year (cost) | Desk a year | Saving a year |
|---|---|---|---|
| 300 (district pilot) | ₹0.2 Cr | ₹1.0 Cr | ₹0.8 Cr |
| 1 lakh | ₹64 Cr | ₹323 Cr | **₹259 Cr** |
| 10 lakh | ₹643 Cr | ₹3,230 Cr | **₹2,590 Cr** |
(Government's own spend if it buys from us at ₹22 is ₹80 Cr a year at 1 lakh a day: saving against the desk ₹243 Cr.)

## 16. Open items before the deck is final

1. Three vendor quotes: phone line, in-India model, Sarvam enterprise; ask Bhashini for its production rate.
2. Real KCC cost per seat, calls a year and call types (ask the department; none published).
3. A real load test: calls per server and phone channels per server (§7 is sizing, not measurement).
4. Test the lean plan: Hindi and Marathi model answers without the translate step; v2 voice with farmers.
5. Run the other 8 languages on live calls; measure script lengths on 50+ sentences, not 8.
6. Confirm Bharat-VISTAAR status and GeM trial-order limits.
7. Check the B2 build range (₹15–25 Cr) against one real government voice-AI contract.

## 17. Corrections to earlier figures (so the team does not use old ones)

- ₹15 a call (earlier chat) → **₹17.6**: voice-out now counted on 2,400 letters of 40 reply sentences, not the 910 letters of a pasted draft.
- Reviewers at 1,000/s: "150–300" was wrong → about 36,000.
- Human check ₹0.34 a call here is lower than ₹1–2 in BUSINESS-CASE.md §7: that file's tiers are not recomputed.
- BUSINESS-CASE.md §11–13 omit the translate step; use this file.
