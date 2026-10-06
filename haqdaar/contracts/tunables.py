"""haqdaar/contracts/tunables.py

UNOWNED. Every tunable lives here and changes with no ceremony at all.
Hardcode nothing.
"""
from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

# Telephony & stream tunables (06-BUILD-PLAN.md Step 1)
TONE_FREQ_HZ: int = int(os.environ.get("TONE_FREQ_HZ", 440))
TONE_DURATION_S: float = float(os.environ.get("TONE_DURATION_S", 1.0))
TONE_AMPLITUDE: float = float(os.environ.get("TONE_AMPLITUDE", 0.5))
NGROK_DOMAIN: str = os.environ.get("NGROK_DOMAIN", "")
# D12: which module in haqdaar/audio/telephony/ talks to the phone line.
PHONE_PROVIDER: str = os.environ.get("PHONE_PROVIDER", "twilio")

# Timing and thresholds (04-INTERFACES.md § What is not frozen)
# Step 7: caller questions. Every switch is off by default; off means the call is as before.
def _on(name: str) -> bool:
    return os.environ.get(name, "false").strip().lower() in ("1", "true", "yes", "on")


QA_ENABLED: bool = _on("QA_ENABLED")            # 7.1 answer a caller's question (text)
TALK_ONLY: bool = _on("TALK_ONLY")              # 7.13 talk like a person: after the language pick, no keys
# 7.1 / 1.4: speech -> English -> work -> caller's language. On by default in a talk call (owner, D1: ONE path
# for every language, Hindi and English too). ENGLISH_PIPE=false brings back the direct way for Hindi, Marathi
# and English; a caller in any other Sarvam language always goes through English (the talk is written in those three).
ENGLISH_PIPE: bool = os.environ.get("ENGLISH_PIPE", "true" if TALK_ONLY else "false").strip().lower() in ("1", "true", "yes", "on")
QA_SPEAK: bool = _on("QA_SPEAK") or TALK_ONLY   # 7.2 say the answer aloud on a real call (live speech)
SPEECH_CUT_IN: bool = _on("SPEECH_CUT_IN")      # 7.2 the caller's voice stops a playing clip
QA_SEARCH: bool = _on("QA_SEARCH")              # 7.3 find the scheme by search when too many are left
TALK_TIMEOUT_S: float = float(os.environ.get("TALK_TIMEOUT_S", 6.0))        # one model call of a talk turn
# "One moment" while the line is checking. The words reach the engine about 1 s after the caller stops, so 1.6 here
# is about 2.7 s of quiet for the caller. A usual reply sounds before that, so the line is said only on a slow turn,
# and then it is said whole: the answer waits behind it (it was cut mid-word on the 5 Oct call at 1.0).
# If still nothing is said, it is said again every TALK_ONE_MOMENT_AGAIN_S.
TALK_ONE_MOMENT_S: float = float(os.environ.get("TALK_ONE_MOMENT_S", 1.6))
TALK_ONE_MOMENT_AGAIN_S: float = float(os.environ.get("TALK_ONE_MOMENT_AGAIN_S", 4.0))
TALK_MAX_SENTENCES: int = int(os.environ.get("TALK_MAX_SENTENCES", 7))      # full details of a scheme + one closing question
TALK_MAX_WORDS: int = int(os.environ.get("TALK_MAX_WORDS", 110))
TALK_SENTENCE_WORDS: int = int(os.environ.get("TALK_SENTENCE_WORDS", 24))   # a longer sentence is refused: it is a phone call
TALK_LOG_CHARS: int = int(os.environ.get("TALK_LOG_CHARS", 1500))           # how much of the call log the model reads
TALK_MAX_TURNS: int = int(os.environ.get("TALK_MAX_TURNS", 40))             # a talk call always ends
TALK_MAX_QUESTIONS: int = int(os.environ.get("TALK_MAX_QUESTIONS", 3))   # 1.3a: at most 3 questions a talk call
# 3.1 / 3.2 / 3.3 (Phase 3): keys and talk switch inside one call. In a talk call key KEYS_KEY goes to keys
# with the answers so far; words in the keys part go back to talk. Off: key 6 is "keys are off" again.
KEYS_IN_TALK: bool = os.environ.get("KEYS_IN_TALK", "true" if TALK_ONLY else "false").strip().lower() in ("1", "true", "yes", "on")
KEYS_KEY: str = os.environ.get("KEYS_KEY", "6")
# 3.5: this many questions in a talk call with no usable reply: the line says "press 6 for keys", once a call.
TALK_KEYS_OFFER_AFTER: int = int(os.environ.get("TALK_KEYS_OFFER_AFTER", 3))
# 1.5: the model is shown the top 5 PARTS of schemes (search by part), not whole scheme cards. False: whole
# cards, as before. The quick way back if a live call gets worse.
TALK_CHUNKS: bool = os.environ.get("TALK_CHUNKS", "true").strip().lower() in ("1", "true", "yes", "on")
# Tried in order; the next one only when Groq says "too many requests" (8000 tokens a minute per model).
# Order by speed measured 5 Oct on real talk prompts: qwen 0.5-0.6 s, gpt-oss-120b 0.7-1.3 s, gpt-oss-20b 0.9-2.8 s.
TALK_MODELS: str = os.environ.get("TALK_MODELS", "qwen/qwen3.8-27b,openai/gpt-oss-120b,openai/gpt-oss-20b")
# A "muse:<model name>" entry in TALK_MODELS is served by Muse (haqdaar/model/muse_talk.py), inside its rupee caps.
# Measured 5 Oct on a full talk prompt, muse-spark-1.3-contributor: 8.6 s at "minimal", 16.8 s at "low" ("none" is
# refused). Too slow for the front of the chain; it is not in the default chain. It needs its own, longer timeout.
TALK_MUSE_EFFORT: str = os.environ.get("TALK_MUSE_EFFORT", "minimal")
TALK_MUSE_TIMEOUT_S: float = float(os.environ.get("TALK_MUSE_TIMEOUT_S", 12.0))
TALK_HOLD_S: float = float(os.environ.get("TALK_HOLD_S", 120.0))   # 1.8: "hold on": the quiet rule does not start for this long
TALK_SLOW_PACE: float = float(os.environ.get("TALK_SLOW_PACE", 0.8))   # 1.8 (B): the voice pace after "speak slowly" (LIVE_TTS_PACE is 1.0)
TALK_OFF_TOPIC_END: int = int(os.environ.get("TALK_OFF_TOPIC_END", 3))   # 1.8 (B): this many off-topic turns in a row end the call politely
TALK_END_WAIT_MS: int =int(os.environ.get("TALK_END_WAIT_MS", 600))        # quiet that ends the caller's turn in a talk call (keys call: 800)
# 4.2 / 4.3: in a talk call the agent may offer an SMS link for a photo, and the answer to a photo
# opens the next call. Off: none of it runs (key 9 is "keys are off" again).
PHOTO_IN_CALL: bool = os.environ.get("PHOTO_IN_CALL", "true" if TALK_ONLY else "false").strip().lower() in ("1", "true", "yes", "on")
PHOTO_PENDING_S: float = float(os.environ.get("PHOTO_PENDING_S", 1800.0))   # a call-back waiting longer than this is dropped
PHOTO_SURE_MIN: float = float(os.environ.get("PHOTO_SURE_MIN", 0.4))        # the reader was less sure than this: a bad photo
# The desk now writes the call-back text in the case's own language (pass 4), so this is off. On: an English
# text goes through the translate step (1.4) for a caller of another language.
PHOTO_BACK_TRANSLATE: bool = os.environ.get("PHOTO_BACK_TRANSLATE", "false").strip().lower() in ("1", "true", "yes", "on")
QA_MAX_PER_CALL: int = int(os.environ.get("QA_MAX_PER_CALL", 5))
QA_MAX_SCHEMES: int = int(os.environ.get("QA_MAX_SCHEMES", 4))
QA_TIMEOUT_S: float = float(os.environ.get("QA_TIMEOUT_S", 4.0))
QA_MAX_WORDS: int = int(os.environ.get("QA_MAX_WORDS", 40))
QA_BACKUP_MODEL: str = os.environ.get("QA_BACKUP_MODEL", "qwen/qwen3.8-27b")
QA_TRANSLATE_TIMEOUT_S: float = float(os.environ.get("QA_TRANSLATE_TIMEOUT_S", 3.0))
QA_TTS_TIMEOUT_S: float = float(os.environ.get("QA_TTS_TIMEOUT_S", 4.0))
CUT_IN_MIN_MS: int = int(os.environ.get("CUT_IN_MIN_MS", 240))   # voice this long stops the clip
CUT_IN_GAP_MS: int = int(os.environ.get("CUT_IN_GAP_MS", 200))   # quiet this long ends a short burst (two coughs do not add up)
# 7.14 (B5) cut-in with a strict gate, in a talk call. Off: strict turns (the agent does not listen while it talks).
CUT_IN_GATE: bool = _on("CUT_IN_GATE")
CUT_IN_GATE_MS: int = int(os.environ.get("CUT_IN_GATE_MS", 600))       # real voice this long pauses the agent
CUT_IN_GATE_GAP_MS: int = int(os.environ.get("CUT_IN_GATE_GAP_MS", 300))   # quiet this long ends a burst of voice
CUT_IN_GATE_WORDS: int = int(os.environ.get("CUT_IN_GATE_WORDS", 2))   # real words that make it the caller's turn
SILERO_ON: float = float(os.environ.get("SILERO_ON", 0.5))             # Silero's "this is a voice" score to start
SILERO_OFF: float = float(os.environ.get("SILERO_OFF", 0.35))          # and to stay one
CUT_IN_FALSE_MAX: int = int(os.environ.get("CUT_IN_FALSE_MAX", 2))   # a cut with no words: the clip is said again, this often per wait
# The "this call is recorded" line after the language pick. Off (owner, 4 Oct 2026: not needed
# for now). The line and its clips stay; CONSENT_LINE=true plays it again.
CONSENT_LINE: bool = _on("CONSENT_LINE")
# The languages a caller is offered at the greeting, in order: the first is key 1, the next key 2.
# Marathi is paused (owner, 4 Oct 2026): its lines and clips stay, it is just not offered and
# `*` does not switch to it. To bring it back: LANGS_OFFERED=hi,mr,en and change the English
# greeting part in audio/lines.yaml to "press 3".
LANGS_OFFERED: tuple[str, ...] = tuple(
    l.strip() for l in os.environ.get("LANGS_OFFERED", "hi,en").split(",") if l.strip()
)


