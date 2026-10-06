# Haqdaar — product & business case (number-backed)

Status: pilot-stage. Every number below is either measured on our own line (source given)
or flagged TO-VERIFY. Nothing here is invented.

## 1. Product in one line

A phone number any farmer can call and ask, in speech, which government schemes fit
them. No app, no reading, works on an Rs 800 keypad phone. Talk mode + keys fallback
+ photo diagnosis by SMS link with a spoken call-back.

## 2. What one 5-minute call consumes (measured quantities)

A 5-min call ≈ 10 talk turns (replies measured 0.7–1.6 s on Mac calls; cold first
turn 6.6 s; greeting 18.0 s for 5 languages: hi 3.4 / en 3.8 / mr 3.3 / gu 4.0 / ta 3.4).

| Component | Qty per 5-min call | Unit price | Source |
|---|---|---|---|
| Groq talk turns | 10 turns × ~3,000 tokens = ~30,000 tokens | free tier today; paid = tokens × list price (TO-VERIFY) | NOTES "carried over" + PLAN §1.4 |
| Sarvam STT (ear) | ~10–12 requests (0.3–0.4 s each; 2.36 s seen under stall) | paid per request (TO-VERIFY) | call ..af7f06 log |
| Sarvam live TTS | ~10 replies × ~4 sentences | paid per request (TO-VERIFY) | Mac-call logs |
| Sarvam translate (English-middle) | ~40 sentences (1 req/sentence, 2 on failed first try) | paid per request (TO-VERIFY) | NOTES 6 Oct late audit |
| Link SMS | 1 SMS, ≤120 plain-English letters = 1 part | **$0.0832 ≈ ₹7, measured delivered** | NOTES Turn 24 SMS test |
| Photo read (Muse) | 1 read (≤4 photos, 200 in 5.3 s, 405 in + 145 out tokens) | **≈ ₹0.006, measured** | NOTES Turn 24 probe |
| Twilio voice minutes | 5 min inbound (India) | TO-VERIFY in console (trial so far) | — |
| Human review share | §7 tiers | operator wage × minutes (TO-VERIFY wage) | — |

Fully-loaded estimate (stage 2, paid tiers): **₹15–30 per call**. The two lines to nail
before printing a deck: Twilio India voice ₹/min and Sarvam paid per-request prices.

## 3. Hard capacity caps (why the ladder looks the way it does)

Free-tier math, all measured:
- Groq: 8,000 tokens/min + 200,000 tokens/day + 1,000 requests/day **per model**, 3-model
  chain. 30,000 tokens per 5-min call → **~6–7 calls/day per model, ~20/day across the
  chain**. Tokens bind before requests (100 calls/day by request count). Per-minute:
  8,000 ÷ 3,000 ≈ 2.6 turns/min — never binding, since a turn takes ~20–30 s.
- Sarvam translate: **~60–90 requests/min measured** (429 at request 87 inside 52 s).
  One call uses ~8 sentences/min → **~8–10 concurrent calls per key**, then 429s.
- Muse: **Rs 30/day cap** → at ₹0.006/read ≈ 5,000 photo reads/day per key. Never the
  bottleneck before telephony.
- Line itself: **one caller at a time**, 10-min hard cap (CALL_CEILING_S 600),
  TALK_MAX_TURNS 40 (code default). One more concurrent caller = one more number + server slot.

## 4. Scale ladder

- **Stage 1 (today): laptop + tunnel + 1 number.** ~20 calls/day free, ~₹0/call.
  Use: demo + first pilot village.
- **Stage 2 (cloud VM Mumbai + paid API tiers + 5–10 numbers):** hundreds of
  calls/day at ₹15–30/call. Nothing architectural changes; each number is an
  independent slot. First binding constraint is Sarvam translate per key (~8–10
  concurrent) — solved with quota increase, not code.
- **Stage 3 (sharded servers + number pool + desk operator pool):** thousands/day.
  Bottlenecks scale linearly with money (minutes, reviewers). No technical cliff.

Scheme coverage grows separately: 17 live → 27 derived ready → 100+ central schemes
prompt is already with a coder. Search is 6–8 ms real; chunked cards cut ~450 tokens
per prompt — headroom is ample.

## 5. Viability: why we win

CSCs, helplines and portals all assume reading + data + initiative. Nobody serves the
illiterate keypad user voice-first end-to-end. Moat compounds per call: symptom→scheme
logs, dialect/short-name word lists, photo finding set — data no portal collects.
Distribution is the village network itself (fertilizer shops, Krishi Mitra, CSC VLEs
as photo proxies), not app-store marketing.

## 6. Monetization: four cases with pricing math

