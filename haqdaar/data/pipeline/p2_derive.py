"""haqdaar/data/pipeline/p2_derive.py

myScheme derivation pass (Step 8, 05-DATA-CONTRACT.md, T06, T07, T10, T11, T12, T21, T22, T24).
Build pipeline tool — NEVER imported by runtime code.

Hard rules:
  - Source of truth: only data_cache/raw/*.json (myscheme.gov.in). No third-party datasets.
  - Fail loudly: on any failure, fail loudly and write nothing. Never invent eligibility rules.
  - Groq rate limits: 1,000 requests/day, 8,000 TPM. The cache is load-bearing.
  - Re-runs must cost ZERO API calls.
  - Reasoning effort: "low" sent with response_format: {"type": "json_object"}.
  - Verbatim evidence quote check: strictly in code, not prompt. Value becomes ANY if quote
    is missing or not found verbatim in eligibility text.
  - Single caller at a time (R1): no worker pool, no thread pool.
  - Numbers in tunables.py, never inline.
  - Keys from .env.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

from dotenv import load_dotenv

from haqdaar.contracts import tunables
from haqdaar.contracts import vocab
from haqdaar.contracts.types import ANY, HARD_BOXES, SEVEN_BOXES, ValueCode
from haqdaar.data.pipeline.p1_scrape import (
    DEFAULT_PRIORITY,
    DEFAULT_SCHEMES_FILE,
    load_scheme_priorities,
)

logger = logging.getLogger("haqdaar.pipeline.p2_derive")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
RAW_CACHE_DIR = BASE_DIR / tunables.RAW_CACHE_DIR
EXTRACT_CACHE_DIR = BASE_DIR / tunables.EXTRACT_CACHE_DIR
DERIVED_DIR = BASE_DIR / tunables.DERIVED_DIR
REPORTS_DIR = BASE_DIR / tunables.REPORTS_DIR

MYSCHEME_HOST = "myscheme.gov.in"

# Closed vocabulary lists, keypad labels, and forbidden phrases now live in
# haqdaar/contracts/vocab.py (D6), so the pipeline and the engine read the same lists.


class GroqClient:
    """Single-caller HTTP client for Groq API with low reasoning effort."""

    def __init__(self, api_key: Optional[str] = None, ledger_path: Optional[Path] = None):
        if api_key is None:
            load_dotenv()
            api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY must be set in environment or .env")
        self.api_key = api_key
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"
        self._last_call_time: float = 0.0
        self.ledger_path: Path = (
            Path(ledger_path) if ledger_path is not None
            else BASE_DIR / tunables.REPORTS_DIR / "groq_usage.jsonl"
        )
        # Run totals for the cost printout at the end of a derive pass
        self.requests: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0

    def _write_ledger(self, task: str, slug: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Append one usage line to the ledger. Never lets a write failure break a derive run."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "task": task,
            "slug": slug,
            "model": tunables.GROQ_MODEL,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"Warning: failed to write Groq usage ledger {self.ledger_path}: {e}", file=sys.stderr)

    def call(self, system_prompt: str, user_prompt: str, task: str = "", slug: str = "") -> dict[str, Any]:
        """Execute one throttled call to Groq with response_format json_object and 429 backoff."""
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": tunables.GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "reasoning_effort": tunables.GROQ_REASONING_EFFORT,
        }

        max_retries = tunables.GROQ_MAX_RETRIES
        for attempt in range(max_retries):
            # Polite throttle (R1)
            now = time.time()
            elapsed = now - self._last_call_time
            if elapsed < tunables.GROQ_POLITE_DELAY_S:
                time.sleep(tunables.GROQ_POLITE_DELAY_S - elapsed)

            self._last_call_time = time.time()
            try:
                with httpx.Client(timeout=tunables.GROQ_TIMEOUT_S) as client:
                    resp = client.post(self.endpoint, headers=headers, json=payload)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Groq network call failed: {e}") from e
                logger.warning(f"Groq network error on attempt {attempt + 1}: {e}. Retrying in {tunables.GROQ_RETRY_SLEEP_S}s...")
                time.sleep(tunables.GROQ_RETRY_SLEEP_S)
                continue

            if resp.status_code == 429:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Groq API rate limit (HTTP 429) exceeded after {max_retries} attempts: {resp.text}")
                wait_s = tunables.GROQ_429_DEFAULT_WAIT_S
                retry_after = resp.headers.get("retry-after")
                if retry_after:
                    try:
                        wait_s = max(float(retry_after), tunables.GROQ_429_MIN_WAIT_S)
                    except ValueError:
                        pass
                else:
                    match = re.search(r"try again in ([0-9.]+)s", resp.text)
                    if match:
                        wait_s = float(match.group(1)) + tunables.GROQ_429_PAD_S
                logger.warning(
                    f"Groq 429 rate limit hit. Sleeping {wait_s:.2f}s before retry (attempt {attempt + 1}/{max_retries})..."
                )
                time.sleep(wait_s)
                continue

            if resp.status_code != 200:
                raise RuntimeError(f"Groq API returned error HTTP {resp.status_code}: {resp.text}")

            data = resp.json()
            choices = data.get("choices")
            if not choices:
                raise RuntimeError(f"Groq response missing choices: {data}")

            content = choices[0].get("message", {}).get("content", "")
            if not content or not content.strip():
                raise RuntimeError("Groq returned empty content (reasoning budget exceeded)")

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Failed to parse Groq response JSON: {e}\nRaw content: {content}") from e

            usage = data.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens") or 0
            completion_tokens = usage.get("completion_tokens") or 0
            self.requests += 1
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
            self._write_ledger(task, slug, prompt_tokens, completion_tokens)

            return parsed

        raise RuntimeError(f"Groq call failed after {max_retries} retries.")


def normalize_text(text: str) -> str:
    """Lowercase and collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def check_evidence_quote(quote: str, eligibility_text: str) -> bool:
    """Verify in code that quote is non-empty and appears verbatim in eligibility_text.

    A prompt is not a guard. This asserts verbatim inclusion. A quote containing an
    ellipsis ("..." or "…") is an elided quote: split it on the ellipsis, each stripped,
    non-empty fragment must itself be verbatim in the source, and the fragments must
    appear in order (each found only after the previous one's end) -- so a quote can elide
    the middle of a long sentence without being able to stitch together words that were
    never adjacent or that run backwards.
    """
    if not quote or not str(quote).strip():
        return False
    q = str(quote).strip()

    if "..." in q or "…" in q:
        fragments = [f.strip() for f in re.split(r"\.\.\.|…", q) if f.strip()]
        if not fragments:
            return False
        text_norm = " ".join(eligibility_text.split())
        pos = 0
        for frag in fragments:
            frag_norm = " ".join(frag.split())
            if not frag_norm:
                return False
            idx = text_norm.find(frag_norm, pos)
            if idx == -1:
                return False
            pos = idx + len(frag_norm)
        return True

    if q in eligibility_text:
        return True
    # Strip quotes/dots wrapping
    q_stripped = q.strip('"\'. \n\t')
    if q_stripped and q_stripped in eligibility_text:
        return True
    # Normalize whitespace
    q_norm = " ".join(q.split())
    text_norm = " ".join(eligibility_text.split())
    return bool(q_norm and q_norm in text_norm)


