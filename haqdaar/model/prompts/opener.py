"""haqdaar/model/prompts/opener.py

Prompt builder for opener utterances in HAQDAAR v2.
"""
from __future__ import annotations

from haqdaar.model.prompts.kinds import english_note


def build_opener_prompt(transcript: str, lang: str = "en", english: bool = False) -> str:
    """Build user prompt for opener extraction."""
    note = english_note(lang) if english else ""
    return f"""The caller gave this opening statement (language: {lang}):
\"\"\"{transcript}\"\"\"
{note}
Task:
Extract any demographic facets or scheme requests explicitly mentioned by the caller.
Return a JSON object with a single key "stamps" containing a list of objects.
Each object must have:
- "box": one of ("state", "gender", "social_category", "occupation", "category", "age", "income_band", "scheme")
- "value": the standardized value code for that box
- "span": the EXACT words from the transcript that stated this facet

If no known facets are mentioned, return:
{{"stamps": []}}

JSON Output:"""