# 3.4: the keys of the five-language greeting of a talk call, in the order it speaks them.
TALK_LANG_KEYS: tuple[str, ...] = tuple(
    l.strip() for l in os.environ.get("TALK_LANG_KEYS", "hi,en,mr,gu,ta").split(",") if l.strip()
)


def turn0_keys() -> dict[str, str]:
    """Greeting key -> language, from LANGS_OFFERED as it is now. A talk call that says the
    five-language greeting uses TALK_LANG_KEYS instead: key 1 is the first language it speaks."""
    langs = TALK_LANG_KEYS if TALK_ONLY and GREETING_FIVE else LANGS_OFFERED
    return {str(i + 1): lang for i, lang in enumerate(langs)}


KEY_REPEAT_MS: int = int(os.environ.get("KEY_REPEAT_MS", 300))
KEY_GUARD_MS: int = int(os.environ.get("KEY_GUARD_MS", 250))
ENDPOINT_MS: int = int(os.environ.get("ENDPOINT_MS", 700))
MODEL_TIMEOUT_S: float = float(os.environ.get("MODEL_TIMEOUT_S", 2.0))
STT_TIMEOUT_S: float = float(os.environ.get("STT_TIMEOUT_S", 5.0))
SILENCE_GAP_S: int = int(os.environ.get("SILENCE_GAP_S", 6))
TURN0_GAP_S: int = int(os.environ.get("TURN0_GAP_S", 4))
SILENCE_REMIND_S: float = float(os.environ.get("SILENCE_REMIND_S", 30))
SILENCE_HANGUP_S: float = float(os.environ.get("SILENCE_HANGUP_S", 60))
MAX_TURNS: int = int(os.environ.get("MAX_TURNS", 8))
MAX_QUESTIONS: int = int(os.environ.get("MAX_QUESTIONS", 6))
STOP_SURVIVORS: int = int(os.environ.get("STOP_SURVIVORS", 4))
NEAREST_CAP: int = int(os.environ.get("NEAREST_CAP", 2))
OVERFLOW_READ_CAP: int = int(os.environ.get("OVERFLOW_READ_CAP", 3))
READBACK_REPLAY_MAX: int = int(os.environ.get("READBACK_REPLAY_MAX", 2))
CONFIRM_REPEAT_MAX: int = int(os.environ.get("CONFIRM_REPEAT_MAX", 3))
MODEL_FAILURES_TO_KEYPAD: int = int(os.environ.get("MODEL_FAILURES_TO_KEYPAD", 2))
UNCLEAR_TRIES: int = int(os.environ.get("UNCLEAR_TRIES", 3))
KEYPAD_CARDINALITY_MAX: int = int(os.environ.get("KEYPAD_CARDINALITY_MAX", 9))
ALIAS_FLOOR: int = int(os.environ.get("ALIAS_FLOOR", 3))
CALL_CEILING_S: int = int(os.environ.get("CALL_CEILING_S", 600))