def evidence_text(box: str, raw_data: dict[str, Any]) -> str:
    """Text a facet's quote must sit in. Category words ("health", "pension") are said in the
    benefits text, so a category quote may come from eligibility or benefits. Every other box
    stays eligibility-only."""
    text = raw_data.get("eligibility", "")
    if box == "category":
        text += "\n" + raw_data.get("benefits", "")
    return text


def check_numeric_range(val: Any, quote: str) -> Any:
    """Numerics are stored exact as {"min", "max"} (05-DATA-CONTRACT §1C). Returns ANY if unusable.

    Each number must appear in the quote, so the model cannot invent a cutoff.
    """
    if not isinstance(val, dict):
        return ANY
    out: dict[str, Optional[int]] = {}
    quote_digits = set(re.findall(r"\d+", quote.replace(",", "")))
    for key in ("min", "max"):
        n = val.get(key)
        if n is None:
            out[key] = None
            continue
        if isinstance(n, bool) or not isinstance(n, int):
            return ANY
        if str(n) not in quote_digits:
            return ANY
        out[key] = n
    if out["min"] is None and out["max"] is None:
        return ANY
    if out["min"] is not None and out["max"] is not None and out["min"] > out["max"]:
        return ANY
    return out


def check_forbidden_words(text: str, forbidden_list: Sequence[str]) -> Optional[str]:
    """Check if any forbidden word/phrase appears in text. Returns matched phrase or None."""
    lower = text.lower()
    for fw in forbidden_list:
        if fw.lower() in lower:
            return fw
    return None


# Bumped when a task's prompt TEXT changes, so a stale cached response (derived under the
# old prompt) is never mistaken for one derived under the new prompt. facets -> 2 (step 1.4:
# closed lists now generated from vocab.py, state removed). aliases/summary prompt text is
# unchanged in this step, so they stay at 1.
# translate_hi/translate_mr are p4's (plan 1.9, D4). They are versioned here with the rest so
# that changing the model or the numeral format invalidates the cached translations.
PROMPT_VERSIONS: dict[str, int] = {
    "facets": 2, "aliases": 1, "summary": 1, "cards": 2,
    "translate_hi": 1, "translate_mr": 1,
}


def get_cache_path(source_sha256: str, task_name: str, cache_dir: Path) -> Path:
    """Content-addressed cache key: source_sha256 + task name + prompt version."""
    version = PROMPT_VERSIONS[task_name]
    return cache_dir / f"{source_sha256}_{task_name}_v{version}.json"


def read_from_cache(source_sha256: str, task_name: str, cache_dir: Path) -> Optional[dict[str, Any]]:
    path = get_cache_path(source_sha256, task_name, cache_dir)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Corrupt cache file %s, discarding: %s", path, e)
    return None


