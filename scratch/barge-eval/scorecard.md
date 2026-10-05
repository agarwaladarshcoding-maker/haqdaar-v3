# Cut-in scorecard

65622 scenarios + 22 plain calls under trouble. Real engine and audio code on a virtual clock; fake line, speech-to-text and model.

| | check | what good looks like | what we do | n | result |
|---|---|---|---|---|---|
| C1 | every call ends cleanly (no crash, no loop, one stop row) | 100 % | 65622 of 65622 | 65622 | **pass** |
| C2 | a key stops the agent | <= 50 ms, every time | max 0 ms, stopped 1792 of 1792 | 1792 | **pass** |
| C3 | clear speech stops the agent fast | <= 300 ms (good systems: 200-300) | median 280 ms, p95 290 ms, max 290 ms | 3220 | **pass** |
| C4.keys_only | speech gets through at every place the agent talks (goodbye aside) [keys_only] | every place | 0 of 19 places; deaf at: anything_else, box_question, greeting_trilingual, keypad_box, menu_chip, menu_key, next_scheme_intro, no_more_schemes, opener_prompt, opener_short_prompt, results_exact_preamble, scheme:benefit_text, scheme:name, scheme:summary, section_menu, section_source_frame, state_q_maharashtra, unclear_prompt, waiting_for_reply | 302 | **info** |
| C4.voice | speech gets through at every place the agent talks (goodbye aside) [voice] | every place | 12 of 19 places; deaf at: next_scheme_intro, results_exact_preamble, scheme:benefit_text, scheme:name, scheme:summary, section_menu, section_source_frame | 302 | **FAIL** |
| C4.voice_qa | speech gets through at every place the agent talks (goodbye aside) [voice_qa] | every place | 21 of 21 places; deaf at: none | 310 | **pass** |
| C5a | a short cough or soft far voice does not stop the agent | 0 stops | 0 stops in 3904 | 3904 | **pass** |
| C5b | two short coughs (250 ms each, 250 ms apart) do not stop the agent | 0 stops | 0 stops in 1228 | 1228 | **pass** |
| C6a | a long cough or "hmm" does not make the caller lose what was being said | agent keeps talking, or says the cut part again | stopped 920 of 1288; cut part never said again in 0 | 1288 | **pass** |
| C6b | a long cough or "hmm" does not cost a turn or a strike | 0 | 0 of 1288 calls logged an extra NOISE / UNCLEAR turn | 1288 | **pass** |
| C7 | the caller's sentence reaches the engine whole and once (also with a breath in it, also when long) | 100 % | 2376 of 3612 | 3612 | **FAIL** |
| C8 | the agent starts to reply soon after the caller stops talking | <= 1500 ms (good systems: ~1000) | median 1639 ms, p95 2140 ms (of this, fixed waits: 800 ms end-of-speech + 350 ms speech-to-text) | 3756 | **FAIL** |
| C9 | agent and caller do not talk over each other for long (one plain sentence) | <= 600 ms | median 279 ms, max 469 ms; over 600 ms in 0 of 2772 | 2772 | **pass** |
| C10 | never more than one silence gap of dead air | <= 9 s | max 6099 ms | 62172 | **pass** |
| C11 | the agent never says the same clip twice in a row | 0 | 0 of 62172; clips: {} | 62172 | **pass** |
| C12 | the goodbye is always heard whole | 100 % | chopped in 0 of 56960 | 56960 | **pass** |
| C13 | the log knows how much of a cut clip was heard | within 60 ms | max error 1 ms | 62172 | **pass** |
| C14 | a key pressed while talking wins over the words | 100 % | 2016 of 2016 | 2016 | **pass** |
| C15 | after the caller hangs up the agent says nothing more | at most the clip in flight | 5244 of 5268 | 5268 | **FAIL** |
| C16 | input in the first 250 ms of a clip is not lost | speech is still heard | keys: took 552 of 1052 (rest dropped by the guard, on purpose); speech lost in 0 of 332 | 332 | **pass** |
| C17 | a second cut-in right after the first is heard too | 100 % | 828 of 828 | 828 | **pass** |
| C18.bed300 | works in a place with background sound level 300 (voice starts at 700, ends under 400) | question still heard, reply as fast as in a quiet room | question heard 76 of 76; reply median 1639 ms; ghost inputs in 0 key-only cases | 1320 | **pass** |
| C18.bed550 | works in a place with background sound level 550 (voice starts at 700, ends under 400) | question still heard, reply as fast as in a quiet room | question heard 0 of 76; reply median 6009 ms; ghost inputs in 0 key-only cases | 1320 | **FAIL** |
| C18.bed900 | works in a place with background sound level 900 (voice starts at 700, ends under 400) | question still heard, reply as fast as in a quiet room | question heard 0 of 23; reply median 0 ms; ghost inputs in 150 key-only cases | 810 | **FAIL** |
| C19.keys.voice.echo500 | plain call, echo 500 [keys, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **pass** |
| C19.keys.voice.echo1500 | plain call, echo 1500 [keys, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 22, ghost inputs 0, 73.8 s (quiet 51.6 s), keypad_only=False | 1 | **FAIL** |
| C19.keys.voice.bed300 | plain call, bed 300 [keys, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **pass** |
| C19.keys.voice.bed550 | plain call, bed 550 [keys, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **pass** |
| C19.keys.voice.bed900 | plain call, bed 900 [keys, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 7, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **FAIL** |
| C19.keys.voice_qa.echo500 | plain call, echo 500 [keys, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **pass** |
| C19.keys.voice_qa.echo1500 | plain call, echo 1500 [keys, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 34, ghost inputs 0, 79.7 s (quiet 51.6 s), keypad_only=False | 1 | **FAIL** |
| C19.keys.voice_qa.bed300 | plain call, bed 300 [keys, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **pass** |
| C19.keys.voice_qa.bed550 | plain call, bed 550 [keys, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **pass** |
| C19.keys.voice_qa.bed900 | plain call, bed 900 [keys, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 12, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **FAIL** |
| C19.question.voice.echo500 | plain call, echo 500 [question, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 60.1 s (quiet 60.1 s), keypad_only=False | 1 | **pass** |
| C19.question.voice.echo1500 | plain call, echo 1500 [question, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 16, ghost inputs 0, 66.6 s (quiet 60.1 s), keypad_only=False | 1 | **FAIL** |
| C19.question.voice.bed300 | plain call, bed 300 [question, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 60.1 s (quiet 60.1 s), keypad_only=False | 1 | **pass** |
| C19.question.voice.bed550 | plain call, bed 550 [question, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 60.1 s (quiet 60.1 s), keypad_only=False | 1 | **pass** |
| C19.question.voice.bed900 | plain call, bed 900 [question, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 6, ghost inputs 0, 60.1 s (quiet 60.1 s), keypad_only=False | 1 | **FAIL** |
| C19.question.voice_qa.echo500 | plain call, echo 500 [question, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 59.9 s (quiet 59.9 s), keypad_only=False | 1 | **pass** |
| C19.question.voice_qa.echo1500 | plain call, echo 1500 [question, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 41, ghost inputs 0, 109.3 s (quiet 59.9 s), keypad_only=False | 1 | **FAIL** |
| C19.question.voice_qa.bed300 | plain call, bed 300 [question, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 59.9 s (quiet 59.9 s), keypad_only=False | 1 | **pass** |
| C19.question.voice_qa.bed550 | plain call, bed 550 [question, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 68.6 s (quiet 59.9 s), keypad_only=False | 1 | **pass** |
| C19.question.voice_qa.bed900 | plain call, bed 900 [question, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 10, ghost inputs 0, 78.1 s (quiet 59.9 s), keypad_only=False | 1 | **FAIL** |
| C19.spoken.voice_qa.speech-to-textdown | plain call, speech-to-text down [spoken, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs -2, 25.7 s (quiet 51.2 s), keypad_only=True | 1 | **info** |
| C19.question.voice_qa.speech-to-textdown | plain call, speech-to-text down [question, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops -2, ghost inputs -2, 60.1 s (quiet 59.9 s), keypad_only=True | 1 | **info** |

## Failing checks: where, and one case to replay

- **C4.voice** speech gets through at every place the agent talks (goodbye aside) [voice]
  - where: {'voice:scheme:name': 28, 'voice:scheme:summary': 28, 'voice:section_menu': 24, 'voice:scheme:benefit_text': 19, 'voice:results_exact_preamble': 16, 'voice:section_source_frame': 15, 'voice:waiting_for_reply': 8, 'voice:next_scheme_intro': 6}
  - replay: `python -m tools.barge_eval --show keys:voice --lang en --bed 0 --at 5:300 --kind voice_question`
- **C7** the caller's sentence reaches the engine whole and once (also with a breath in it, also when long)
  - where: {'voice_qa:section_menu': 96, 'voice_qa:scheme:name': 84, 'voice_qa:scheme:summary': 84, 'voice_qa:section_source_frame': 60, 'voice_qa:scheme:benefit_text': 60, 'voice:box_question': 56, 'voice:anything_else': 56, 'voice_qa:box_question': 56}
  - note: {'voice_long': 1236}
  - replay: `python -m tools.barge_eval --show keys:voice --lang en --bed 0 --at 1:50 --kind voice_long`
- **C8** the agent starts to reply soon after the caller stops talking
  - where: {'voice_qa:scheme:name': 252, 'voice_qa:scheme:summary': 252, 'voice_qa:section_menu': 192, 'voice_qa:section_source_frame': 180, 'voice_qa:scheme:benefit_text': 180, 'voice_qa:anything_else': 168, 'voice:box_question': 168, 'voice_qa:box_question': 168}
  - replay: `python -m tools.barge_eval --show keys:voice_qa --lang en --bed 0 --at 1:200 --kind voice_answer`
- **C15** after the caller hangs up the agent says nothing more
  - where: {'voice_qa:one_moment': 24}
  - replay: `python -m tools.barge_eval --show question:voice_qa --lang en --bed 0 --at 9:50 --kind hangup`
- **C18.bed550** works in a place with background sound level 550 (voice starts at 700, ends under 400)
  - where: {'voice_qa:scheme:name': 8, 'voice_qa:scheme:summary': 8, 'voice_qa:section_menu': 8, 'voice_qa:box_question': 6, 'voice_qa:section_source_frame': 6, 'voice_qa:scheme:benefit_text': 6, 'voice_qa:anything_else': 6, 'voice_qa:greeting_trilingual': 4}
  - replay: `python -m tools.barge_eval --show keys:voice_qa --lang en --bed 550 --at 0:300 --kind voice_question`
- **C18.bed900** works in a place with background sound level 900 (voice starts at 700, ends under 400)
  - where: {'voice_qa:box_question': 28, 'voice_qa:results_exact_preamble': 27, 'voice_qa:section_source_frame': 21, 'voice_qa:greeting_trilingual': 14, 'voice_qa:opener_short_prompt': 14, 'voice_qa:state_q_maharashtra': 14, 'voice_qa:next_scheme_intro': 14, 'voice_qa:no_more_schemes': 14}
  - replay: `python -m tools.barge_eval --show keys:voice_qa --lang en --bed 900 --at 0:300 --kind voice_question`
- **C19.keys.voice.echo1500** plain call, echo 1500 [keys, voice]
- **C19.keys.voice.bed900** plain call, bed 900 [keys, voice]
- **C19.keys.voice_qa.echo1500** plain call, echo 1500 [keys, voice_qa]
- **C19.keys.voice_qa.bed900** plain call, bed 900 [keys, voice_qa]
- **C19.question.voice.echo1500** plain call, echo 1500 [question, voice]
- **C19.question.voice.bed900** plain call, bed 900 [question, voice]
- **C19.question.voice_qa.echo1500** plain call, echo 1500 [question, voice_qa]
- **C19.question.voice_qa.bed900** plain call, bed 900 [question, voice_qa]

Run: 65622 scenarios in 186 s.