# Step 1.0: safe and smooth line. Each switch is ON unless set to false.
def _off(name: str) -> bool:
    return os.environ.get(name, "true").strip().lower() in ("0", "false", "no", "off")


PHONE_CHECK: bool = not _off("PHONE_CHECK")           # /answer must be signed by the phone provider; /stream takes only a call /answer saw
STREAM_START_WAIT_S: float = float(os.environ.get("STREAM_START_WAIT_S", 5.0))   # a socket that sends no start is closed
LINE_RECONNECT: bool = not _off("LINE_RECONNECT")     # a dropped stream is opened again and the call goes on
LINE_RECONNECT_WAIT_S: float = float(os.environ.get("LINE_RECONNECT_WAIT_S", 60.0))   # how long a dropped call is kept
LINE_RECONNECT_TRIES: int = int(os.environ.get("LINE_RECONNECT_TRIES", 3))       # then "the line dropped" and hang up
NET_KEEPALIVE_S: float = float(os.environ.get("NET_KEEPALIVE_S", 60.0))          # an open connection to Sarvam / Groq is kept this long
NET_CHECK_TRIES: int = int(os.environ.get("NET_CHECK_TRIES", 3))                 # make call-me: tiny requests before the ring
NET_CHECK_SLOW_S: float = float(os.environ.get("NET_CHECK_SLOW_S", 2.0))         # a slower reply than this = "weak network"

