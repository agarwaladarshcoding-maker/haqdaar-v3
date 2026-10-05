# NOTES-lang (branch step-1-lang, 6 Oct night): 1.4 wired, every Sarvam language, 1.7 checks

- ONE language list: haqdaar/contracts/types.py SARVAM_CODES (hi mr en bn gu kn ml od pa ta te -> xx-IN).
  Read by ear.SARVAM_LANG (+ normalize_lang), render.TTS_LANG (= live_tts voice), translate.TARGET_CODES
  (all but en), middle.LANGS. lang_words.NAMES got the 8 new languages (names in Latin, Devanagari, own script).
  render's recorded clips stay hi/mr/en (texts.LANGS): no paid render.
- talk.py: NATIVE = (hi, mr, en). _work(): "en" when ENGLISH_PIPE is on (lang != en), or lang not in NATIVE.
  The model prompt and the checks (check_answer, forbidden words, code_name) use the work language.
  hi/mr with the pipe: the checked English say is translated in _decide (before the fixed lines are added:
  those are the hand-written ones). Other languages: _speak translates the whole say at its top (all the talk's
  words for them are English). Translate failure / guard refusal: the English sentence is said + a blocked row
  "translate". Never silence: the filler ("one moment") runs while translate runs (it is before the first voice).
  act row gets translate_ms.
- ENGLISH_PIPE default: true when TALK_ONLY (D1: one path). Tests and talk-eval set TALK_ONLY by setattr, so
  they keep the pipe off unless set. ENGLISH_PIPE=false = direct way for hi/mr/en.
- phone._clips: a recorded clip for a caller in a non-recorded language is the English clip (one moment,
  goodbye, unclear): was silence ("no clip").
- Greeting: GREETING_ALL_LANGS=true adds short lines for bn kn ml od pa te (draft words, off by default: 11 lines
  ~25 s). The talk's own hello is translated for them, so each language is greeted.
- worktree had no audio/ link: added symlink audio -> ~/code/haqdaar-v2/audio (as in the cut-in folder).
- Known limits: guard_ok knows scheme names only in en/hi/mr/gu/ta: a sentence naming a scheme in kn/te/... is
  kept in English unless the name stays Latin. Number WORDS of the new languages are not known to the guard
  (digits are): such a sentence falls back to English. "same_again" never fires in pipe mode (last_say holds
  the translated text). LANG_EACH_TURN now follows a caller into any of 11 languages (a wrong guess by Sarvam
  on a 3-word turn could switch it).
- No real Sarvam call was made on this branch (network to Sarvam is blocked from this session). Real translate,
  voice and hearing in the 8 new languages are NOT checked; only faked tests.
- A script run as `python file.py` from outside the repo imports the MAIN folder's haqdaar (the venv is the main
  folder's); pytest and `python -m tools.x` from the side folder use the side folder.
- Tests that held the old rule "any code but hi/mr/en is Hindi" were changed: test_step11_greeting (gu-IN -> gu,
  ta-IN -> ta), test_step12_language (gu-IN now followed).
