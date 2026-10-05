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