# Door A matching thresholds (4.3)
DOOR_A_EXACT_SCORE: float = float(os.environ.get("DOOR_A_EXACT_SCORE", 1000.0))
DOOR_A_ALIAS_SCORE_BASE: float = float(os.environ.get("DOOR_A_ALIAS_SCORE_BASE", 500.0))
DOOR_A_SCORE_FLOOR: float = float(os.environ.get("DOOR_A_SCORE_FLOOR", 30.0))
DOOR_A_TIE_BAND: float = float(os.environ.get("DOOR_A_TIE_BAND", 0.90))
DOOR_A_MIN_TOKEN_OVERLAP: int = int(os.environ.get("DOOR_A_MIN_TOKEN_OVERLAP", 2))

# Audio cache and storage tiers (03-ARCHITECTURE.md §10.1, 04-INTERFACES.md)
AUDIO_CACHE_MB: int = int(os.environ.get("AUDIO_CACHE_MB", 64))  # 3.8: LRU of scheme clips
AUDIO_PREFETCH_ON_STOP: bool = (
    os.environ.get("AUDIO_PREFETCH_ON_STOP", "true").lower() in ("true", "1", "yes")
)
AUDIO_TIER2: str = os.environ.get("AUDIO_TIER2", "none")  # "none" | "s3" | "r2"
# 3.8: off. Filling RAM with every clip does not scale past the 12 schemes; pin fixed lines only.
AUDIO_WARM_ON_BOOT: bool = (
    os.environ.get("AUDIO_WARM_ON_BOOT", "false").lower() in ("true", "1", "yes")
)