def write_to_cache(source_sha256: str, task_name: str, data: dict[str, Any], cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = get_cache_path(source_sha256, task_name, cache_dir)
    tmp = target.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.rename(target)


def derive_facets_task(
    raw_data: dict[str, Any],
    client: Optional[GroqClient] = None,
    cache_dir: Path = EXTRACT_CACHE_DIR,
) -> tuple[dict[str, Any], bool]:
    """Task 1: Derive facets with verbatim evidence quote check."""
    sha = raw_data["source_sha256"]
    cached = read_from_cache(sha, "facets", cache_dir)
    if cached is not None:
        return cached, True

    if client is None:
        raise ValueError("Cache miss and no Groq client provided")

    eligibility_text = raw_data.get("eligibility", "")
    benefits_text = raw_data.get("benefits", "")
    exclusions_text = raw_data.get("exclusions", "")
    slug = raw_data.get("myscheme_slug", "")

    # Closed-list lines are generated from vocab.py (D6), so the prompt and the pipeline's
    # own validation can never disagree about what values are allowed.
    category_lines = "\n".join(
        f"  - {c} ({vocab.CATEGORY_GLOSS[c]})" for c in vocab.CATEGORY
    )
    gender_list = ", ".join(f"'{v}'" for v in (*vocab.GENDER, ANY))
    social_category_list = ", ".join(f"'{v}'" for v in (*vocab.SOCIAL_CATEGORY, ANY))
    occupation_list = ", ".join(f"'{v}'" for v in (*vocab.OCCUPATION, ANY))

    system_prompt = (
        "You are an expert government scheme eligibility analyst for Haqdaar.\n"
        "Extract eligibility facets from the scheme text into a strict JSON object.\n"
        "Rules:\n"
        "1. Select from the allowed closed lists or return 'ANY'. Never invent new values.\n"
        "2. For EVERY non-ANY facet, you MUST provide an exact, verbatim sentence or clause from the eligibility text "
        "that justifies this value in the 'quote' field.\n"
        "3. If no exact sentence in the eligibility text justifies a facet, or if the scheme is universal on that dimension, "
        "set the value to 'ANY' and 'quote' to ''.\n"
        "4. The evidence-quote check is in code: if quote is missing or not verbatim in the eligibility text, "
        "code will discard the value to ANY.\n"
        "5. Category only: the quote may come from the benefits text OR the eligibility text.\n"
        "6. Occupation: if the text names several groups or occupations (or rural families as well as workers), "
        "occupation is 'ANY'. Never pick one group as representative. Set occupation only when the scheme is "
        "for that one occupation.\n\n"
        "Closed lists:\n"
        "- category: one of the following (code and what it covers), or 'ANY':\n"
        f"{category_lines}\n"
        f"- gender: one of [{gender_list}]\n"
        f"- social_category: one of [{social_category_list}]\n"
        "- age: {\"min\": <int or null>, \"max\": <int or null>} in years, or 'ANY'. Fill min and max separately; never put an upper limit in min.\n"
        "- income_band: {\"min\": <int or null>, \"max\": <int or null>} annual income in rupees, or 'ANY'.\n"
        "  For age and income_band the quote must contain every number you give.\n"
        f"- occupation: one of [{occupation_list}]\n\n"
        "Output JSON format:\n"
        "{\n"
        "  \"facets\": {\n"
        "    \"category\": {\"value\": \"<value>\", \"quote\": \"<verbatim quote>\"},\n"
        "    \"gender\": {\"value\": \"ANY\", \"quote\": \"\"},\n"
        "    \"social_category\": {\"value\": \"ANY\", \"quote\": \"\"},\n"
        "    \"age\": {\"value\": {\"min\": null, \"max\": null}, \"quote\": \"<verbatim quote>\"},\n"
        "    \"income_band\": {\"value\": \"ANY\", \"quote\": \"\"},\n"
        "    \"occupation\": {\"value\": \"<value>\", \"quote\": \"<verbatim quote>\"}\n"
        "  },\n"
        "  \"gate_notes\": [\"<non-column exclusion or blind spot>\"]\n"
        "}"
    )

    user_prompt = (
        f"Scheme slug: {slug}\n\n"
        f"Benefits:\n{benefits_text}\n\n"
        f"Eligibility:\n{eligibility_text}\n\n"
        f"Exclusions:\n{exclusions_text}\n"
    )

    raw_result = client.call(system_prompt, user_prompt, task="facets", slug=slug)
    write_to_cache(sha, "facets", raw_result, cache_dir)
    return raw_result, False


def derive_aliases_task(
    raw_data: dict[str, Any],
    scheme_title: str,
    client: Optional[GroqClient] = None,
    cache_dir: Path = EXTRACT_CACHE_DIR,
) -> tuple[dict[str, Any], bool]:
    """Task 2: Derive aliases in en, hi, mr with code-mixed variants."""
    sha = raw_data["source_sha256"]
    cached = read_from_cache(sha, "aliases", cache_dir)
    if cached is not None:
        return cached, True

    if client is None:
        raise ValueError("Cache miss and no Groq client provided")

    slug = raw_data.get("myscheme_slug", "")
    benefits_text = raw_data.get("benefits", "")[:tunables.ALIAS_BENEFITS_CHARS]

    system_prompt = (
        "You are a multilingual civil service outreach expert for Haqdaar in India.\n"
        "Generate spoken scheme aliases that citizens use when calling a phone helpline.\n"
        "Rules:\n"
        "1. Provide at least 5 distinct spoken aliases for English (aliases_en).\n"
        "2. Provide at least 5 distinct spoken aliases for Hindi (aliases_hi). At least ONE MUST BE code-mixed "
        "(this scheme's own name or acronym in Latin letters, or mixed with Hindi words).\n"
        "3. Provide at least 5 distinct spoken aliases for Marathi (aliases_mr). At least ONE MUST BE code-mixed "
        "(this scheme's own name or acronym in Latin letters, or mixed with Marathi words).\n"
        "4. Every alias must name THIS scheme only, built from its own title, acronym and benefit. "
        "Never use the name or acronym of any other government scheme.\n"
        "5. Output scheme names in Hindi and Marathi.\n\n"
        "Output JSON format:\n"
        "{\n"
        "  \"scheme_name_hi\": \"<Hindi full name>\",\n"
        "  \"scheme_name_mr\": \"<Marathi full name>\",\n"
        "  \"aliases_en\": [\"<alias1>\", \"<alias2>\", ...],\n"
        "  \"aliases_hi\": [\"<alias1>\", \"<alias2>\", ...],\n"
        "  \"aliases_mr\": [\"<alias1>\", \"<alias2>\", ...]\n"
        "}"
    )

    user_prompt = (
        f"Scheme slug: {slug}\n"
        f"Official English Title: {scheme_title}\n"
        f"Benefits overview: {benefits_text}\n"
    )

    raw_result = client.call(system_prompt, user_prompt, task="aliases", slug=slug)
    write_to_cache(sha, "aliases", raw_result, cache_dir)
    return raw_result, False


def derive_summary_task(
    raw_data: dict[str, Any],
    scheme_title: str,
    client: Optional[GroqClient] = None,
    cache_dir: Path = EXTRACT_CACHE_DIR,
) -> tuple[dict[str, Any], bool]:
    """Task 3: Derive summary in English (~35 words) and translate, banning Tier-1 words."""
    sha = raw_data["source_sha256"]
    cached = read_from_cache(sha, "summary", cache_dir)
    if cached is not None:
        return cached, True

    if client is None:
        raise ValueError("Cache miss and no Groq client provided")

    slug = raw_data.get("myscheme_slug", "")
    benefits_text = raw_data.get("benefits", "")
    eligibility_text = raw_data.get("eligibility", "")

    target_words = tunables.SUMMARY_WORD_TARGET
    min_words = target_words - tunables.SUMMARY_WORD_TOLERANCE
    max_words = target_words + tunables.SUMMARY_WORD_TOLERANCE

    system_prompt = (
        "You are a government communications specialist for Haqdaar.\n"
        f"Generate a concise, one-breath spoken summary of the scheme in English (~{target_words} words, strictly between {min_words} and {max_words} words).\n"
        "Then provide translations in Hindi and Marathi.\n\n"
        "CRITICAL HARD CONSTRAINT (TIER-1 FORBIDDEN WORDS BANNED):\n"
        "Do NOT use ANY of these forbidden words or phrases:\n"
        "- English forbidden: 'eligible', 'qualify', 'entitled', 'you will get', 'you can get'\n"
        "- Hindi forbidden: 'पात्र', 'हकदार', 'मिलेगा', 'पा सकते हैं'\n"
        "- Marathi forbidden: 'पात्र', 'हक्क', 'मिळेल', 'मिळू शकते'\n\n"
        "Instead of 'You are eligible for Rs 6000', say: 'The scheme provides Rs 6,000 annually to landholding farmer families.'\n"
        "Instead of 'You can get a loan', say: 'The initiative offers credit assistance.'\n\n"
        "Output JSON format:\n"
        "{\n"
        "  \"summary_en\": \"<concise English summary>\",\n"
        "  \"summary_hi\": \"<Hindi translation without forbidden words>\",\n"
        "  \"summary_mr\": \"<Marathi translation without forbidden words>\"\n"
        "}"
    )

    user_prompt = (
        f"Scheme slug: {slug}\n"
        f"Official Title: {scheme_title}\n"
        f"Benefits:\n{benefits_text}\n\n"
        f"Eligibility:\n{eligibility_text}\n"
    )

    raw_result = client.call(system_prompt, user_prompt, task="summary", slug=slug)
    write_to_cache(sha, "summary", raw_result, cache_dir)
    return raw_result, False


def apply_alias_uniqueness_gate(
    schemes: list[dict[str, Any]],
    langs: Sequence[str] = ("en", "hi", "mr"),
) -> None:
    """Gate 1: Alias uniqueness gate (05-DATA-CONTRACT §3, T12, T24).
    
    - Alias on >= 3 schemes: dropped from all of them (category word).
    - Alias on exactly 2 schemes: kept (Door A disambiguation pair).
    - Alias on 1 scheme: kept.
    Modifies schemes in place.
    """
    alias_counts: dict[str, dict[str, int]] = {lang: defaultdict(int) for lang in langs}

    # Pass 1: count occurrences
    for s in schemes:
        for lang in langs:
            raw_aliases = s.get(f"aliases_{lang}", [])
            seen_for_scheme: set[str] = set()
            for alias in raw_aliases:
                norm = normalize_text(alias)
                if not norm or norm in seen_for_scheme:
                    continue
                seen_for_scheme.add(norm)
                alias_counts[lang][norm] += 1

    # Pass 2: filter aliases on each scheme
    for s in schemes:
        for lang in langs:
            raw_aliases = s.get(f"aliases_{lang}", [])
            kept: list[str] = []
            seen: set[str] = set()
            for alias in raw_aliases:
                norm = normalize_text(alias)
                if not norm or norm in seen:
                    continue
                seen.add(norm)
                # Keep if on <= 2 schemes
                if alias_counts[lang][norm] < tunables.ALIAS_CATEGORY_WORD_MIN:
                    kept.append(norm)
            s[f"aliases_{lang}"] = kept


def read_scheme_title_from_html(slug: str, raw_dir: Path = RAW_CACHE_DIR) -> str:
    """Read full scheme title from scraped HTML <title> tag."""
    html_path = raw_dir / f"{slug}.html"
    if html_path.exists():
        try:
            content = html_path.read_text(encoding="utf-8")
            m = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
            if m:
                title = m.group(1).strip()
                title = re.sub(r"\s*\|\s*myScheme.*$", "", title, flags=re.IGNORECASE)
                if title:
                    return title
        except Exception:
            pass
    # Fallback to slug title-cased
    return slug.replace("-", " ").title()


def run_pipeline_extract(
    raw_dir: Path = RAW_CACHE_DIR,
    extract_cache_dir: Path = EXTRACT_CACHE_DIR,
    derived_dir: Path = DERIVED_DIR,
    reports_dir: Path = REPORTS_DIR,
    client: Optional[GroqClient] = None,
    schemes_file: Path = DEFAULT_SCHEMES_FILE,
) -> list[dict[str, Any]]:
    """Execute Step 8 derivation pass.

    Reads 12 files from data_cache/raw/*.json.
    Derives facets, aliases, and summary via Groq (cached).
    Applies evidence-quote checks in code.
    Applies table-wide alias uniqueness gate.
    Cuts trilingual occupation vocabulary (cardinality <= 9).
    Writes valid records to data_cache/derived/.

    A scheme that fails a per-scheme check (bad host, a Groq task exception, a forbidden
    word, the summary word cap, the alias floor or missing code-mixed alias) is quarantined
    with a reason in data_cache/reports/derive.json instead of stopping the run (D2). The run
    itself still raises if fewer than tunables.MIN_SCHEMES schemes survive, or if a whole-corpus
    invariant (occupation cardinality, the evidence-quote self-check) is violated.
    """
    raw_files = sorted(raw_dir.glob("*.json"), key=lambda p: p.stem)
    if not raw_files:
        raise FileNotFoundError(f"No raw scheme files found in {raw_dir}")

    extract_cache_dir.mkdir(parents=True, exist_ok=True)
    derived_dir.mkdir(parents=True, exist_ok=True)

    priorities = load_scheme_priorities(schemes_file)

    if client is None:
        client = GroqClient()

    logger.info("Starting derivation pass for %d schemes...", len(raw_files))

    quarantined: list[dict[str, str]] = []

    def _quarantine(slug: str, reason: str) -> None:
        """Set a scheme aside with a reason instead of failing the whole run (D2).

        Removes any stale data_cache/derived/<slug>.json so no quarantined scheme's old
        record survives from a previous run.
        """
        quarantined.append({"slug": slug, "reason": reason})
        stale = derived_dir / f"{slug}.json"
        if stale.exists():
            stale.unlink()

    raw_schemes: list[dict[str, Any]] = []
    for rf in raw_files:
        with open(rf, "r", encoding="utf-8") as f:
            data = json.load(f)
        slug = data.get("myscheme_slug", rf.stem)
        # Verify host
        url = data.get("source_url", "")
        parsed = urlparse(url)
        if MYSCHEME_HOST not in parsed.netloc:
            _quarantine(slug, f"invalid host: {url}")
            continue
        raw_schemes.append(data)

    total_tasks = len(raw_schemes) * 3
    cache_hits = 0
    network_calls = 0

    intermediate_records: list[dict[str, Any]] = []

    for idx, raw_data in enumerate(raw_schemes):
        slug = raw_data["myscheme_slug"]
        sha = raw_data["source_sha256"]
        title_en = read_scheme_title_from_html(slug, raw_dir)

        try:
            # 1. Facets task
            facets_result, facets_cached = derive_facets_task(raw_data, client, extract_cache_dir)
            if facets_cached:
                cache_hits += 1
                logger.info("[CACHE] %s:facets (%s) hit", slug, sha[:8])
            else:
                network_calls += 1
                logger.info("[GROQ]  %s:facets (%s) completed", slug, sha[:8])

            # 2. Aliases task
            aliases_result, aliases_cached = derive_aliases_task(raw_data, title_en, client, extract_cache_dir)
            if aliases_cached:
                cache_hits += 1
                logger.info("[CACHE] %s:aliases (%s) hit", slug, sha[:8])
            else:
                network_calls += 1
                logger.info("[GROQ]  %s:aliases (%s) completed", slug, sha[:8])

            # 3. Summary task
            summary_result, summary_cached = derive_summary_task(raw_data, title_en, client, extract_cache_dir)
            if summary_cached:
                cache_hits += 1
                logger.info("[CACHE] %s:summary (%s) hit", slug, sha[:8])
            else:
                network_calls += 1
                logger.info("[GROQ]  %s:summary (%s) completed", slug, sha[:8])
        except Exception as e:
            # A Groq task exhausts its retries and raises (RuntimeError), or the cache
            # misses with no client (ValueError). Either way, quarantine this scheme only.
            logger.error("Scheme %s quarantined: %s", slug, e)
            _quarantine(slug, str(e))
            continue

        intermediate_records.append({
            "idx": idx,
            "raw": raw_data,
            "title_en": title_en,
            "facets_res": facets_result,
            "aliases_res": aliases_result,
            "summary_res": summary_result,
        })

    # Assemble and validate records
    derived_schemes: list[dict[str, Any]] = []

    for item in intermediate_records:
        raw_data = item["raw"]
        slug = raw_data["myscheme_slug"]
        sha = raw_data["source_sha256"]
        title_en = item["title_en"]
        facets_res = item["facets_res"]
        aliases_res = item["aliases_res"]
        summary_res = item["summary_res"]

        # state comes from level, never from the model (D6): the model is never asked, so it
        # can never invent a state. p1 does not write a level yet, so this still hard-codes
        # CENTRAL for every real scheme until step 3.3; raw_data.get() only lets a level
        # travel through when a future p1 (or a test) sets one.
        level = raw_data.get("level", "CENTRAL")
        if level == "CENTRAL":
            state_value = ANY
        elif level == "MAHARASHTRA":
            state_value = "MAHARASHTRA"
        else:
            _quarantine(slug, f"level {level} not served")
            continue

        # Parse and verify facets
        raw_facets = facets_res.get("facets", {})
        gate_notes = list(facets_res.get("gate_notes", []))

        validated_facets: dict[str, Any] = {}
        evidence_quotes: dict[str, str] = {}
        closed_lists = {
            "category": vocab.CATEGORY,
            "gender": vocab.GENDER,
            "social_category": vocab.SOCIAL_CATEGORY,
            "occupation": vocab.OCCUPATION,
        }

        quarantine_reason: Optional[str] = None
        for box in SEVEN_BOXES:
            if box == "state":
                continue  # derived from level above, never asked of the model
            box_data = raw_facets.get(box, {})
            if isinstance(box_data, dict):
                val = box_data.get("value", ANY)
                quote = str(box_data.get("quote", "")).strip()
            else:
                val = box_data
                quote = ""

            # A value outside its closed list is not silently widened to ANY (D6): that has
            # the same lie risk as an unknown value -- a women-only scheme would be read to
            # everyone. It quarantines the whole scheme instead. (Applies to category too:
            # an unknown category *code* is still quarantined, even though an unverified
            # category *quote* is not -- see below.)
            closed_list = closed_lists.get(box)
            if closed_list is not None and val != ANY and val not in closed_list:
                quarantine_reason = f"unknown {box} value {val!r}"
                break

            if box in ("age", "income_band"):
                if val == ANY:
                    validated_facets[box] = ANY
                    evidence_quotes[box] = ""
                    continue
                if isinstance(val, dict) and val.get("min") is None and val.get("max") is None:
                    # No number at all -- the model is saying "no limit", not offering a
                    # fact it failed to back up. Silent ANY, same as the model saying ANY.
                    validated_facets[box] = ANY
                    evidence_quotes[box] = ""
                    continue
                # At least one number is being asserted: it must be backed by a quote that
                # both contains every number given AND is itself verbatim in the source.
                # Missing, unverified, or number-short quotes all quarantine (D6) -- there is
                # no silent-ANY escape once a number has actually been claimed.
                checked = check_numeric_range(val, quote)
                if checked == ANY:
                    quarantine_reason = f"Unusable {box} range: {quote}"
                    break
                if not check_evidence_quote(quote, evidence_text(box, raw_data)):
                    quarantine_reason = f"Unverified quote for {box}={checked}: {quote}"
                    break
                validated_facets[box] = checked
                evidence_quotes[box] = quote
                continue

            # category, gender, social_category, occupation
            if val == ANY:
                validated_facets[box] = ANY
                evidence_quotes[box] = ""
                continue

            if check_evidence_quote(quote, evidence_text(box, raw_data)):
                validated_facets[box] = val
                evidence_quotes[box] = quote
            elif box == "category":
                # category is the caller's NEED, not an eligibility rule like the other hard
                # boxes: an unverified quote here is honest ambiguity, not a lie risk, so it
                # falls back to ANY with a gate note instead of quarantining (the pre-1.4
                # behaviour, kept for this one box only).
                gate_notes.append(f"Unverified quote for category={val}: {quote}")
                validated_facets[box] = ANY
                evidence_quotes[box] = ""
            else:
                # gender / social_category / occupation: same lie risk as an unknown value
                # (D6) -- quarantine rather than silently widen to ANY.
                quarantine_reason = f"Unverified quote for {box}={val}: {quote}"
                break

        if quarantine_reason is not None:
            logger.warning("Scheme %s quarantined: %s", slug, quarantine_reason)
            _quarantine(slug, quarantine_reason)
            continue

        # Validate summary and forbidden phrases
        summary_en = summary_res.get("summary_en", "").strip()
        # D4 (plan 1.9): p2 writes ENGLISH ONLY. The Hindi and Marathi summaries used to come
        # from Groq here with no gate, which is finding F2. They now come from p4_translate.py
        # and are gated by p5, so these stay empty for p4 to fill.
        summary_hi = ""
        summary_mr = ""

        # Check forbidden phrases via vocab.py (D2: quarantine this scheme, don't stop the run).
        # English only now: hi/mr no longer originate here, and p5 gates what p4 produces.
        bad_word_reason = None
        for lang, text in [("en", summary_en)]:
            bad_phrase = vocab.find_forbidden(text, lang)
            if bad_phrase:
                bad_word_reason = f"Forbidden phrase '{bad_phrase}' found in {lang} summary: '{text}'"
                break
        if bad_word_reason:
            _quarantine(slug, bad_word_reason)
            continue

        # ~35-word cap is checked in code, not only asked for in the prompt
        n_words = len(summary_en.split())
        if n_words > tunables.SUMMARY_WORD_TARGET + tunables.SUMMARY_WORD_TOLERANCE:
            _quarantine(
                slug,
                f"English summary is {n_words} words, over the ~{tunables.SUMMARY_WORD_TARGET}-word cap",
            )
            continue

        # Clean aliases
        aliases_en = [normalize_text(a) for a in aliases_res.get("aliases_en", []) if normalize_text(a)]
        aliases_hi = [normalize_text(a) for a in aliases_res.get("aliases_hi", []) if normalize_text(a)]
        aliases_mr = [normalize_text(a) for a in aliases_res.get("aliases_mr", []) if normalize_text(a)]

        title_hi = aliases_res.get("scheme_name_hi", title_en)
        title_mr = aliases_res.get("scheme_name_mr", title_en)

        scheme_record: dict[str, Any] = {
            "scheme_id": slug,
            "myscheme_slug": slug,
            "source_url": raw_data["source_url"],
            "level": level,
            "priority": priorities.get(slug, DEFAULT_PRIORITY),
            "state": state_value,
            "department": "Government of India",
            "fetched_on": raw_data["fetched_on"],
            "source_sha256": sha,
            "facets_source": "derived",
            "facets_verified_by": None,
            "facets_verified_on": None,
            "en_sections_origin": "source",
            "hi_sections_origin": "machine",
            "mr_sections_origin": "machine",
            "en_summary_origin": "machine",
            "hi_summary_origin": "machine",
            "mr_summary_origin": "machine",
            "en_verified_by": None,
            "en_verified_on": None,
            "hi_verified_by": None,
            "hi_verified_on": None,
            "mr_verified_by": None,
            "mr_verified_on": None,
            "scheme_name_en": title_en,
            "scheme_name_hi": title_hi,
            "scheme_name_mr": title_mr,
            "aliases_en": aliases_en,
            "aliases_hi": aliases_hi,
            "aliases_mr": aliases_mr,
            "category": validated_facets["category"],
            "gender": validated_facets["gender"],
            "social_category": validated_facets["social_category"],
            "age": validated_facets["age"],
            "income_band": validated_facets["income_band"],
            "occupation": validated_facets["occupation"],
            "evidence_quotes": evidence_quotes,
            "gate_notes": gate_notes,
            "chunks": {
                "en": {
                    "name": title_en,
                    "summary": summary_en,
                    "benefit_text": raw_data.get("benefits", "").strip(),
                    "who_can_apply": raw_data.get("eligibility", "").strip(),
                    "documents": raw_data.get("documents", "").strip(),
                    "how_to_apply": raw_data.get("apply", "").strip(),
                },
                "hi": {
                    "name": title_hi,
                    "summary": summary_hi,
                    "benefit_text": "",
                    "who_can_apply": "",
                    "documents": "",
                    "how_to_apply": "",
                },
                "mr": {
                    "name": title_mr,
                    "summary": summary_mr,
                    "benefit_text": "",
                    "who_can_apply": "",
                    "documents": "",
                    "how_to_apply": "",
                },
            },
        }
        derived_schemes.append(scheme_record)

    # Apply Table-Wide Alias Uniqueness Gate (Gate 1)
    apply_alias_uniqueness_gate(derived_schemes)

    # Alias floor and code-mix check post-gate. No padding with made-up aliases:
    # if the floor bites, quarantine the scheme rather than admit one the caller cannot name (T07).
    kept_schemes: list[dict[str, Any]] = []
    for s in derived_schemes:
        slug = s["myscheme_slug"]
        reason: Optional[str] = None
        for lang in ("en", "hi", "mr"):
            if len(s[f"aliases_{lang}"]) < tunables.ALIAS_FLOOR:
                reason = f"only {len(s[f'aliases_{lang}'])} aliases in {lang}, required >= {tunables.ALIAS_FLOOR}"
                break
        if reason is None:
            for lang in ("hi", "mr"):
                if not any(re.search(r"[a-zA-Z]", a) for a in s[f"aliases_{lang}"]):
                    reason = f"no code-mixed alias in {lang}"
                    break
        if reason is not None:
            _quarantine(slug, reason)
            continue
        kept_schemes.append(s)
    derived_schemes = kept_schemes

    # Write the quarantine report and enforce the floor (D2): the run fails only if too few
    # schemes survive, never because one scheme had a problem.
    kept_slugs = [s["myscheme_slug"] for s in derived_schemes]
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "derive.json"
    tmp_report = report_path.with_suffix(".tmp")
    with open(tmp_report, "w", encoding="utf-8") as f:
        json.dump(
            {"stage": "derive", "kept": kept_slugs, "quarantined": quarantined},
            f, indent=2, ensure_ascii=False,
        )
    tmp_report.rename(report_path)

    if len(kept_slugs) < tunables.MIN_SCHEMES:
        raise RuntimeError(
            f"Pipeline derive kept {len(kept_slugs)} schemes, but at least {tunables.MIN_SCHEMES} "
            f"are required (see {report_path})"
        )

    # Cut trilingual occupation vocabulary from corpus's own eligibility prose
    corpus_occupations: set[str] = set()
    for s in derived_schemes:
        occ = s.get("occupation")
        if occ and occ != ANY:
            corpus_occupations.add(str(occ))

    sorted_occupations = sorted(corpus_occupations)
    cardinality = len(sorted_occupations)

    if cardinality > tunables.KEYPAD_CARDINALITY_MAX:
        raise ValueError(
            f"Occupation vocabulary cardinality {cardinality} exceeds maximum {tunables.KEYPAD_CARDINALITY_MAX}"
        )

    occupation_vocab = {
        "vocab_source": "corpus_prose_cut",
        "cardinality": cardinality,
        "occupations": {
            occ: vocab.LABELS.get(occ, {"en": occ, "hi": occ, "mr": occ})
            for occ in sorted_occupations
        },
    }

    # Invariant verification: every non-ANY facet carries verbatim evidence quote. "state" is
    # excluded: it comes from level (trusted, not model-derived), so it has no evidence quote.
    for s in derived_schemes:
        slug = s["myscheme_slug"]
        for b in SEVEN_BOXES:
            if b == "state":
                continue
            val = s[b]
            if val != ANY:
                quote = s["evidence_quotes"].get(b)
                if not quote:
                    raise AssertionError(f"Scheme {slug} has non-ANY facet {b}={val} without quote")
                raw_s = next(r for r in raw_schemes if r["myscheme_slug"] == slug)
                if not check_evidence_quote(quote, evidence_text(b, raw_s)):
                    raise AssertionError(f"Scheme {slug} facet {b}={val} quote not verbatim in source text")

    # Write occupation vocabulary
    vocab_path = derived_dir / "occupation_vocab.json"
    with open(vocab_path, "w", encoding="utf-8") as f:
        json.dump(occupation_vocab, f, indent=2, ensure_ascii=False)

    # Write individual scheme records and schemes.jsonl
    schemes_jsonl_path = derived_dir / "schemes.jsonl"
    with open(schemes_jsonl_path, "w", encoding="utf-8") as jsonl_f:
        for s in derived_schemes:
            slug = s["myscheme_slug"]
            scheme_path = derived_dir / f"{slug}.json"
            with open(scheme_path, "w", encoding="utf-8") as f:
                json.dump(s, f, indent=2, ensure_ascii=False)
            jsonl_f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print("=" * 60)
    print("Step 8 Pipeline Extraction Complete")
    print(f"Total schemes processed: {len(derived_schemes)}")
    print(f"Total tasks:             {total_tasks}")
    print(f"Cache hits:              {cache_hits}/{total_tasks}")
    print(f"Network calls:           {network_calls}")
    print(f"Occupation cardinality:  {cardinality} <= {tunables.KEYPAD_CARDINALITY_MAX}")
    print(f"Derived records written: {derived_dir}")
    print(f"quarantined: {len(quarantined)} (see data_cache/reports/derive.json)")
    print(f"groq: {client.requests} requests, {client.prompt_tokens} prompt + {client.completion_tokens} completion tokens")
    print("=" * 60)

    return derived_schemes


if __name__ == "__main__":
    run_pipeline_extract()
