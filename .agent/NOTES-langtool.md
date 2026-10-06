# NOTES-langtool (branch lang-switch-tool from v5-full c617565, folder ~/code/haqdaar-v2-langtool, 6 Oct)

- Why its own folder: the main folder was on cut-in-fix with changes not committed (another task, live). Links made
  here: .env, .venv, audio, data_cache/chunk_index, data_cache/photo -> main folder.
- Before: the language changed only by what the ear heard (phone._follow_language). "explain this in Hindi" said in
  English kept English. The model has no tools: it answers one JSON object (prompts/talk.py).
- Now:
  - lang_words.languages_named(text): every language named in the words (11 Sarvam languages, offered or not).
  - engine/talk.py _decide: when the caller's words name a language the call is not in, and the model writes
    English (work == "en"), the turn's NOTE gets prompt.LANG_NOTE (names + codes). The model may add "lang": "hi".
    Taken only if it is one of the languages named THIS turn. _switch_lang sets _Talk.lang, audio.language and
    audio.lang_asked. This same reply is translated and voiced in the new language.
  - action "repeat" + lang ("say that again in Hindi"): the last reply (last_work, English) is said in the new one.
  - phone._follow_language: when lang_asked is set, the ear's guess no longer moves the language. Another ask in
    words moves it again.
- The rule is in the NOTE, not in SYSTEM: the word budget test (test_clarify_wire, 0 words left) is not touched,
  and turns with no language name cost no tokens.
- (The first commit had a limit: no offer with ENGLISH_PIPE=false for a hi / mr caller. Taken away, see the end.)
- No new log row kind: one line in the server log "<- talk: language en -> hi (asked in words)".
- REAL MODEL (Groq qwen3.8-27b, TALK_ONLY, translate faked, scratch script): 5 of 5: en "explain this to me in Hindi" -> hi;
  hi "मुझे इंग्लिश में बताओ ..." -> en; en "I studied in a Hindi medium school ..." -> stays en; en "can you speak in
  Marathi please" -> mr; hi "तमिल में बोलिए" -> ta (say: "I can speak in Tamil. What kind of help ..."). About 8 model
  calls, 4 waits of 25 s on the minute limit.
- CHECKS: tests/test_lang_asked.py 10 passed. Full pytest 3251 passed, 1 failed: test_door_a::test_repo_entries_
  exclude_quarantined_slugs, which fails here with the change stashed too (side folder lacks some ignored data).
  make talk-eval ARGS="--places 2": 1355 calls, 0 broken rules (its fake model never sets lang). py_compile ok.
- NOT done: a real call with voice; talk_eval has no language rule; the main folder (cut-in-fix) does not have this.
- 6 Oct, owner: "why the limit with the pipe off; switch it on". WHY it was there: with the pipe off a hi / mr caller's
  reply is written by the model in Hindi / Marathi, and translate only goes FROM English (translate.py source en-IN).
  FIX: a turn whose words name another language is worked in English (work = "en" for that one turn), pipe on or off.
  If the model does not switch (a mention), the English reply is translated back to the caller's language (the 1.4
  step). "Say it again in X" when the last reply was written in Hindi (pipe off): one more model try with the note
  "Write your last reply again in say, in English"; _last_en marks whether last_work is English.
  COMES WITH IT (pipe off only): that one turn pays the translate step and is checked by the English rules; after a
  switch to hi / mr the next turns are written by the model in that language itself, as any pipe-off call.
  Checks: test_lang_asked 11 passed; full pytest 3252 passed, 1 failed (the same old test_door_a one). Real model
  not run again for this (fake model only); talk-eval not run again.