# Render and audio format constants
SAMPLE_RATE: int = int(os.environ.get("SAMPLE_RATE", 8000))
TAIL_PAD_MS: int = int(os.environ.get("TAIL_PAD_MS", 120))
# 7.6: when a clip loads, quiet at its start and end is cut to this gap. 120 = TAIL_PAD_MS, so the
# tail pad the renderer adds stays. QUIET_LEVEL is the loudest mu-law level (0-127) still counted as quiet.
TRIM_EDGE_MS: int = int(os.environ.get("TRIM_EDGE_MS", 120))
TRIM_QUIET_LEVEL: int = int(os.environ.get("TRIM_QUIET_LEVEL", 15))
# Sarvam TTS (plan 2.1). The bot speaks of itself as a woman in Hindi and Marathi ("पाई",
# "सांगते"), so every speaker here must be a woman's voice. One speaker per language; change one
# and only that language re-renders, because the speaker and pace are part of the render key.
TTS_MODEL: str = os.environ.get("TTS_MODEL", "bulbul:v3")
DEFAULT_TTS_MODEL: str = os.environ.get("DEFAULT_TTS_MODEL", f"sarvam:{TTS_MODEL}")
TTS_SPEAKERS: dict[str, str] = {
    "en": os.environ.get("TTS_SPEAKER_EN", "priya"),
    "hi": os.environ.get("TTS_SPEAKER_HI", "priya"),
    "mr": os.environ.get("TTS_SPEAKER_MR", "priya"),
}
# 15 Sep: the owner said the voice was too fast at 1.0.
TTS_PACE: float = float(os.environ.get("TTS_PACE", 0.9))
# Live voice only. The 582 recorded clips keep TTS_PACE (it is part of their render key).
# 7.14: play the live voice as its sound arrives (first sound ~0.4 s in, not after the whole sentence). Off: as before.
LIVE_TTS_STREAM: bool = os.environ.get("LIVE_TTS_STREAM", "true" if TALK_ONLY else "false").strip().lower() in ("1", "true", "yes", "on")
LIVE_TTS_PACE: float = float(os.environ.get("LIVE_TTS_PACE", 1.0 if TALK_ONLY else TTS_PACE))
# 1.2 (5 Oct): in a talk call the speech service is told no language after the greeting either; a
# turn of 3 or more real words in Hindi, Marathi or English makes that the language of the reply.
LANG_EACH_TURN: bool = os.environ.get("LANG_EACH_TURN", "true" if TALK_ONLY else "false").strip().lower() in ("1", "true", "yes", "on")
# 1.1 part B (5 Oct): the greeting of a talk call, said by the live voice and kept on disk after
# the first call. (Sarvam language code, words.) Gujarati and Tamil say the short line. Hindi, Marathi
# and English add "for keys, press 6" when KEYS_IN_TALK is on (a changed line is rendered once, on the
# first call). Any line that fails: the recorded greeting is said.
GREETING_FIVE: bool = os.environ.get("GREETING_FIVE", "true" if TALK_ONLY else "false").strip().lower() in ("1", "true", "yes", "on")
_FOR_KEYS = {"hi": "बटन के लिए {} दबाएँ।", "en": "For keys, press {}.", "mr": "बटणांसाठी {} दाबा."}


def _with_keys(lang: str, text: str) -> str:
    return f"{text} {_FOR_KEYS[lang].format(KEYS_KEY)}" if KEYS_IN_TALK else text


