# HAQDAAR: references for the PPT

Goes with `DEMO-FOR-PPT.md`. Every link below was looked up on 15 Sep 2026.
Before a number goes on a slide, open its link once and check the number is still there.
Items marked **(check)** came to us second-hand, so read the original first.

---

## 1 · What kinds of references to use

| Kind | Where it goes | Example |
|---|---|---|
| Government data | Problem slide | TRAI phone numbers, MoSPI/NSS surveys, Census, NFHS |
| Scheme facts | Scheme slide | the myscheme.gov.in page for each scheme |
| Studies / reports | Problem slide ("why people miss schemes") | World Bank, Haqdarshak, WEF |
| Similar work | "Why phone / voice" slide | Kisan Call Centre, Mobile Vaani |
| Tools we built on | How-it-works slide | Twilio, Sarvam, Whisper |

On slides, put a short source line under each number (for example "Source: TRAI, May 2026"),
then one last "References" slide with the full links.

---

## 2 · Problem slide: numbers with sources

**1. Almost everyone has a phone.**
- India had **1,294.46 million wireless subscribers** at the end of May 2026.
  Source: TRAI press release, *Telecom Subscription Data as on May 2026*.
  https://www.trai.gov.in/notifications/press-release/trai-releases-telecom-subscription-data-may-2026

**2. But many do not have a smartphone.**
- About **350 million people in India still use a feature phone** (2024, Counterpoint and IDC data).
  Source: TechCrunch, 13 Jul 2024.
  https://techcrunch.com/2024/07/13/india-clings-to-cheap-feature-phones-as-brands-struggle-to-tap-new-smartphone-buyers/

**3. Reading and the internet are hard for many.**
- Literacy is **74.04%** overall and **67.8%** in villages (Census 2011).
  Source: MoSPI, *Literacy and Education* chapter.
  https://www.mospi.gov.in/sites/default/files/reports_and_publication/statistical_publication/social_statistics/Chapter_3.pdf
- Only **24.6% of women in villages** have ever used the internet (NFHS-5, 2019–21). **(check)** the India fact sheet.
  https://rchiips.org/nfhs/factsheet_NFHS-5.shtml
- Only **24.7%** of people aged 15+ can use a computer (NSS 78th round, 2020–21).
  Source: *Report on Multiple Indicator Survey, 2020-21*.
  https://microdata.gov.in/NADA/index.php/catalog/218
- Note: young people are doing better. **82.1% of village youth (15–24)** can use the internet (CAMS 2022–23).
  If you use this, say plainly that older people and women are the gap.
  https://www.mospi.gov.in/sites/default/files/publication_reports/CAMS%20Report_October_N.pdf

**4. There are too many schemes to find by yourself.**
- myScheme, the government's own search site, lists thousands of schemes.
  Open the site and write the count it shows today. Don't copy an old number.
  https://www.myscheme.gov.in/
- About myScheme (NeGD, MeitY): https://negd.gov.in/myscheme/

**5. People miss benefits they are owed.**
- "Only 40% of Indian citizens are able to apply for the government benefits they need."
  Acumen's Haqdarshak case study says this and cites World Bank paper WPS8207. **(check)** the World Bank PDF.
  https://acumen.org/case-studies/haqdarshak/
  https://documents1.worldbank.org/curated/en/785091506521681988/pdf/WPS8207.pdf
- WEF report on Haqdarshak (2026): low awareness, low literacy and poor connectivity stop people
  from getting schemes. **(check)** the exact wording before you quote it.
  https://reports.weforum.org/docs/WEF_The_Art_of_AI_for_Impact_Haqdarshak_2026.pdf

---

## 3 · Scheme slide: official scheme pages

These are the pages our demo facts come from.

| Scheme | Link |
|---|---|
| PM-KISAN | https://www.myscheme.gov.in/schemes/pm-kisan |
| Kisan Credit Card | https://www.myscheme.gov.in/schemes/kcc |
| PM Fasal Bima Yojana | https://www.myscheme.gov.in/schemes/pmfby |
| Atal Pension Yojana | https://www.myscheme.gov.in/schemes/apy |
| Ayushman Bharat PM-JAY | https://www.myscheme.gov.in/schemes/ab-pmjay |
| PMEGP | https://www.myscheme.gov.in/schemes/pmegp |
| NAPS (apprenticeship) | https://www.myscheme.gov.in/schemes/naps |

A good extra line for scheme reach: PM-KISAN's 23rd instalment went to **9.44 crore farmers** (June 2026).
Source: PIB. https://www.pib.gov.in/PressReleasePage.aspx?PRID=2275744&reg=3&lang=1

---

## 4 · "Why a phone call works" slide: similar work

- **Kisan Call Centre** (1800-180-1551). The government has run a farmer phone helpline since
  21 Jan 2004, answering in 22 languages. This shows a phone line already works for farmers.
  https://www.manage.gov.in/kcc/infra.asp
- **Mobile Vaani (Gram Vaani).** A voice platform (IVR) used in villages that needs no internet or smartphone,
  and works for people who can't read well.
  Paper: *An Analysis of Impact Pathways arising from a Mobile-based Community Media Platform in Rural India* (arXiv, 2021).
  https://arxiv.org/abs/2104.07901
- **Haqdarshak.** Field workers help families find and apply for schemes; they have reached millions of families.
  This shows the need is real. HAQDAAR does the same finding step over a phone call, with no field worker.
  https://www.haqdarshak.com/

Line for the slide: *"Phone helplines and voice systems already work in rural India. HAQDAAR adds scheme-finding to one."*

---

## 5 · How-it-works slide: tools

- **Twilio Media Streams**: live call audio to our server. https://www.twilio.com/docs/voice/media-streams
- **Sarvam AI**: Hindi/English voice (Bulbul) and speech-to-text (Saarika). https://docs.sarvam.ai/
- **Whisper** (backup speech-to-text): Radford et al., *Robust Speech Recognition via Large-Scale Weak Supervision*, ICML 2023.
  https://arxiv.org/abs/2212.04356

---

## 6 · Ready-to-paste "References" slide

1. TRAI, Telecom Subscription Data as on May 2026, press release. trai.gov.in
2. TechCrunch (Counterpoint/IDC data), "India clings to cheap feature phones", 13 Jul 2024.
3. Census of India 2011, literacy, via MoSPI.
4. NFHS-5 (2019–21), India fact sheet, IIPS / MoHFW.
5. NSS 78th round, Multiple Indicator Survey 2020–21, MoSPI.
6. CAMS 2022–23 (NSS 79th round), MoSPI.
7. myScheme, National Platform for Government Schemes, NeGD / MeitY. myscheme.gov.in
8. Acumen, Haqdarshak case study, citing World Bank Policy Research Working Paper 8207.
9. World Economic Forum, *The Art of AI for Impact: Haqdarshak*, 2026.
10. PIB, 23rd Instalment of PM-KISAN, June 2026.
11. Kisan Call Centre, MANAGE / Ministry of Agriculture.
12. An Analysis of Impact Pathways arising from a Mobile-based Community Media Platform in Rural India (Mobile Vaani), arXiv:2104.07901, 2021.
13. Twilio Media Streams docs; Sarvam AI docs.
14. Radford et al., Whisper, ICML 2023, arXiv:2212.04356.
