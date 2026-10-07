# Haqdaar — cost model by language (government deployment, business plans)

Date: 6 Oct 2026. Pilot-stage product. Every number is tagged:
**[M]** measured on our own line or code, **[L]** list price from a vendor page (link in §9),
**[E]** my estimate, to be settled with a quote or a load test. Dollar prices use Rs 90 to the dollar [E].

## 1. The case that is priced

- 1,000 calls a second, 5 minutes each, so **300,000 calls on the line at once**, 86.4 million calls a day.
  (Also shown at 1 lakh and 10 lakh calls a day, §7: those are the sizes a government would start with.)
- The caller speaks one of 11 languages (Sarvam's 11): Hindi, Bengali, Marathi, Telugu, Tamil, Gujarati,
  Kannada, Odia, Malayalam, Punjabi, English. Every call goes through English in the middle (speech in →
  English → model → English answer → the caller's language → speech out).
- One photo per call. A text message goes back on every second call, with the audio message.
- The agency is on **business / enterprise plans**: Groq, Sarvam, a carrier line, a cloud account.
  Only Sarvam and cloud list prices are public. Groq and Sarvam enterprise prices are by quote, so the
  list price here is a ceiling.

## 2. One call: what it costs, line by line (weighted over the 11 languages)

| Line | How it is counted | Rs per call | Share |
|---|---|---|---|
| Voice out (talk replies) | 40 reply sentences [M] × 60 letters [E] = 2,400 English letters, grown to the script length (§3); Sarvam Bulbul v3 Rs 30 per 10,000 letters [L] | 8.15 | 46% |
| Translate to the caller's language | the same 2,400 letters; Sarvam Rs 20 per 10,000 [L]; English callers skip it | 4.66 | 26% |
| Phone line | 5 min × Rs 0.45 [E] (cloud toll-free is Rs 0.80–1.50 a minute; a carrier line is quoted 60–80% less) | 2.25 | 13% |
| Speech to text | 80 s of caller speech [E]; Rs 30 an hour [L] | 0.67 | 4% |
| Groq talk model | ~30,000 tokens in + 2,000 out (10 turns of ~3,000); gpt-oss-120b $0.15 in / $0.075 cached / $0.75 out [L]; half cached [E] | 0.55 | 3% |
| Audio message | half the calls × 350 letters spoken | 0.59 | 3% |
| Human check of the photo | 10% of photos [E] × Rs 3.4 a case (Rs 24,000 a month ÷ 177 hours ÷ 40 cases an hour [E]) | 0.34 | 2% |
| SMS | the photo link on every call + the summary on half; Rs 0.12 a part [L range 0.12–0.30] | 0.37 | 2% |
| Photo read (Muse) | one read, 5.3 s, 405 in + 145 out tokens [M] | 0.006 | 0% |
| **Servers, databases, small costs** (§5) | monthly bill ÷ calls | 0.04 | 0.2% |
| **Total** | | **17.62** | |

Three lines (voice out, translate, phone line) are 85% of the bill. The servers are 0.2%.

## 3. By language

How the language changes the cost, with nothing else guessed:
1. **Script length.** The price is per letter and the same sentence takes more letters in some scripts.
   I measured it on 8 reply sentences through Sarvam translate [M, 6 Oct 2026]: Hindi 1.12×, Bengali 1.05×,
   Marathi 1.07×, Telugu 1.16×, Tamil 1.37×, Gujarati 1.02×, Kannada 1.22×, Odia 1.12×, Malayalam 1.33×,
   Punjabi 1.16× the English letters. Only 8 sentences, so treat the third digit as soft.
2. **SMS parts.** Indian scripts go as Unicode: 70 letters in one part, then 134 in two, 201 in three
   [source §9]. A 100-letter English link text is 1 part; in Hindi it is 2; in Tamil it is 3.
3. **English** skips translate (Rs 4.80) and uses one SMS part.
4. Speech to text, the phone line, Groq and the photo read cost the same in every language
   (the model works in English).

Share of calls: the Census 2011 mother-tongue counts of the ten Indian languages, scaled to 97% [L], English 3% [E].
Hindi's count in the Census includes Bhojpuri, Rajasthani and other languages grouped under it, so Hindi's share is
a ceiling.

| Language | Share of calls | Script vs English | Cost per call Rs | Cost per day at 1,000/s (Rs Cr) | Person Rs | Saving per call Rs |
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
| **All 11, weighted** | 100% | | **17.62** | **152.2** | 88.5 | 70.9 |

The dearest language (Tamil, 19.8) is 17% above the cheapest Indian one (Gujarati, 16.9).
No language breaks the plan. The person's cost is one figure for every language (§6); a person who speaks
Tamil or Odia may cost more, which would raise the saving a little.

## 4. What changes the number most (all 11 languages, weighted)

| Change | Rs per call |
|---|---|
| Base (above) | 17.62 |
| Bulbul v2 voice (Rs 15 per 10,000 letters) in place of v3 | 13.2 |
| Phone line at Rs 0.25 a minute / Rs 1.00 a minute | 16.6 / 20.4 |
| Human check of 20% / 80% of photos | 18.0 / 20.0 |
| SMS at Rs 0.30 a part | 18.1 |
| Groq at Rs 1.00 a call (about twice my figure) | 18.0 |
| **Model speaks the language itself (no translate step) + v2 voice** | **≈ 8.6** |

The last row is the lean plan: it needs a model that answers well in Hindi or Marathi directly, and one more
check that the v2 voice is good enough for villagers. Not measured yet.

## 5. Servers, databases, small costs (monthly, at 1,000 calls a second)

Sizing is my estimate [E]. We have not measured calls per server; today the server takes one caller at a time.
Prices: EC2 c7i.xlarge $0.1785 an hour in Mumbai [L]; RDS Postgres db.m6g.large $165 a month [L], scaled by
core count; S3 about Rs 2.1 a GB-month standard and Rs 1.15 infrequent [L]; data out about Rs 8.5 a GB [L].

| Item | Sizing | Rs Cr a month |
|---|---|---|
| App servers | 300,000 calls ÷ 150 a box × 1.25 = 2,500 × c7i.xlarge, on demand | 2.93 |
| Phone-media / SIP boxes | 300,000 ÷ 500 × 1.25 = 750 × c7i.2xlarge | 1.76 |
| Database (cases, review queue, labels) | 10 shards × 48 cores, two zones | 0.71 |
| Second site, warm (half of the above) | | 2.70 |
| Storage | the call log is ~15 KB a call [M]; 12 months kept | 0.05 |
| Data out (audio links, photo page) | ~0.2 MB a call | 0.44 |
| Small costs: load balancers, cache, monitoring, backups, security, cloud support | 15% of the lines above [E] | 1.29 |
| Run team, 40 people, 24×7 | Rs 1.5 lakh a month each [E] | 0.60 |
| **Total** | | **10.5** |

That is Rs 0.04 a call. A 1-year commit on the servers normally saves 30–40% [E, not verified].

**Where the "lag" data lives.** The scheme and language data (the snapshot, 0.4 MB; the chunk index, 5.5 MB;
the 65 MB audio pool) is small and is copied onto every box, so it needs no database to read. The
databases hold only the case records, the review queue and the labels. Photos are wiped once answered, and
caller audio and phone numbers are not kept [M, by design]. If the agency wants every call **recorded**
(about 0.3 MB at 8 kbps [E]), it adds about Rs 0.1 Cr a month per month kept, about Rs 1 Cr for a year kept.

**Small costs that bite later (not in the total):** SMS sender and template registration with the carrier
(DLT, about Rs 5,000 once [L]); a load test before launch; a security audit the agency will ask for;
a spare Sarvam, Groq and carrier account so one outage does not stop the line.

## 6. The person it replaces

Same case, done by a human desk (Kisan-call-centre style): Rs 28.5 the call (BPO math: Rs 24,000 a month
loaded ÷ ~1,400 calls, plus telecom and quality) + Rs 50 to look at the photo + Rs 5 for half an SMS +
Rs 15 for half a voice note = **Rs 88.5** [E; only the call figure comes from staffing math]. At 1,000 calls
a second that is about **1.85 million** people on shift over 24 hours (6.5 min a call, 85% busy, 8-hour shifts,
7-in-6 and 15% leave).

Compared with what the government runs today (all found on the web, 6 Oct 2026):
- **Kisan Call Centre 1551:** live agents; 144 in an older source, 525 seats in the 2023 tender.
  525 seats is 0.2% of 300,000 calls at once. No photo, no call-back in the local language by message.
- **PM-Kisan 155261** with an AI chatbot: [95 lakh queries from 53 lakh farmers](https://telecomtalk.info/?p=1005482);
  a chat tool, not a voice line.
- **About 5 lakh CSCs:** one person at a time, and the farmer must travel; the operator is paid by commission.
- I found **no published cost per call** for any of these, so the person's figure above is staffing math,
  not their bill.

## 7. The benefit, by size

| Calls a day | Haqdaar (Rs Cr a day) | A person (Rs Cr a day) | Saving a year (Rs Cr) |
|---|---|---|---|
| 1 lakh (a pilot state) | 0.18 | 0.89 | about 259 |
| 10 lakh | 1.76 | 8.85 | about 2,590 |
| 86.4 million (1,000 a second, stress) | 152 | 765 | about 2.2 lakh |

The last row is a stress test, not a forecast: it is about one in 17 Indians calling every day.
If the agency sells the service to another body, 25% on cost is Rs 22 a call.

## 8. What is true today, what is not

- **True and measured:** unit prices of speech, translate, SMS and the photo read; the script lengths in §3;
  the 15 KB call log; the small data size.
- **Not true yet:** the server takes **one caller at a time**. 300,000 at once, 150 calls a box, and 500
  phone channels a box are my sizing, not tests. Sarvam translate allowed only about 8–10 calls a key [M];
  a business plan with raised limits is a must. Groq at this load is about 33 turns a second, 100,000 tokens
  a second (6 million a minute): enterprise limits only.
- **Prices to nail down with quotes:** phone line (Rs 0.45 is a guess; no rate card), Groq enterprise,
  Sarvam enterprise, SMS volume tier.
- **The human check of a photo** at Rs 0.34 a call is lower than the Rs 1–2 a call in BUSINESS-CASE.md §7.
  At 1,000 calls a second it still needs about **36,000** reviewers (10% of 8.64 million photos a day,
  40 cases an hour). The number is large because the scale is large.

## 9. Sources

- Sarvam prices (speech Rs 30 an hour, translate Rs 20 per 10,000, Bulbul v3 Rs 30 / v2 Rs 15 per 10,000): [sarvam.ai/api-pricing](https://sarvam.ai/api-pricing)
- Groq token prices and cached rates: [groq.com/pricing](https://www.groq.com/pricing) (enterprise: by quote)
- EC2 c7i.xlarge Mumbai: [doit.com](https://www.doit.com/compute/spot/ap-south-1/c7i.xlarge); RDS: [bytebase](https://www.bytebase.com/dbcost/rds/instance/db.m6g.large.md)
- Toll-free Rs 0.80–1.50 a minute, SIP 60–80% cheaper: [ozonetel](https://www.ozonetel.com/toll-free-numbers-india), [edesy](https://edesy.in/services/sip-trunk-setup-india)
- Unicode SMS parts (70 / 134 / 201): [Exotel](https://developer.exotel.com/docs/sms-support/unicode-sms); price Rs 0.12–0.30: [richautomate](https://richautomate.in/blog/sms-api-pricing-india-2026)
- Mother-tongue counts: Census of India 2011, [censusindia.gov.in](https://censusindia.gov.in/nada/index.php/catalog/10224)
- KCC: [sameti.assam.gov.in](https://sameti.assam.gov.in/sites/default/files/swf_utility_folder/departments/sameti_medhassu_in_oid_8/menu/information_and_services/KCC.pdf); CSC count: [indiaobservers](https://indiaobservers.com/digital-india-cscs-rural-services-expansion/)
- Script lengths: measured with `sarvam-translate:v1` through `haqdaar/model/translate.py`, script in the session scratchpad (about Rs 10 spent).
