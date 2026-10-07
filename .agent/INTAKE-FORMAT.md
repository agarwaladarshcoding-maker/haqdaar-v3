# Intake of the team's schemes (markdown from myscheme), 6 Oct night. Shared spec for the annotators and the builder.

Source: `data_cache/intake/source.md` (5,069 lines, copied from ~/Downloads/documentation (1).md). Index: `data_cache/intake/index.json`
(34 unique schemes; each has slug, name, start, end = line numbers in source.md; a scheme's text is lines start..end).
Skipped on purpose: 3 repeats (National Youth Award, Nikshay Poshan, SBM-G appear twice) and 3 that are already live with recorded
clips (PMFBY, KCC, APY).

## What an annotator writes: one file per scheme, `data_cache/intake/annot/<slug>.json`
```
{
 "slug": "...",                         # same as the index
 "name_en": "...", "name_hi": "...",    # the scheme's own name; Hindi in Devanagari (the common spoken form)
 "aliases_en": ["..", "..", ".."],      # at least 3: short names callers say ("PM Awas", "Har Ghar Jal"), no generic words ("scheme", "loan")
 "aliases_hi": ["..", "..", ".."],      # at least 3 in Devanagari, as a caller would say them
 "category": "<one of the 9 kinds>",    # see below
 "category_why": "one short line",
 "gender": "ANY" | "female" | "male" | "other" | [list],
 "social_category": "ANY" | "GEN" | "OBC" | "SC" | "ST" | [list],
 "age": "ANY" | {"min": int, "max": int},       # the CALLER's age (the applicant); max 120 if no upper limit
 "income_max_inr": null | int,                   # yearly family income limit in rupees, if the text gives one (kept as a note, not a bit)
 "occupation": "ANY" | one of farmer, street_vendor, apprentice, entrepreneur, artisan, weaver, worker | [list],
 "state": "ANY" | "OTHER",                       # OTHER only for a scheme run by ONE state that is not Maharashtra; all central schemes ANY
 "home_state": "ANY" | "<CODE>" | [list],        # the state the caller must live in, code from haqdaar/contracts/vocab.py HOME_STATE
 "gives": ["cash_aid", ...],                     # codes from vocab.GIVES: cash_aid, loan, subsidy, insurance, monthly_pension, training, job, house, health_cover, scholarship, equipment, food, other
 "sub_kind": "short_code" | "ANY",               # the part inside the kind, a-z0-9_ only (examples: crops, animals, irrigation, water_supply, sanitation, roads, legal_aid, awards, for_organisations, tb, accident_cover)
 "for_organisation": true|false,                 # true when the applicant is an institution, company, startup, NGO, state government or a body, not a person
 "facts": {"<fact>": {"role": "needs"|"bars", "quote": "<verbatim from the scheme text>"}},   # fact names ONLY from vocab.FACTS (20). needs = the scheme needs the caller to be yes; bars = the scheme excludes a yes
 "gate_notes": ["plain short condition not turned into a box", ...],   # each condition a caller should hear as "it may fit, if ..."
 "evidence": {"age": "<quote>", "gender": "<quote>", "social_category": "<quote>", "occupation": "<quote>", "home_state": "<quote>", "income_max_inr": "<quote>"},  # a verbatim quote for EVERY non-ANY / non-null value above (only those keys)
 "confidence": "high" | "medium" | "low",
 "notes": "anything the builder or a person should know (optional)"
}
```
Rules for the annotator:
- Read ONLY the scheme's own lines. Do not use outside knowledge for eligibility; if the text does not say it, the value is ANY / absent. Doubt = ANY (a wrong "needs" hides the scheme from callers who fit).
- A quote must be copied exactly from the scheme's lines (the checker matches it after removing markdown marks and extra spaces). Keep quotes short (one clause).
- `needs`/`bars` only for facts the text clearly states. Do not guess a fact from the scheme's theme.
- The 9 kinds (category): farming, business_loans, jobs_skills, health, housing, pension, education, women_children, welfare_disability. Nothing else is allowed (the keys line has recorded clips only for these). Map by purpose: water / sanitation / roads / village infrastructure -> housing (sub_kind says which); life / accident insurance and old-age cover -> pension; legal aid, justice, awards, minority and SC / ST welfare -> welfare_disability unless a better kind fits (women -> women_children, students -> education, trade / enterprise / tourism firms / startups -> business_loans, skills / internships / jobs / government-service awards -> jobs_skills).
- `gender`: female if only women / girls may apply. `age`: the applicant's own age limits only.
- Hindi names: the form a caller says, in Devanagari, for example "प्रधानमंत्री आवास योजना", "पीएम आवास".
- File must be valid JSON (UTF-8). Write nothing else outside data_cache/intake/annot/.

## What the builder does
Reads source.md + index.json + annot/*.json and writes `data_cache/intake/schemes_intake.jsonl` (rows in the shape p6_snapshot reads; talk_only true; chunks.en made from the scheme's own sections) and a report. It REFUSES a scheme when: a code is not in the vocab, a quote is not found in the scheme's lines, fewer than 3 aliases, a fact name is unknown, JSON is invalid. Then it builds a snapshot into an isolated folder (never flips snapshots/CURRENT) for tests and stress.
