# NOTES (new file on branch v5-clean, 5 Oct 2026)
The old notes (3,500 lines, to 5 Oct) are in `.agent/NOTES-until-5oct.md` on this computer (not in git on this
branch) and in git at commit 019d6d0 (branch step-7.3-talk-first, file .agent/NOTES.md). Read their tail for the
last days. What still holds is carried over below.

## Carried over: facts that still hold
- ONE repo (GitHub haqdaar-v3), 4 work folders: ~/code/haqdaar-v2 (branch v5-clean, WORK HERE), ~/code/haqdaar-v2-7.3 (step-7.15-cut-in, the fallback for a call; its .env, .venv and audio are links to this folder's), -7.6, -7.7 (old steps).
- Push over https: `git push https://github.com/agarwaladarshcoding-maker/haqdaar-v3.git <branch>`. `git push origin` hangs when ssh port 22 is blocked. Local "ahead of origin" marks are stale because of this; compare with `git ls-remote --heads <url>`.
- Python is `.venv/bin/python` (3.11). The system python3 has no audioop.
- pytest in this folder on v5-clean: 2385 passed, 0 failed (5 Oct). In ~/code/haqdaar-v2-7.3 one test fails (tests/test_door_a.py::test_repo_entries_exclude_quarantined_slugs); it passes here (not looked into: most likely it reads data that folder does not have). After the summary Python may print "libc++abi ... recursive_mutex lock failed" at exit; the results are not touched by it.
- Groq, per model: 8,000 tokens a minute, 200,000 a day (rolling), 1,000 requests a day. A talk turn is ~3,000 tokens. GROQ_API_KEY_2 is tried once on a refusal. NEVER send a big request to read the limit: a refused turn prints it.
- Muse: Rs 30 a day cap, 8.6 s a turn, not for the front. Sarvam: saaras:v4 for the ear, bulbul:v3 for the voice.
- Hall network lets out web ports only: cloudflared (7844) and ssh (22) fail; ngrok works; run_demo picks ngrok by itself.
- A call with no phone: server `TALK_ONLY=true .venv/bin/python -m uvicorn haqdaar.server:app --port 8001`, then `.venv/bin/python -m tools.talk_probe --script voicepick`.
- Call logs: logs/calls/<id>.jsonl + logs/calls/trace/<id>.jsonl; `make calls`; `make log-text ID=<id>`.

## Carried over: the three bugs at the greeting (call ..50a7a2, 5 Oct 12:51). NOT FIXED. They are PLAN.md step 1.1.
- A noise with no words after the greeting sets prompt_open False (turn.py:469-471); phone.py:145-152 _wait_words listens again without opening it; the next key is dropped (turn.py:159, :246).
- Language by voice is a word list (lang_words.py:45). A full Hindi sentence = "no language heard" -> greeting again. Sarvam's own code (ear.py:219) is dropped at ear.py:797-800.
- Words said at the greeting are thrown away.

## Carried over: how the picker and the bits work today (explore agent, 5 Oct)
- planner.py next_action IS minimax, no model: score = (left now - most left after any answer) / turns; first box in SEVEN_BOXES order wins a tie. Skips known boxes and boxes that split nothing. Stops: STOP_SURVIVORS 4, MAX_QUESTIONS 6, MAX_TURNS 8, no_split.
- filter.py: one int per (box, value), bit i = scheme i; left = AND over answered boxes; UNKNOWN never narrows. Values: category 9, state 2, gender 3, social_category 4, age 7, income_band 0, occupation 7. 17 schemes.
- talk_pick.narrow says "ask nothing" at <= 4 left BEFORE the planner runs (talk_pick.py:105-106). No category has more than 4 schemes, so a situation never gets a question. The prompt (prompts/talk.py:66-69) then says show schemes. "Situation" is not in the prompt.
- Candidates = 10 search hits + all schemes of the known category (talk.py:163-176).
- Categories health and education hold 0 schemes: 4 hits are shown, all marked "does not fit" (talk.py:152).
- talk_words.spot fills category, occupation (5 of 7), gender. Age, state, social group come from the model's facts, checked in talk.py:83-103.
- No "sentence -> expected question" test set exists yet.

## 5 Oct ~15:00: branch v5-clean made (Claude). No app code changed.
- Off step-7.15-cut-in b5516aa, checked out in ~/code/haqdaar-v2.
- Removed (all still in git on the old branches): 25 PROMPT-*.md, PLAN-V2, PLAN-DASHBOARD, PHASE-4-PLAN, NEXT-PLAN, AUDIT-PHASE1-4, MUSE-BRIEF, OWNER-END-TODO, WORK.md, scratch/, work-adarsh/, work-with-tools/, dashboard/ with tools/dashboard_api.py + its test + the Makefile target. Build leftovers of the dashboard (node_modules, .next) deleted from disk.
- Kept on purpose: haqdaar-v2-brain/, source-docs/, sync_vault.py (owner's rule file + the AGENTS.md check use them; owner to say), .agents/ (agent set-up), all of tools/ and tests/ (one-off tools lines_sheet, cards_sheet, pace_samples, door_a_check, ear_check, model_bakeoff, qa_check are still there: each has a Makefile target; cut them when their part of the code is next touched).
- Added: PLAN.md (plan v5, three phases = the three charts), flow/ (charts + the script that draws and checks them), HANDOFF.md written new.
- Charts changed: the bits box is now "keyword bits + question picker (fixed code, minimax)"; a rules box says "a situation: ask first, at most 3, then show schemes; a named scheme: answer first".
- Scheme-search vectors copied from -7.3 to data_cache/scheme_index/ (not in git) so the first start does not build them again.
- Checks on v5-clean before the commit: pytest 2385 passed 0 failed (201 s); make talk-eval 2,552 calls 0 rules broken; flow/build_flows.py all checks pass; py_compile ok; sync_vault --status in sync. make stress / barge-eval not run (no app code changed).

## 5 Oct evening (turn 7): human-style talk on today's fixed code. No model, no cost. Script was a scratch one-off (not kept).
Facts from the run (snapshot CURRENT, 17 schemes; kinds: farming 4, business_loans 3, pension 3, jobs 2, women_children 2, welfare_disability 2, housing 1, health 0, education 0; state values are MAHARASHTRA / OTHER only; income_band has no values):
- talk_words.spot does not know "not". "मैं किसान नहीं हूँ" -> category farming + occupation farmer. "मुझे लोन नहीं चाहिए" -> business_loans. "i am not a farmer" -> farmer. The fact is then set BEFORE the model is called (talk.py:189), and the model can not take a fact away (talk.py _take_facts only sets).
- spot takes another person's work as the caller's: "मेरे पति किसान थे, अब मैं विधवा हूँ" -> occupation farmer + farming (she wants a widow pension). "my husband is a farmer and he is sick" -> farming; "sick" is not a health word.
- Two needs in one sentence: "खेती और घर दोनों" -> farming only (bare "घर" is not a housing word). When two kinds ARE both named, spot leaves the box out and the picker asks "which kind" (fine, but no memory of the second need).
- No "who is it for": "मेरी माँ के लिए पेंशन" gives pension only. Age / gender questions are worded "How old are you?" (prompts/talk.py QUESTION).
- Name match is weak. by="name" only for the full written name: "पीएम किसान योजना के बारे में बताइए", "अटल पेंशन योजना", "किसान क्रेडिट कार्ड". NOT matched by name: "पीएम किसान" (top hit smam), "pm kisan", "किसान सम्मान निधि" (top kcc), "मनरेगा" (top pmmy), "केसीसी", "pm awas" (top pmmy), "स्वनिधि", "मुद्रा लोन", "mudra loan". Step 1.3's rule "a named scheme: answer first" needs a list of short names per scheme first.
- A scheme we do not hold looks like any other need: "आयुष्मान" top kcc 0.47, "राशन कार्ड" top kcc 0.58, "ladli behna" jsy1 0.37, "उज्ज्वला" pmmy 0.34. The score can not tell "not held" from "held" (real needs score 0.37-0.62). Needs a list of well-known schemes we do not hold, or the model's word.
- Loose remarks ("पैसे की तंगी है", "घर में कोई कमाने वाला नहीं", "बुज़ुर्ग हूँ, कोई सहारा नहीं") -> 10 left, ask = category. Good: these DO get a question today.
- "पता नहीं", "नहीं नहीं बस योजना बता दो": no code path. The box is asked once more (ASK_TRIES 2), then UNKNOWN. No "just tell me" stop.
- talk.py run(): 2 silences in a row = goodbye + hang up (SILENCE_HANGUP_RUNG 2). A caller who says "one minute, I will get the paper" is hung up on. No "hold" action.
- prompt ACTIONS has 7 actions: answer, ask, show_scheme, repeat, goodbye, not_for_me, other_topic. None for: skip the questions, do not know, hold on, say it simpler, compare two, a scheme we do not hold, are you real / is it free, distress.
- Turn 7 files so far: fixtures/talk_human.json (55 cases, new), PLAN.md (added: more starts in 1.1, "1.3 additions", new step 1.8, 4 risks, D5-D7; nothing taken out), flow/build_flows.py (box "people" at x=2300, a free place right of the fail column; at XR it hit the fail box; 3 lines added to the limits note). Pictures: `python3 flow/build_flows.py <dir>` then `rsvg-convert -w 2600 x.svg -o x.png`.

## Turn 7: folder audit (explore agent, read only). Main points; from reading, not run.
- No secret in git. .env never committed. HF_TOKEN and NVIDIA_API_KEY in .env are read by no code.
- HARM 1: `make run`, `make call-me`, `tools/tunnel.py:147` point the ONE Twilio number at this folder with no confirm -> the fallback in -7.3 stops getting calls.
- HARM 2: server binds 0.0.0.0 (Makefile:20, run_demo.py:97); `/stream` has no Twilio check and no length cap (CALL_CEILING_S is read nowhere); `/tone` is an open debug route; /docs is open.
- HARM 3: `make stage-check` sends ~2,500 tokens to each talk model; `make talk-questions` ~120,000 tokens a model with no guard; `make ear-check` is live by default.
- HARM 4: p1_scrape.py:403-410 deletes a scheme's cached raw files when its scrape fails; `make pipeline-scrape` has no guard.
- STALE: .agents/rules/haqdaar-brain.md (alwaysApply) calls the brain "binding / single source of truth"; AGENTS.md:23-24 names sync_vault as the build check. Both clash with plan v5. Left for the owner (D2); agent rule files are his.
- DEAD: phone.py:50 TURN0_KEYS; run_demo.py:28,108 voice_demo branch; tunables read by no code: BOX_STRIKES_TO_KEYPAD, GATES_FILE, MAX_SOURCE_AGE_DAYS, RESPONSE_BUDGET_S (CALL_CEILING_S too, but 1.6 wants it); types.py:41 names WORK.md. 7 old snap_* folders used by nothing. Tools write to scratch/, which was not ignored.
- STEP 1.1 traps: (a) the greeting is a RECORDED clip: lines.yaml -> texts.py hash -> audio/*.ulaw -> snapshot templates.json. New greeting words = `make render YES=1 SNAP=...` (paid Sarvam) + `make snapshot` (flips CURRENT). (b) HELLO in prompts/talk.py:115 is a second copy of opener_prompt in lines.yaml:40. (c) LANGS_OFFERED sets greeting parts AND keys AND pickable languages; 5 hellos with 2 pickable needs a new setting. (d) Lang type holds 3 languages only (types.py:16, log_schema.py:73, ~14 hard-coded tuples). (e) talk.run() has no way to take first words (talk.py:411; call.py:667); phone.py:102-110 drops the text; call.py:630-637 counts non-language words as a wrong key. (f) select_language has copies: sim.py:219, barge_eval.py:534, talk_eval.py:169, fakes in test_barge_sweep / test_talk. (g) with SPEECH_CUT_IN off, sound during the greeting clip is thrown away (turn.py:434). (h) ear.py:55 end-of-speech wait is fixed at import. (i) call_viewer.py:27 and talk_eval.py:246 parse the log line "<- key N: language xx" and the clip name greeting_trilingual.
- Tests that pin today's greeting: test_barge_sweep.py:625-690 (+:487), test_silence_rules.py:73,140, test_barge_eval.py:185-225, test_talk.py:97,209, test_lang_words.py, test_langs_offered.py:26, test_texts.py:68, test_render.py:25,57, test_live_speech.py:400. conftest.py:73 forces LANGS_OFFERED hi,mr,en for the suite (phone runs hi,en).
- tools/talk_probe.py default port 8001 = call_viewer's port.
