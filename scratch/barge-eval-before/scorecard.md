# Cut-in scorecard

61992 scenarios + 22 plain calls under trouble. Real engine and audio code on a virtual clock; fake line, speech-to-text and model.

| | check | what good looks like | what we do | n | result |
|---|---|---|---|---|---|
| C1 | every call ends cleanly (no crash, no loop, one stop row) | 100 % | 61992 of 61992 | 61992 | **pass** |
| C2 | a key stops the agent | <= 50 ms, every time | max 0 ms, stopped 1672 of 1672 | 1672 | **pass** |
| C3 | clear speech stops the agent fast | <= 300 ms (good systems: 200-300) | median 440 ms, p95 450 ms, max 450 ms | 2982 | **FAIL** |
| C4.keys_only | speech gets through at every place the agent talks (goodbye aside) [keys_only] | every place | 0 of 15 places; deaf at: anything_else, box_question, did_not_get_reply, greeting_trilingual, next_scheme_intro, no_more_schemes, opener_short_prompt, results_exact_preamble, scheme:benefit_text, scheme:name, scheme:summary, section_menu, section_source_frame, state_q_maharashtra, unclear_prompt | 285 | **info** |
| C4.voice | speech gets through at every place the agent talks (goodbye aside) [voice] | every place | 8 of 15 places; deaf at: next_scheme_intro, results_exact_preamble, scheme:benefit_text, scheme:name, scheme:summary, section_menu, section_source_frame | 285 | **FAIL** |
| C4.voice_qa | speech gets through at every place the agent talks (goodbye aside) [voice_qa] | every place | 17 of 17 places; deaf at: none | 293 | **pass** |
| C5a | a short cough or soft far voice does not stop the agent | 0 stops | 0 stops in 3664 | 3664 | **pass** |
| C5b | two short coughs (250 ms each, 250 ms apart) do not stop the agent | 0 stops | 666 stops in 1168 | 1168 | **FAIL** |
| C6a | a long cough or "hmm" does not make the caller lose what was being said | agent keeps talking, or says the cut part again | stopped 852 of 1220; cut part never said again in 410 | 1220 | **FAIL** |
| C6b | a long cough or "hmm" does not cost a turn or a strike | 0 | 144 of 1220 calls logged an extra NOISE / UNCLEAR turn | 1220 | **FAIL** |
| C7 | the caller's sentence reaches the engine whole and once (also with a breath in it, also when long) | 100 % | 2136 of 3252 | 3252 | **FAIL** |
| C8 | the agent starts to reply soon after the caller stops talking | <= 1500 ms (good systems: ~1000) | median 1639 ms, p95 2140 ms (of this, fixed waits: 800 ms end-of-speech + 350 ms speech-to-text) | 3260 | **FAIL** |
| C9 | agent and caller do not talk over each other for long (one plain sentence) | <= 600 ms | median 439 ms, max 629 ms; over 600 ms in 246 of 2592 | 2592 | **FAIL** |
| C10 | never more than one silence gap of dead air | <= 9 s | max 13749 ms | 58632 | **FAIL** |
| C11 | the agent never says the same clip twice in a row | 0 | 1040 of 58632; clips: {'opener_short_prompt': 400, 'state_q_maharashtra': 316, 'q_gender': 252, 'q_social_category': 72} | 58632 | **FAIL** |
| C12 | the goodbye is always heard whole | 100 % | chopped in 760 of 53720 | 53720 | **FAIL** |
| C13 | the log knows how much of a cut clip was heard | within 60 ms | max error 1 ms | 58632 | **pass** |
| C14 | a key pressed while talking wins over the words | 100 % | 1896 of 1896 | 1896 | **pass** |
| C15 | after the caller hangs up the agent says nothing more | at most the clip in flight | 4944 of 4968 | 4968 | **FAIL** |
| C16 | input in the first 250 ms of a clip is not lost | speech is still heard | keys: took 492 of 992 (rest dropped by the guard, on purpose); speech lost in 0 of 312 | 312 | **pass** |
| C17 | a second cut-in right after the first is heard too | 100 % | 768 of 768 | 768 | **pass** |
| C18.bed300 | works in a place with background sound level 300 (voice starts at 700, ends under 400) | question still heard, reply as fast as in a quiet room | question heard 76 of 76; reply median 1639 ms; ghost inputs in 0 key-only cases | 1320 | **pass** |
| C18.bed550 | works in a place with background sound level 550 (voice starts at 700, ends under 400) | question still heard, reply as fast as in a quiet room | question heard 0 of 76; reply median 6009 ms; ghost inputs in 0 key-only cases | 1320 | **FAIL** |
| C18.bed900 | works in a place with background sound level 900 (voice starts at 700, ends under 400) | question still heard, reply as fast as in a quiet room | question heard 0 of 22; reply median 0 ms; ghost inputs in 126 key-only cases | 720 | **FAIL** |
| C19.keys.voice.echo500 | plain call, echo 500 [keys, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **pass** |
| C19.keys.voice.echo1500 | plain call, echo 1500 [keys, voice] | ends like the quiet call, agent never stops itself | stop=max_turns (quiet: survivors_le_4), self-stops 10, ghost inputs 9, 59.9 s (quiet 51.6 s), keypad_only=False | 1 | **FAIL** |
| C19.keys.voice.bed300 | plain call, bed 300 [keys, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **pass** |
| C19.keys.voice.bed550 | plain call, bed 550 [keys, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **pass** |
| C19.keys.voice.bed900 | plain call, bed 900 [keys, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 7, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **FAIL** |
| C19.keys.voice_qa.echo500 | plain call, echo 500 [keys, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **pass** |
| C19.keys.voice_qa.echo1500 | plain call, echo 1500 [keys, voice_qa] | ends like the quiet call, agent never stops itself | stop=max_turns (quiet: survivors_le_4), self-stops 10, ghost inputs 9, 59.9 s (quiet 51.6 s), keypad_only=False | 1 | **FAIL** |
| C19.keys.voice_qa.bed300 | plain call, bed 300 [keys, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **pass** |
| C19.keys.voice_qa.bed550 | plain call, bed 550 [keys, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 51.6 s (quiet 51.6 s), keypad_only=False | 1 | **pass** |
| C19.keys.voice_qa.bed900 | plain call, bed 900 [keys, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 11, ghost inputs 1, 48.3 s (quiet 51.6 s), keypad_only=False | 1 | **FAIL** |
| C19.question.voice.echo500 | plain call, echo 500 [question, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 60.3 s (quiet 60.3 s), keypad_only=False | 1 | **pass** |
| C19.question.voice.echo1500 | plain call, echo 1500 [question, voice] | ends like the quiet call, agent never stops itself | stop=max_turns (quiet: survivors_le_4), self-stops 10, ghost inputs 9, 104.9 s (quiet 60.3 s), keypad_only=False | 1 | **FAIL** |
| C19.question.voice.bed300 | plain call, bed 300 [question, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 60.3 s (quiet 60.3 s), keypad_only=False | 1 | **pass** |
| C19.question.voice.bed550 | plain call, bed 550 [question, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 60.3 s (quiet 60.3 s), keypad_only=False | 1 | **pass** |
| C19.question.voice.bed900 | plain call, bed 900 [question, voice] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 6, ghost inputs 0, 60.3 s (quiet 60.3 s), keypad_only=False | 1 | **FAIL** |
| C19.question.voice_qa.echo500 | plain call, echo 500 [question, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 59.9 s (quiet 59.9 s), keypad_only=False | 1 | **pass** |
| C19.question.voice_qa.echo1500 | plain call, echo 1500 [question, voice_qa] | ends like the quiet call, agent never stops itself | stop=max_turns (quiet: survivors_le_4), self-stops 8, ghost inputs 7, 104.9 s (quiet 59.9 s), keypad_only=False | 1 | **FAIL** |
| C19.question.voice_qa.bed300 | plain call, bed 300 [question, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 59.9 s (quiet 59.9 s), keypad_only=False | 1 | **pass** |
| C19.question.voice_qa.bed550 | plain call, bed 550 [question, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs 0, 68.6 s (quiet 59.9 s), keypad_only=False | 1 | **pass** |
| C19.question.voice_qa.bed900 | plain call, bed 900 [question, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 9, ghost inputs 0, 49.3 s (quiet 59.9 s), keypad_only=False | 1 | **FAIL** |
| C19.spoken.voice_qa.speech-to-textdown | plain call, speech-to-text down [spoken, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops 0, ghost inputs -1, 67.2 s (quiet 49.2 s), keypad_only=True | 1 | **info** |
| C19.question.voice_qa.speech-to-textdown | plain call, speech-to-text down [question, voice_qa] | ends like the quiet call, agent never stops itself | stop=survivors_le_4 (quiet: survivors_le_4), self-stops -2, ghost inputs -1, 57.2 s (quiet 59.9 s), keypad_only=True | 1 | **info** |

## Failing checks: where, and one case to replay

- **C3** clear speech stops the agent fast
  - where: {'voice_qa:scheme:summary': 196, 'voice_qa:scheme:name': 196, 'voice:anything_else': 196, 'voice_qa:anything_else': 196, 'voice_qa:section_menu': 168, 'voice:box_question': 147, 'voice_qa:box_question': 147, 'voice:state_q_maharashtra': 140}
  - replay: `python -m tools.barge_eval --show keys:voice --lang en --bed 0 --at 19:850 --kind voice_answer`
- **C4.voice** speech gets through at every place the agent talks (goodbye aside) [voice]
  - where: {'voice:scheme:name': 28, 'voice:scheme:summary': 28, 'voice:section_menu': 24, 'voice:scheme:benefit_text': 19, 'voice:results_exact_preamble': 16, 'voice:section_source_frame': 15, 'voice:did_not_get_reply': 8, 'voice:next_scheme_intro': 6}
  - replay: `python -m tools.barge_eval --show keys:voice --lang en --bed 0 --at 5:300 --kind voice_question`
- **C5b** two short coughs (250 ms each, 250 ms apart) do not stop the agent
  - where: {'voice:anything_else': 56, 'voice_qa:anything_else': 56, 'voice_qa:scheme:name': 55, 'voice_qa:section_menu': 48, 'voice_qa:scheme:summary': 43, 'voice_qa:scheme:benefit_text': 39, 'voice:box_question': 37, 'voice_qa:box_question': 37}
  - replay: `python -m tools.barge_eval --show keys:voice --lang en --bed 0 --at 0:200 --kind two_coughs`
- **C6a** a long cough or "hmm" does not make the caller lose what was being said
  - where: {'voice_qa:scheme:name': 56, 'voice_qa:scheme:summary': 56, 'voice_qa:scheme:benefit_text': 38, 'voice:no_more_schemes': 32, 'voice:anything_else': 32, 'voice_qa:results_exact_preamble': 32, 'voice_qa:no_more_schemes': 32, 'voice_qa:anything_else': 32}
  - replay: `python -m tools.barge_eval --show keys:voice --lang en --bed 0 --at 3:300 --kind backchannel`
- **C6b** a long cough or "hmm" does not cost a turn or a strike
  - where: {'voice:box_question': 22, 'voice_qa:box_question': 22, 'voice:state_q_maharashtra': 18, 'voice_qa:state_q_maharashtra': 18, 'voice:did_not_get_reply': 16, 'voice_qa:did_not_get_reply': 16, 'voice:opener_short_prompt': 12, 'voice_qa:opener_short_prompt': 12}
  - replay: `python -m tools.barge_eval --show keys:voice --lang en --bed 0 --at 2:300 --kind cough_long`
- **C7** the caller's sentence reaches the engine whole and once (also with a breath in it, also when long)
  - where: {'voice_qa:section_menu': 96, 'voice_qa:scheme:name': 84, 'voice_qa:scheme:summary': 84, 'voice_qa:section_source_frame': 60, 'voice_qa:scheme:benefit_text': 60, 'voice:box_question': 56, 'voice:anything_else': 56, 'voice_qa:box_question': 56}
  - note: {'voice_long': 1116}
  - replay: `python -m tools.barge_eval --show keys:voice --lang en --bed 0 --at 1:50 --kind voice_long`
- **C8** the agent starts to reply soon after the caller stops talking
  - where: {'voice_qa:scheme:name': 252, 'voice_qa:scheme:summary': 252, 'voice_qa:section_menu': 192, 'voice_qa:scheme:benefit_text': 180, 'voice_qa:section_source_frame': 170, 'voice_qa:anything_else': 168, 'voice:anything_else': 168, 'voice:box_question': 156}
  - replay: `python -m tools.barge_eval --show keys:voice_qa --lang en --bed 0 --at 1:200 --kind voice_answer`
- **C9** agent and caller do not talk over each other for long (one plain sentence)
  - where: {'voice_qa:box_question': 36, 'voice_qa:section_source_frame': 30, 'voice_qa:greeting_trilingual': 24, 'voice_qa:opener_short_prompt': 24, 'voice_qa:state_q_maharashtra': 24, 'voice_qa:results_exact_preamble': 24, 'voice_qa:no_more_schemes': 24, 'voice_qa:next_scheme_intro': 18}
  - replay: `python -m tools.barge_eval --show keys:voice_qa --lang en --bed 0 --at 0:50 --kind voice_answer`
- **C10** never more than one silence gap of dead air
  - where: {'keys_only:section_source_frame': 10, 'voice:section_source_frame': 10, 'keys_only:results_exact_preamble': 8, 'voice:results_exact_preamble': 8, 'keys_only:next_scheme_intro': 6, 'voice:next_scheme_intro': 6, 'keys_only:did_not_get_reply': 4, 'voice:did_not_get_reply': 4}
  - replay: `python -m tools.barge_eval --show spoken:keys_only --lang en --bed 0 --at 7:200 --kind key_twice`
- **C11** the agent never says the same clip twice in a row
  - where: {'voice:opener_short_prompt': 122, 'voice_qa:opener_short_prompt': 122, 'voice:state_q_maharashtra': 100, 'voice_qa:state_q_maharashtra': 100, 'keys_only:box_question': 92, 'voice:box_question': 92, 'voice_qa:box_question': 92, 'keys_only:opener_short_prompt': 72}
  - replay: `python -m tools.barge_eval --show keys:keys_only --lang en --bed 0 --at 1:300 --kind key_hash`
- **C12** the goodbye is always heard whole
  - where: {'voice:closing_farewell': 272, 'voice_qa:closing_farewell': 272, 'keys_only:closing_farewell': 216}
  - note: {'key_three_fast': 120, 'key_twice': 96, 'key_valid': 72, 'key_wrong': 72, 'key_hash': 72, 'key_star': 72}
  - replay: `python -m tools.barge_eval --show keys:keys_only --lang en --bed 0 --at 23:50 --kind key_three_fast`
- **C15** after the caller hangs up the agent says nothing more
  - where: {'voice_qa:one_moment': 24}
  - replay: `python -m tools.barge_eval --show question:voice_qa --lang en --bed 0 --at 9:50 --kind hangup`
- **C18.bed550** works in a place with background sound level 550 (voice starts at 700, ends under 400)
  - where: {'voice_qa:scheme:name': 8, 'voice_qa:scheme:summary': 8, 'voice_qa:section_menu': 8, 'voice_qa:box_question': 6, 'voice_qa:section_source_frame': 6, 'voice_qa:scheme:benefit_text': 6, 'voice_qa:anything_else': 6, 'voice_qa:greeting_trilingual': 4}
  - replay: `python -m tools.barge_eval --show keys:voice_qa --lang en --bed 550 --at 0:300 --kind voice_question`
- **C18.bed900** works in a place with background sound level 900 (voice starts at 700, ends under 400)
  - where: {'voice_qa:box_question': 28, 'voice_qa:unclear_prompt': 26, 'voice_qa:greeting_trilingual': 14, 'voice_qa:opener_short_prompt': 14, 'voice_qa:state_q_maharashtra': 14, 'voice_qa:results_exact_preamble': 14, 'voice_qa:next_scheme_intro': 14, 'voice_qa:section_source_frame': 14}
  - replay: `python -m tools.barge_eval --show keys:voice_qa --lang en --bed 900 --at 0:300 --kind voice_question`
- **C19.keys.voice.echo1500** plain call, echo 1500 [keys, voice]
- **C19.keys.voice.bed900** plain call, bed 900 [keys, voice]
- **C19.keys.voice_qa.echo1500** plain call, echo 1500 [keys, voice_qa]
- **C19.keys.voice_qa.bed900** plain call, bed 900 [keys, voice_qa]
- **C19.question.voice.echo1500** plain call, echo 1500 [question, voice]
- **C19.question.voice.bed900** plain call, bed 900 [question, voice]
- **C19.question.voice_qa.echo1500** plain call, echo 1500 [question, voice_qa]
- **C19.question.voice_qa.bed900** plain call, bed 900 [question, voice_qa]

Run: 61992 scenarios in 162 s.