1. **B2G per-query / per-district SaaS.** Price ₹25–40 per resolved query vs ₹15–30
   cost → positive margin from day one of paid operation. Per-district: e.g. 300
   calls/day × ₹25 × 30 days ≈ ₹2.25 L/month/district revenue. Slowest cycle,
   biggest cheques. Entry: one pilot district.
2. **B2B agri-input / credit leads.** Fertilizer, seed, MFI/bank pay per qualified
   handoff (KCC intent, crop advisory). Same call flow; retailer kiosk already
   designed as the proxy point. Price per lead TO-VERIFY against local agent rates.
3. **Sponsored toll-free.** Sponsor funds minutes; one sponsor line plays per call;
   caller pays nothing. Funds the keypad base that can never pay. Price: cost +
   margin per call, sold as packs (e.g. 10,000 calls).
4. **Demand insights.** Anonymized, aggregated demand/pest maps as reports to agri
   firms and policy teams. Zero marginal cost once calls flow. Never sell personal
   data — caller numbers are never even logged.

Order: 1 (one pilot district) + 3 (one sponsor funds it) → 2 when intent quality is
proven → 4 in year two.

## 7. Human in the loop: built hooks + cost tiers

Already built: operator desk approves every photo answer (auto-approve only when AI
sure ≥ 0.4); bad photo → "send a clearer one", same link; unclear-speech and
voice-failure recovery, max twice, then polite close; "press 6" drops stuck talkers
to keys (offered after 3 unanswered questions); recap confirms details once before
answering; call-back catch routes missed call-backs to audio-by-SMS.

