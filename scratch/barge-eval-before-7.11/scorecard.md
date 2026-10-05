# Cut-in scorecard

540 scenarios + 0 plain calls under trouble. Real engine and audio code on a virtual clock; fake line, speech-to-text and model.

| | check | what good looks like | what we do | n | result |
|---|---|---|---|---|---|
| C1 | every call ends cleanly (no crash, no loop, one stop row) | 100 % | 540 of 540 | 540 | **pass** |
| C2 | a key stops the agent | <= 50 ms, every time | max 0 ms, stopped 84 of 84 | 84 | **pass** |
| C3 | clear speech stops the agent fast | <= 300 ms (good systems: 200-300) | median 280 ms, p95 290 ms, max 290 ms | 67 | **pass** |
| C4.keys_only | speech gets through at every place the agent talks (goodbye aside) [keys_only] | every place | 0 of 0 places; deaf at: none | 0 | **info** |
| C4.voice | speech gets through at every place the agent talks (goodbye aside) [voice] | every place | 7 of 13 places; deaf at: results_exact_preamble, scheme:benefit_text, scheme:name, scheme:summary, section_menu, section_source_frame | 22 | **FAIL** |
| C4.voice_qa | speech gets through at every place the agent talks (goodbye aside) [voice_qa] | every place | 16 of 16 places; deaf at: none | 56 | **pass** |
| C5a | a short cough or soft far voice does not stop the agent | 0 stops | 0 stops in 90 | 90 | **pass** |
| C5b | two short coughs (250 ms each, 250 ms apart) do not stop the agent | 0 stops | 0 stops in 0 | 0 | **pass** |
| C6a | a long cough or "hmm" does not make the caller lose what was being said | agent keeps talking, or says the cut part again | stopped 134 of 168; cut part never said again in 0 | 168 | **pass** |
| C6b | a long cough or "hmm" does not cost a turn or a strike | 0 | 0 of 168 calls logged an extra NOISE / UNCLEAR turn | 168 | **pass** |
| C7 | the caller's sentence reaches the engine whole and once (also with a breath in it, also when long) | 100 % | 64 of 64 | 64 | **pass** |
| C8 | the agent starts to reply soon after the caller stops talking | <= 1500 ms (good systems: ~1000) | median 1639 ms, p95 2139 ms (of this, fixed waits: 800 ms end-of-speech + 350 ms speech-to-text) | 70 | **FAIL** |
| C9 | agent and caller do not talk over each other for long (one plain sentence) | <= 600 ms | median 279 ms, max 289 ms; over 600 ms in 0 of 56 | 56 | **pass** |
| C10 | never more than one silence gap of dead air | <= 9 s | max 6099 ms | 540 | **pass** |
| C11 | the agent never says the same clip twice in a row | 0 | 0 of 540; clips: {} | 540 | **pass** |
| C12 | the goodbye is always heard whole | 100 % | chopped in 0 of 450 | 450 | **pass** |
| C13 | the log knows how much of a cut clip was heard | within 60 ms | max error 1 ms | 540 | **pass** |
| C14 | a key pressed while talking wins over the words | 100 % | 0 of 0 | 0 | **pass** |
| C15 | after the caller hangs up the agent says nothing more | at most the clip in flight | 88 of 90 | 90 | **FAIL** |
| C16 | input in the first 250 ms of a clip is not lost | speech is still heard | keys: took 0 of 0 (rest dropped by the guard, on purpose); speech lost in 0 of 0 | 0 | **pass** |
| C17 | a second cut-in right after the first is heard too | 100 % | 0 of 0 | 0 | **pass** |

## Failing checks: where, and one case to replay

- **C4.voice** speech gets through at every place the agent talks (goodbye aside) [voice]
  - where: {'voice:results_exact_preamble': 2, 'voice:scheme:name': 2, 'voice:scheme:summary': 2, 'voice:section_menu': 1, 'voice:section_source_frame': 1, 'voice:scheme:benefit_text': 1}
  - replay: `python -m tools.barge_eval --show spoken:voice --lang hi --bed 0 --at 7:300 --kind voice_question`
- **C8** the agent starts to reply soon after the caller stops talking
  - where: {'voice_qa:no_more_schemes': 4, 'voice_qa:anything_else': 4, 'voice_qa:opener_short_prompt': 4, 'voice_qa:state_q_maharashtra': 4, 'voice_qa:box_question': 4, 'voice_qa:results_exact_preamble': 4, 'voice_qa:scheme:name': 4, 'voice_qa:scheme:summary': 4}
  - replay: `python -m tools.barge_eval --show question:voice_qa --lang en --bed 0 --at 22:850 --kind voice_question`
- **C15** after the caller hangs up the agent says nothing more
  - where: {'voice_qa:one_moment': 2}
  - replay: `python -m tools.barge_eval --show question:voice_qa --lang en --bed 0 --at 9:300 --kind hangup`

Run: 540 scenarios in 2 s.