GREETING_LINES: tuple[tuple[str, str], ...] = (
    ("hi-IN", _with_keys("hi", "हक़दार में आपका स्वागत है। अपनी भाषा में बोलिए।")),
    ("en-IN", _with_keys("en", "Welcome to Haqdaar. Speak in English or your own language.")),
    ("mr-IN", _with_keys("mr", "हक्कदार मध्ये आपले स्वागत आहे. तुमच्या भाषेत बोला.")),
    ("gu-IN", "હકદારમાં સ્વાગત છે. તમારી ભાષામાં બોલો."),
    ("ta-IN", "ஹக்தார் வரவேற்கிறது. உங்கள் மொழியில் பேசுங்கள்."),
) + ((
    # The other six Sarvam languages, the short line only. Off by default: eleven lines are about 25 s.
    # A caller who speaks one of them is still heard and answered in it. Draft words: a speaker checks them.
    ("bn-IN", "হকদারে স্বাগতম। আপনার ভাষায় বলুন।"),
    ("kn-IN", "ಹಕ್ದಾರ್‌ಗೆ ಸ್ವಾಗತ. ನಿಮ್ಮ ಭಾಷೆಯಲ್ಲಿ ಮಾತನಾಡಿ."),
    ("ml-IN", "ഹഖ്ദാറിലേക്ക് സ്വാഗതം. നിങ്ങളുടെ ഭാഷയിൽ സംസാരിക്കൂ."),
    ("od-IN", "ହକଦାରକୁ ସ୍ୱାଗତ। ଆପଣଙ୍କ ଭାଷାରେ କୁହନ୍ତୁ।"),
    ("pa-IN", "ਹੱਕਦਾਰ ਵਿੱਚ ਜੀ ਆਇਆਂ ਨੂੰ। ਆਪਣੀ ਭਾਸ਼ਾ ਵਿੱਚ ਬੋਲੋ।"),
    ("te-IN", "హక్దార్‌కు స్వాగతం. మీ భాషలో మాట్లాడండి."),
) if _on("GREETING_ALL_LANGS") else ())
TTS_WORKERS: int = int(os.environ.get("TTS_WORKERS", 3))
TTS_TIMEOUT_S: float = float(os.environ.get("TTS_TIMEOUT_S", 60))
TTS_MAX_ATTEMPTS: int = int(os.environ.get("TTS_MAX_ATTEMPTS", 5))
TTS_RETRY_BACKOFF_S: float = float(os.environ.get("TTS_RETRY_BACKOFF_S", 2.0))
# 30 Sep: Sarvam sent 429 after ~50 requests in the first minute. Start requests at least this
# far apart across all workers (~46 a minute), and wait longer after a 429.
TTS_MIN_GAP_S: float = float(os.environ.get("TTS_MIN_GAP_S", 1.3))
TTS_429_WAIT_S: float = float(os.environ.get("TTS_429_WAIT_S", 15.0))
# "#" twice replays the last line slower, stretched at play time (plan 2.5).
SLOW_PACE: float = float(os.environ.get("SLOW_PACE", 0.8))
# Audio goes down the line in frames of this many mu-law bytes (8000 = 1 s), each clip then a mark.
FRAME_BYTES: int = int(os.environ.get("FRAME_BYTES", 8000))
# After the goodbye, wait at most this long for it to finish playing before hanging up.
HANGUP_WAIT_S: float = float(os.environ.get("HANGUP_WAIT_S", 15.0))
# Real phone calls write their turn log here (logs/server.log has the line-by-line events).
CALL_LOGS_DIR: str = os.environ.get("CALL_LOGS_DIR", "logs/calls")

# Voice IDs per language, as they go into the render key.
VOICE_IDS: dict[str, str] = {
    lang: f"{speaker}@{TTS_PACE}" for lang, speaker in TTS_SPEAKERS.items()
}

