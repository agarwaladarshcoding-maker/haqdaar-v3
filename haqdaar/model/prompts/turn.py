"""haqdaar/model/prompts/turn.py

Prompt builder for question turns in HAQDAAR v2.
Classifies utterances into five classes with precedence:
META > ANSWER > CLARIFY > REPEAT > UNCLEAR
"""
from __future__ import annotations

from typing import Sequence


def build_turn_prompt(
    transcript: str,
    box: str,
    values: Sequence[str],
    window: Sequence[str] | None = None,
    ask_count: int = 0,
) -> str:
    """Build user prompt for question turn classification and extraction."""
    window_lines = "\n".join(f"- {w}" for w in (window or []))
    if not window_lines:
        window_lines = "(none)"

    val_str = ", ".join(values)

    return f"""The caller was asked about box: "{box}".
Valid closed-set choices for this box: [{val_str}].
Question rephrase count: {ask_count}.
Recent conversation history (last 2 turns):
{window_lines}

Caller utterance:
\"\"\"{transcript}\"\"\"

Classify the utterance into exactly one of these five classes:
1. "META": Caller issued a command (e.g. change language, stop, agent, restart).
2. "ANSWER": Caller provided a direct answer or correction for the question box (or another box).
3. "CLARIFY": Caller asked for explanation or meaning of the question (e.g. "what do you mean?", "samjha nahi", "kya matlab?").
4. "REPEAT": Caller asked to repeat the question (e.g. "repeat please", "fir se bolo", "pardon").
5. "UNCLEAR": Utterance is unintelligible or unrelated.

Return a JSON object:
- For META: {{"class": "META", "command": "<command>"}}
- For ANSWER: {{"class": "ANSWER", "box": "<box_name>", "value": "<closed_set_value>", "span": "<exact substring>"}}
- For CLARIFY: {{"class": "CLARIFY", "box": "{box}"}}
- For REPEAT: {{"class": "REPEAT"}}
- For UNCLEAR: {{"class": "UNCLEAR", "reason": "<reason>"}}

JSON Output:"""
