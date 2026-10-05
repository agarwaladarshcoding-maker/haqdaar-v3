# Muse job — the words for the new lines, then the step 7.3 review

Two parts. Part A can start now and writes no code. Part B starts only when the step 7.3
coding job is finished. Before either: `make muse-status` (cap is Rs 30 a day; stop if blocked).
Work in `~/code/haqdaar-v2`. Read `.agent/TASK.md` and the end of `.agent/NOTES.md` first.

## Part A — words for three new spoken lines (no code, no render)

Steps 7.3 and 7.4 add three short lines. Each must be recorded in English, Hindi and Marathi,
and each recording costs money, so the words must be right before `make render`.

| Line | When it plays | What it must say |
|---|---|---|
| talk-first opening | right after the language is picked | "What do you want to know? Say it, or press 0 for the list." |
| no-reply line | at ANY point where the call waited and heard nothing | "I did not get your reply. Here are the choices again." Then the same menu or question plays again. |
| one moment | the moment a question is taken, while the answer is made | "One moment." |

Do this:
1. Read `haqdaar/audio/lines.yaml` to match the voice of the lines already there
   (`greeting_trilingual`, `opener_prompt`, `unclear_prompt`, `section_menu`).
   Read `PROMPT-STEP-7.3-TALK-FIRST.md` and `PROMPT-STEP-7.4-ONE-MOMENT.md` for the rules.
2. Write each line in en, hi, mr. The caller is on a basic phone, often in a village, often
   not a strong reader. So: spoken, everyday words, the way a helpful person at a counter talks.
   No English loan words in the Hindi or Marathi where a plain word exists. Feminine voice
   (the lines already use "समझ नहीं पाई").
3. Keep them short. Say how many seconds each takes at the pace used now. The topic menu is
   already 44 seconds in Hindi, so the opening must be under 5 seconds and "one moment" under 2.
4. The no-reply line must work in front of every menu and every question, so it must not name
   any one menu. Check it reads right before: the language choice, the topic list, a yes/no
   confirm, and the section menu of a scheme.
5. Give 2 choices per line per language where there is a real choice, and say which you would pick.
6. Check each line id you suggest does not clash with one already in `lines.yaml`.

Output: one table (line id, en, hi, mr, seconds) for the owner to say yes or no to.
Do NOT edit `lines.yaml`. Do NOT render. The owner approves the words first.

## Part B — review step 7.3 (only after the coding job reports done)

Step 7.3 = talk-first opening + the owner's rule: silence can come at ANY wait point, so every
wait must speak again through ONE shared helper. Never a silent default, never dead air.

The base to compare against is branch `step-7.2-one-at-a-time` (commit 254d828 = steps 7.1 + 7.2).
`git diff step-7.2-one-at-a-time` shows only step 7.3.

Run and paste real output:
- `.venv/bin/python -m pytest -q` (must be 2267 or more)
- `make stress` (crashes 0, truth failures 0)
- one keypad sim and one spoken sim to the farewell

Check, with path:line for each:
1. The opening is one short line. The 9-choice list plays only on key 0 or after two misses.
   Misses are counted and logged.
2. Every wait point re-prompts on silence. The 8 `audio.next_input` sites in
   `haqdaar/engine/call.py` are: Door A pick, the language turn, keypad box, spoken box, confirm,
   two in "anything else", and read-back. Is it truly one shared helper, or copies?
3. Turn 0 no longer picks Hindi silently on no reply.
4. Silence still ends somewhere: the silence ladder must still hang up a caller who is gone.
   No loop that re-prompts forever.
5. It still fits with 7.1 (after any cut the call says something) and 7.2 (one scheme at a
   time, "this scheme" is the one being heard).
6. `test_talk_first_opener` exists and would fail if the rule broke (not empty on any case).
7. `call.py` still has no top-level import of audio, model or pipeline
   (`test_concurrency_and_import_discipline`).
8. No clip was rendered and `lines.yaml` holds no words the owner has not approved.

Also still open from the step 7.1 review, to be fixed before 7.1 to 7.3 merge:
(1) `test_cut_is_always_answered` is empty on 64 of 400 cases, assert at least one cut was seen;
(2) a failed `say_text` calls the paid `model.answer` again;
(3) the raw error text goes into `questions.jsonl`;
(4) `importlib` is called twice inside the loop.
Say for each: fixed, or still open.

Verdict: PASS, CONDITIONAL PASS with a numbered list, or FAIL. Write it into `.agent/NOTES.md`.
Do not fix code yourself. Do not merge.