# Directories and paths
AUDIO_DIR: str = os.environ.get("AUDIO_DIR", "audio")
SNAPSHOTS_DIR: str = os.environ.get("SNAPSHOTS_DIR", "snapshots")
RAW_CACHE_DIR: str = os.environ.get("RAW_CACHE_DIR", "data_cache/raw")
EXTRACT_CACHE_DIR: str = os.environ.get("EXTRACT_CACHE_DIR", "data_cache/extract")
DERIVED_DIR: str = os.environ.get("DERIVED_DIR", "data_cache/derived")
REPORTS_DIR: str = os.environ.get("REPORTS_DIR", "data_cache/reports")

# Groq model and extraction pipeline (06-BUILD-PLAN.md Step 8)
# Plan 3.1 discovery: myscheme search, 100 a page, one page every 2 s.
DISCOVER_PAGE_SIZE: int = int(os.environ.get("DISCOVER_PAGE_SIZE", 100))
DISCOVER_PAGE_GAP_S: float = float(os.environ.get("DISCOVER_PAGE_GAP_S", 2.0))
DISCOVER_TIMEOUT_S: float = float(os.environ.get("DISCOVER_TIMEOUT_S", 30.0))

GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_REASONING_EFFORT: str = os.environ.get("GROQ_REASONING_EFFORT", "low")
GROQ_POLITE_DELAY_S: float = float(os.environ.get("GROQ_POLITE_DELAY_S", 2.0))
SUMMARY_WORD_TARGET: int = int(os.environ.get("SUMMARY_WORD_TARGET", 35))
SUMMARY_WORD_TOLERANCE: int = int(os.environ.get("SUMMARY_WORD_TOLERANCE", 10))
GROQ_MAX_RETRIES: int = int(os.environ.get("GROQ_MAX_RETRIES", 6))
GROQ_TIMEOUT_S: float = float(os.environ.get("GROQ_TIMEOUT_S", 45.0))
GROQ_RETRY_SLEEP_S: float = float(os.environ.get("GROQ_RETRY_SLEEP_S", 2.0))
GROQ_429_DEFAULT_WAIT_S: float = float(os.environ.get("GROQ_429_DEFAULT_WAIT_S", 5.0))
GROQ_429_MIN_WAIT_S: float = float(os.environ.get("GROQ_429_MIN_WAIT_S", 1.0))
GROQ_429_PAD_S: float = float(os.environ.get("GROQ_429_PAD_S", 1.5))
ALIAS_BENEFITS_CHARS: int = int(os.environ.get("ALIAS_BENEFITS_CHARS", 300))
# An alias on this many schemes or more is a category word and is dropped from all (T12)
ALIAS_CATEGORY_WORD_MIN: int = int(os.environ.get("ALIAS_CATEGORY_WORD_MIN", 3))
# A scrape/derive run fails only if fewer than this many schemes survive quarantine (D2)
MIN_SCHEMES: int = int(os.environ.get("MIN_SCHEMES", 8))

# Spoken cards (step 1.9, D3). A card is read aloud on a phone call, so it is capped in words;
# CARD_OVERLAP_MIN is the share of a card's content words that must also appear in the source,
# which is how a card is held to the source instead of being trusted.
CARD_MAX_WORDS: int = int(os.environ.get("CARD_MAX_WORDS", 55))
CARD_OVERLAP_MIN: float = float(os.environ.get("CARD_OVERLAP_MIN", 0.6))
CARDS_FILE: str = os.environ.get("CARDS_FILE", "data_cache/derived/cards.jsonl")