Built 6 Oct night for the keypad-SMS photo door (branch `sms-photo`, tested, not merged):
a photo that comes as SMS packets is read by Muse. The answer goes to the caller only if
the reader is at least 0.7 sure, every picture is at least 104 dots wide, and every photo
that was sent came whole. Otherwise the case waits on the same operator desk (it shows how
many photos came and the caller's first-call words) and the caller hears nothing until the
operator answers. Pictures are wiped once answered; only words are kept as labels
(`logs/review_labels.jsonl`; `tools/review_counts.py` shows how often the operator agreed,
by picture size). With no Muse key every SMS photo waits for the operator. The 0.7 and 104
are first guesses, to be set from those counts.

Tiers (review share × operator minutes):
- 80% review (pilot): every photo + low-confidence answer checked. ≈ +₹8–10/call.
- 20% (early scale): photos + low-confidence only. ≈ +₹2–4/call.
- 10% (mature): photos only. ≈ +₹1–2/call.
(Operator wage TO-VERIFY; desk review measured at ~1–2 min/case → 30–50
cases/hour/operator.) The review log is the training set — humans are the quality
brand and the data flywheel, not a stopgap.

## 8. Feasibility checklist (for the Q&A slide)

PROVEN: speech in/out hi/mr/en; SMS link delivered; Muse photo read; desk approve;
call-back speaking the answer; 3,000+ tests green; talk-eval 0 broken on main paths.
PILOT-STAGE (say so): real farmers calling; SMS to unchecked phones (needs paid
Twilio); cloud server; keypad-SMS photos (cut, join, operator hand-over built and tested with a stand-in
reader; no real keypad phone and no real model read of a 100–180 dot photo yet);
non-Hindi guard ~9/10 (falls back to English, never wrong text).

## 9. Top risks

1. Trial-account telephony (checked numbers only, US→India filtering) — cleared by
   paying Twilio, budgeted in §2.
2. Groq/Sarvam free-tier walls at ~20 calls/day and ~8–10 concurrent — cleared by
   paid tiers; unit cost stays inside §2.
3. Keypad-SMS photo readability — the one genuine technical unknown. The cut now
   gives about 176×132 for one photo and 96–128 wide for 2–5 photos (header left out,
   most detailed half of the frame), but no real model read of these is measured yet;
   the operator desk catches the doubtful ones until the counts say how often it is needed.
4. Government sales cycle — mitigated by sponsor-funded pilot (case 3) that needs
   no tender to start.

## 10. Verified 5-minute call scenario (Ramesh, Yavatmal)

Caller: smallholder cotton farmer, 2.5 acres, Marathi-accented Hindi. Goal: pest
identified on 3 photos + treatment + PMFBY claim steps, inside exactly 300 s.
Dialogue kept from the draft; every system label below corrected to what the code
actually does (verification appendix §14 lists each fix).

- 00:00 inbound SIP; 00:01 pre-rendered 5-language greeting (18.0 s, disk cache, ₹0).
- 00:19 Turn 1: Sarvam STT hears cotton-boll worm + curling leaves. talk_words.spot
  sets state/category/occupation locally (~1 ms CPU, ₹0); Groq replies, offering
  the photo link on yes / key 9.
- 00:48 caller says yes (son has a smartphone). Token case created; 1 DLT
  transactional SMS with the link leaves (₹0.12, volume-tier range ₹0.10–0.22).
- 01:25 3 photos arrive (Door 1 web upload; Door 0 keypad-SMS: 20 SMS parts for 1 photo, 12 each for 2, 10 each for 3–5, or
  3-digit proxy code at fertilizer kiosk / Krishi Mitra).
- 01:33 photo/read runs the Muse backend (PHOTO_READER=auto → muse when the key
  is set; stand-in otherwise): one read, ≤4 photos, measured 5.3 s, 405 in + 145
  out tokens ≈ **₹0.006**. Returns finding + sure score; dose-guard strips dosage
  sentences locally (₹0). Chunk index pulls the PMFBY clause locally (~ms, ₹0).
- 01:46 diagnosis spoken (pheromone traps, neem extract, no doses); 02:18 PMFBY
  72-hour intimation rule; 02:58 document checklist (Aadhaar, passbook, 7/12,
  sowing record); 03:32 thanks + goodbye; 03:52 hangup at 300 s.
- 03:53 post-call: 1 summary SMS (₹0.12) + voice advisory — audio link in SMS
  (data case) or 45-sec OBD call drop (no-data case).

## 11. Corrected sequence cost trace (production-India stack)

Basis flags: ✅ measured on our line · 🔶 official list price (live-check 6 Oct 26)
· ⚠️ third-party/plausible, confirm before printing · 🔴 draft was wrong, fixed.

| Seq | Action | Basis | ₹ |
|---|---|---|---|
| 1 | Inbound SIP 5 min @ ~₹0.45/min | ⚠️ Exotel-typical range ₹0.30–0.50, no rate card | 2.250 |
| 2 | 5-language greeting (disk cache) | ✅ | 0.000 |
| 3 | STT turn 1 (~18 s audio @ ₹30/hr) | 🔶 sarvam.ai/api-pricing | 0.150 |
| 4 | Minimax + bitmask narrowing (local CPU) | ✅ | 0.000 |
| 5 | Groq turn 1 (~1,500 tok; rate below) | ⚠️ $0.59/$0.79 per 1M, aggregators only | 0.080 |
| 6 | TTS turn 1 (~140 chars @ ₹3/1k) | 🔶 (draft said ₹0.042: 10× under) | 0.420 |
| 7 | STT turn 2 (~8 s) | 🔶 | 0.067 |
| 8 | Photo-link SMS (DLT transactional) | 🔶 range ₹0.10–0.22 | 0.120 |
| 9 | TTS guidance (~110 chars) | 🔶 (draft ₹0.033 → fix) | 0.330 |
| 10 | Muse photo read, 3 photos, 1 call | ✅ measured 5.3 s, ₹0.006 | 0.006 |
| 11 | Dose guard + chunk search (local) | ✅ | 0.000 |
| 12 | Groq diagnosis turn (~2,400 tok) | ⚠️ same rate flag | 0.130 |
| 13 | TTS diagnosis (~260 chars) | 🔶 (draft ₹0.078 → fix) | 0.780 |
| 14 | STT + Groq PMFBY turn (~14 s + ~1,500 tok) | 🔶+⚠️ | 0.197 |
| 15 | TTS 72-hr rule (~180 chars) | 🔶 (draft ₹0.054 → fix) | 0.540 |
| 16 | STT + Groq documents turn (~8 s + ~1,200 tok) | 🔶+⚠️ | 0.132 |
| 17 | TTS checklist (~160 chars) | 🔶 (draft ₹0.048 → fix) | 0.480 |
| 18 | Outro STT + Groq + TTS (~60 chars) | 🔶+⚠️ | 0.175 |
| 19 | Post-call summary SMS | 🔶 | 0.120 |
| 20A | Voice advisory as audio link + 350-char render | 🔶 Cloudflare R2 ~free + TTS ₹1.05 | 1.050 |
| 20B | Voice advisory as 45-s OBD drop | ⚠️ outbound typical ₹0.80–1.00/min, 60-s pulse | 0.900 |

Totals: **Scenario A (data) ≈ ₹7.03** · **Scenario B (no data) ≈ ₹5.98 + 0.90 ≈ ₹6.88.**
(Sums machine-checked: seq 1–19 = ₹5.977; +20A = ₹7.027; +20B = ₹6.877.)
Biggest draft errors fixed: TTS was 10× understated; the four vision rows
(Gemini router + 3× Llama vision ≈ ₹0.49) replaced by one measured Muse read
(₹0.006); OBD ₹0.40 → ~₹0.90 (60-s pulse); Groq model renamed (chain is
qwen3/gpt-oss — llama-3.3-70b 404'd on Groq 4 Oct, and $0.59/$0.79 is not on any
official price list).

## 12. Human vs Haqdaar for the same resolved case (corrected)

| Task | Human (KCC/KVK-style) | Haqdaar | Human basis |
|---|---|---|---|
| 5-min call handling | ₹28.50 | ₹3.3 (SIP+STT+Groq+TTS, seq 1–9) | ⚠️ in-house BPO math (₹24k/mo ÷ ~1,400 calls ≈ ₹17 + telecom + QA). Draft's KCC-tender basis withdrawn — see §14. |
| Visual inspection, 3 photos | ₹50.00 | ₹0.006 (one Muse read) | estimate: private agronomist per-batch fee |
| Dose/legal verification | ₹10.00 | ₹0.000 (local guard) | estimate: manual gazette check |
| Localised SMS drafting | ₹5.00 | ₹0.120 (DLT) | estimate: operator time |
| Spoken advisory | ₹15.00 | ₹1.05 / ₹0.90 (link / OBD) | estimate: field-officer recording |
| Physical field visit | ₹250–500 | not needed | NOTES field-visit figure, no URL on file |
| **Total remote** | **₹108.50** | **₹7.03 / ₹6.88** | **≈93–94% cheaper** |

Monthly savings at 100,000 cases: 100,000 × (108.50 − 7.03) ≈ **₹1.01 Cr**.
(With a physical visit avoided: ~₹350 − 7 ≈ ₹343 saved per case.)

## 13. Scalability: today vs the 1-lakh/day target

TODAY (measured, single laptop): one caller at a time; ~20 calls/day inside
free-tier walls (Groq 200k tok/day, translate ~60–90 req/min ≈ 8–10 concurrent
per key, Muse Rs 30/day ≈ 5,000 reads); Twilio trial (checked numbers only).

TARGET (what the draft's architecture section describes — build, not status):
SIP pool fronting stateless app boxes; photo upload + vision in background
threads so the voice loop never blocks; token-dir cases, no DB contention;
operator desk (port 8003) as the review queue; call-back daemon when the line
is idle. Nothing here contradicts the code's shape (server/talk/photo split),
but the concurrency figures in the draft (250 calls/box, 6.2 s vision, 10,000
channels) are unmeasured — load-test before printing.

Scale math (from B4): 1 lakh 5-min calls over a 14-h day ≈ 600 concurrent,
~1,200 at 2× peak. Humans: ~2,100 heads, ₹25–60/call, ₹8–18 Cr/month.
Haqdaar: ~150 reviewers + 20 tech/ops, ~₹8–12/call all-in (trace above + review
share + infra), ~₹3–4 Cr/month. Review tiers carry the quality story: 80%
reviewed in pilot → photos + low-confidence only at scale.

## 14. Verification appendix (6 Oct 2026, two checker agents)

- Sarvam STT ₹30/hr, TTS ₹3/1k chars: ✅ official api-pricing page, live.
- Groq $0.59/$0.79: ⚠️ no official price list (groq.com/pricing redirects;
  3.3-70b shows Enterprise-gated). Our live chain is qwen3-8b/gpt-oss — price
  Groq at purchase, quantities in §11 hold regardless.
- Gemini 2.0 Flash $0.075: 🔴 that is Flash-Lite's price; 2.0 retired from
  Google's page. And zero `gemini` references exist repo-wide — router removed.
- Exotel ₹0.45/min in: ⚠️ plausible (their blog: typical ₹0.30–0.50), no rate card.
- OBD ₹0.40/45-s: 🔴 not found; outbound typical ₹0.80–1.00/min, 60-s pulse.
- DLT SMS ₹0.12: ✅ inside every published 2026 range (₹0.10–0.22, volume-tier).
- KCC ₹142.85 Cr / 234 seats: 🔴 neither verified; live 2023 DA&FW RFP states
  525 initial seats, no award value. Human-call basis above recomputed from BPO
  staffing math instead.
- `photo/reassembler.py` → 🔴 real path `keypad_sms/reassembler.py`
  (SMSReassemblyManager.ingest_sms). `photo/back_msg.py` → 🔴 use
  `tools/photo_back.py` (PhotoBack; OLD_S=1800, SPACE_S=600, RETRY_S=30).
- OpenCV blur check, species confidences (0.94/0.88), 30–35% canopy: 🔴 no such
  code — reader returns finding + sure score + dose-sanitized text.
- uvloop, 250 concurrent/box, 10,000 channels: 🔴 unmeasured — §13 labels them
  target-architecture.