# Translation (plan item 1.9, D4). Hindi and Marathi come from Sarvam Translate, not Groq, so
# Groq's small daily budget stays with the live call. Every number below was probed against the
# live API on 20 Sep 2026 and written to .agent/NOTES.md; TRANSLATE_CHAR_LIMIT in particular is
# the API's own cap (2001 characters returns a 400), not a guess.
TRANSLATE_MODEL: str = os.environ.get("TRANSLATE_MODEL", "sarvam-translate:v1")
TRANSLATE_CHAR_LIMIT: int = int(os.environ.get("TRANSLATE_CHAR_LIMIT", 2000))
TRANSLATE_TIMEOUT_S: float = float(os.environ.get("TRANSLATE_TIMEOUT_S", 60))
TRANSLATE_MIN_GAP_S: float = float(os.environ.get("TRANSLATE_MIN_GAP_S", 0.2))
# One read timed out on the first real run of the 12. A timeout or a 5xx/429 is retried; a 402
# (no credits) or a 400 (bad input) is final and is never retried.
TRANSLATE_MAX_ATTEMPTS: int = int(os.environ.get("TRANSLATE_MAX_ATTEMPTS", 3))
TRANSLATE_RETRY_BACKOFF_S: float = float(os.environ.get("TRANSLATE_RETRY_BACKOFF_S", 2.0))
# Cache invalidation lives with the other prompt versions, in p2_derive.PROMPT_VERSIONS
# ("translate_hi"/"translate_mr"): bump it there after a model or numeral-format change.

# Gates (plan item 1.10, D5). Five gates decide whether a scheme may be spoken in a language.
# A number below GATE_NUMBER_MIN is allowed to arrive as a word: Sarvam turns "3 installments"
# into "तीन", seen first-hand on pm-kisan. Amounts (6000, 200000) are never spelled out, so
# anything at or above the floor must survive the translation as digits.
GATE_NUMBER_MIN: int = int(os.environ.get("GATE_NUMBER_MIN", 100))
GATE_LENGTH_RATIO_MAX: float = float(os.environ.get("GATE_LENGTH_RATIO_MAX", 1.6))
GATE_SCRIPT_MIN: float = float(os.environ.get("GATE_SCRIPT_MIN", 0.8))
# G3 counts words, not characters (Devanagari uses more characters per word), and skips text
# shorter than this: turning "Aadhaar Card." into a spoken sentence must add words.
GATE_LENGTH_MIN_WORDS: int = int(os.environ.get("GATE_LENGTH_MIN_WORDS", 12))

# Plan 3.3: Playwright's own Chromium is not installed on the owner's Mac; the system Chrome is.
# None = Playwright's bundled browser.
SCRAPE_BROWSER_CHANNEL: str | None = "chrome"

# Plan 3.4 / 3.5 (owner, 30 Sep): Muse Spark 1.3 Contributor does the cards and the translation,
# at "high" reasoning, with a hard ₹60 cap over every run (haqdaar/data/pipeline/muse.py).
# "groq" / "sarvam" bring the old clients back.
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "muse")
TRANSLATE_PROVIDER: str = os.environ.get("TRANSLATE_PROVIDER", "muse")
MUSE_MODEL: str = os.environ.get("MUSE_MODEL", "muse-spark-1.3-contributor")
MUSE_REASONING_EFFORT: str = os.environ.get("MUSE_REASONING_EFFORT", "high")
MUSE_CAP_INR: float = float(os.environ.get("MUSE_CAP_INR", 60.0))
# Owner, 2 Oct: no more than ₹30 of Muse in one day. The day is counted in India time and
# rolls at 05:00, not at midnight, because the owner works at night.
MUSE_DAILY_CAP_INR: float = float(os.environ.get("MUSE_DAILY_CAP_INR", 30.0))
MUSE_DAY_START_HOUR_IST: int = 5
MUSE_USD_PER_M_IN: float = 0.10
MUSE_USD_PER_M_OUT: float = 0.20
USD_TO_INR: float = 90.0  # rounded up, so the cap trips a little early rather than late
MUSE_TIMEOUT_S: float = 180.0  # "high" reasoning on a long card prompt can think for a while
MUSE_POLITE_DELAY_S: float = 1.0
MUSE_MAX_RETRIES: int = 5
MUSE_RETRY_SLEEP_S: float = 3.0
MUSE_429_WAIT_S: float = 20.0

# Plan 5.3: `make run` starts the server again after a crash (tools/keep_running.py).
RESTART_WAIT_S: float = 2.0
RESTART_MAX_STOPS: int = 5      # this many stops inside the window = a crash loop: give up
RESTART_WINDOW_S: float = 60.0
