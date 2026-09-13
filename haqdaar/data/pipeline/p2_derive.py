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
from haqdaar.contracts.types import ANY, HARD_BOXES, SEVEN_BOXES, ValueCode

logger = logging.getLogger("haqdaar.pipeline.p2_derive")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
RAW_CACHE_DIR = BASE_DIR / tunables.RAW_CACHE_DIR
EXTRACT_CACHE_DIR = BASE_DIR / tunables.EXTRACT_CACHE_DIR
DERIVED_DIR = BASE_DIR / tunables.DERIVED_DIR

MYSCHEME_HOST = "myscheme.gov.in"

# Closed vocabulary sets (T06, T10, T11, 05-DATA-CONTRACT §1C)
CATEGORIES: frozenset[str] = frozenset({
    "agriculture",
    "business",
    "education",
    "employment",
    "handloom",
    "health",
    "housing",
    "livelihood",
    "pension",
    "skills",
    "social_welfare",
    "ANY",
})

GENDERS: frozenset[str] = frozenset({"female", "male", "other", "ANY"})

SOCIAL_CATEGORIES: frozenset[str] = frozenset({"GEN", "OBC", "SC", "ST", "ANY"})

STATES: frozenset[str] = frozenset({
    "ANDAMAN_AND_NICOBAR", "ANDHRA_PRADESH", "ARUNACHAL_PRADESH", "ASSAM", "BIHAR",
    "CHANDIGARH", "CHHATTISGARH", "DADRA_AND_NAGAR_HAVELI_AND_DAMAN_AND_DIU", "DELHI",
    "GOA", "GUJARAT", "HARYANA", "HIMACHAL_PRADESH", "JAMMU_AND_KASHMIR", "JHARKHAND",
    "KARNATAKA", "KERALA", "LADAKH", "LAKSHADWEEP", "MADHYA_PRADESH", "MAHARASHTRA",
    "MANIPUR", "MEGHALAYA", "MIZORAM", "NAGALAND", "ODISHA", "PUDUCHERRY", "PUNJAB",
    "RAJASTHAN", "SIKKIM", "TAMIL_NADU", "TELANGANA", "TRIPURA", "UTTAR_PRADESH",
    "UTTARAKHAND", "WEST_BENGAL", "ANY",
})

OCCUPATIONS: frozenset[str] = frozenset({
    "farmer",
    "street_vendor",
    "apprentice",
    "entrepreneur",
    "artisan",
    "weaver",
    "worker",
    "ANY",
})

# Tier-1 forbidden words (05-DATA-CONTRACT §3 Gate 4)
TIER1_FORBIDDEN_EN: tuple[str, ...] = ("eligible", "qualify", "entitled", "you will get", "you can get")
TIER1_FORBIDDEN_HI: tuple[str, ...] = ("पात्र", "हकदार", "मिलेगा", "पा सकते हैं")
TIER1_FORBIDDEN_MR: tuple[str, ...] = ("पात्र", "हक्क", "मिळेल", "मिळू शकते")

OCCUPATION_TRILINGUAL: dict[str, dict[str, str]] = {
    "farmer": {"en": "farmer", "hi": "किसान", "mr": "शेतकरी"},
    "street_vendor": {"en": "street vendor", "hi": "रेहड़ी-पटरी विक्रेता", "mr": "फेरीवाले"},
    "apprentice": {"en": "apprentice", "hi": "प्रशिक्षु", "mr": "शिकाऊ उमेदवार"},
    "entrepreneur": {"en": "entrepreneur", "hi": "उद्यमी", "mr": "उद्योजक"},
    "artisan": {"en": "artisan", "hi": "कारीगर", "mr": "कारागीर"},
    "weaver": {"en": "weaver", "hi": "बुनकर", "mr": "विणकर"},
    "worker": {"en": "worker", "hi": "श्रमिक", "mr": "कामगार"},
}


class GroqClient:
    """Single-caller HTTP client for Groq API with low reasoning effort."""

    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            load_dotenv()
            api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY must be set in environment or .env")
        self.api_key = api_key
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"
        self._last_call_time: float = 0.0

    def call(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
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
                return json.loads(content)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Failed to parse Groq response JSON: {e}\nRaw content: {content}") from e

        raise RuntimeError(f"Groq call failed after {max_retries} retries.")


def normalize_text(text: str) -> str:
    """Lowercase and collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def check_evidence_quote(quote: str, eligibility_text: str) -> bool:
    """Verify in code that quote is non-empty and appears verbatim in eligibility_text.
    
    A prompt is not a guard. This asserts verbatim inclusion.
    """
    if not quote or not str(quote).strip():
        return False
    q = str(quote).strip()
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


def check_forbidden_words(text: str, forbidden_list: Sequence[str]) -> Optional[str]:
    """Check if any forbidden word/phrase appears in text. Returns matched phrase or None."""
    lower = text.lower()
    for fw in forbidden_list:
        if fw.lower() in lower:
            return fw
    return None


def get_cache_path(source_sha256: str, task_name: str, cache_dir: Path) -> Path:
    """Content-addressed cache key: source_sha256 + task name."""
    return cache_dir / f"{source_sha256}_{task_name}.json"


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
        "code will discard the value to ANY.\n\n"
        "Closed lists:\n"
        "- category: one of ['agriculture', 'business', 'education', 'employment', 'handloom', 'health', 'housing', 'livelihood', 'pension', 'skills', 'social_welfare', 'ANY']\n"
        "- state: one of 36 Indian states/UTs in uppercase or 'ANY'. Central/nationwide schemes MUST be 'ANY'.\n"
        "- gender: one of ['female', 'male', 'other', 'ANY']\n"
        "- social_category: one of ['GEN', 'OBC', 'SC', 'ST', 'ANY']\n"
        "- age: integer cutoff or 'ANY'\n"
        "- income_band: integer annual income cutoff or 'ANY'\n"
        "- occupation: one of ['farmer', 'street_vendor', 'apprentice', 'entrepreneur', 'artisan', 'weaver', 'worker', 'ANY']\n\n"
        "Output JSON format:\n"
        "{\n"
        "  \"facets\": {\n"
        "    \"category\": {\"value\": \"<value>\", \"quote\": \"<verbatim quote>\"},\n"
        "    \"state\": {\"value\": \"ANY\", \"quote\": \"\"},\n"
        "    \"gender\": {\"value\": \"ANY\", \"quote\": \"\"},\n"
        "    \"social_category\": {\"value\": \"ANY\", \"quote\": \"\"},\n"
        "    \"age\": {\"value\": \"ANY\", \"quote\": \"\"},\n"
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

    raw_result = client.call(system_prompt, user_prompt)
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
        "(e.g. using Latin alphabet or mixing English and Hindi words like 'pm kisan loan' or 'kisan yojana').\n"
        "3. Provide at least 5 distinct spoken aliases for Marathi (aliases_mr). At least ONE MUST BE code-mixed "
        "(e.g. using Latin alphabet or mixing English and Marathi words like 'pm kisan loan' or 'kisan yojana').\n"
        "4. Include common short acronyms, scheme keywords, and colloquial terms.\n"
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

    raw_result = client.call(system_prompt, user_prompt)
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

    raw_result = client.call(system_prompt, user_prompt)
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
    client: Optional[GroqClient] = None,
) -> list[dict[str, Any]]:
    """Execute Step 8 derivation pass.
    
    Reads 12 files from data_cache/raw/*.json.
    Derives facets, aliases, and summary via Groq (cached).
    Applies evidence-quote checks in code.
    Applies table-wide alias uniqueness gate.
    Cuts trilingual occupation vocabulary (cardinality <= 9).
    Writes valid records to data_cache/derived/.
    """
    raw_files = sorted(raw_dir.glob("*.json"))
    if not raw_files:
        raise FileNotFoundError(f"No raw scheme files found in {raw_dir}")

    extract_cache_dir.mkdir(parents=True, exist_ok=True)
    derived_dir.mkdir(parents=True, exist_ok=True)

    if client is None:
        client = GroqClient()

    logger.info("Starting derivation pass for %d schemes...", len(raw_files))

    raw_schemes: list[dict[str, Any]] = []
    for rf in raw_files:
        with open(rf, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Verify host
        url = data.get("source_url", "")
        parsed = urlparse(url)
        if MYSCHEME_HOST not in parsed.netloc:
            raise ValueError(f"Scheme {rf.name} has invalid host: {url}")
        raw_schemes.append(data)

    total_tasks = len(raw_schemes) * 3
    cache_hits = 0
    network_calls = 0

    intermediate_records: list[dict[str, Any]] = []

    for idx, raw_data in enumerate(raw_schemes):
        slug = raw_data["myscheme_slug"]
        sha = raw_data["source_sha256"]
        title_en = read_scheme_title_from_html(slug, raw_dir)

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
        eligibility_text = raw_data.get("eligibility", "")
        facets_res = item["facets_res"]
        aliases_res = item["aliases_res"]
        summary_res = item["summary_res"]

        # Parse and verify facets
        raw_facets = facets_res.get("facets", {})
        gate_notes = list(facets_res.get("gate_notes", []))

        validated_facets: dict[str, Any] = {}
        evidence_quotes: dict[str, str] = {}

        for box in SEVEN_BOXES:
            box_data = raw_facets.get(box, {})
            if isinstance(box_data, dict):
                val = box_data.get("value", ANY)
                quote = str(box_data.get("quote", "")).strip()
            else:
                val = box_data
                quote = ""

            # Check closed sets
            if box == "category" and val not in CATEGORIES:
                val = ANY
            elif box == "state" and val not in STATES:
                val = ANY
            elif box == "gender" and val not in GENDERS:
                val = ANY
            elif box == "social_category" and val not in SOCIAL_CATEGORIES:
                val = ANY
            elif box == "occupation" and val not in OCCUPATIONS:
                val = ANY
            elif box in ("age", "income_band"):
                if val != ANY and not isinstance(val, int):
                    if isinstance(val, str) and val.isdigit():
                        val = int(val)
                    else:
                        val = ANY

            # VERBATIM EVIDENCE CHECK IN CODE
            if val != ANY:
                is_verbatim = check_evidence_quote(quote, eligibility_text)
                if is_verbatim:
                    validated_facets[box] = val
                    evidence_quotes[box] = quote
                else:
                    # Value without verbatim quote becomes ANY
                    logger.warning(
                        "Scheme %s: facet %s=%s rejected: quote not verbatim in eligibility text",
                        slug, box, val,
                    )
                    if quote:
                        gate_notes.append(f"Unverified quote for {box}={val}: {quote}")
                    validated_facets[box] = ANY
                    evidence_quotes[box] = ""
            else:
                validated_facets[box] = ANY
                evidence_quotes[box] = ""

        # Validate summary and forbidden phrases
        summary_en = summary_res.get("summary_en", "").strip()
        summary_hi = summary_res.get("summary_hi", "").strip()
        summary_mr = summary_res.get("summary_mr", "").strip()

        # Check Tier-1 forbidden words
        for lang, text, fwords in [
            ("en", summary_en, TIER1_FORBIDDEN_EN),
            ("hi", summary_hi, TIER1_FORBIDDEN_HI),
            ("mr", summary_mr, TIER1_FORBIDDEN_MR),
        ]:
            bad_word = check_forbidden_words(text, fwords)
            if bad_word:
                raise ValueError(
                    f"Tier-1 forbidden word '{bad_word}' found in {lang} summary for {slug}: '{text}'"
                )

        # ~35-word cap is checked in code, not only asked for in the prompt
        n_words = len(summary_en.split())
        if n_words > tunables.SUMMARY_WORD_TARGET + tunables.SUMMARY_WORD_TOLERANCE:
            raise ValueError(f"English summary for {slug} is {n_words} words, over the ~{tunables.SUMMARY_WORD_TARGET}-word cap")

        # Clean aliases
        aliases_en = [normalize_text(a) for a in aliases_res.get("aliases_en", []) if normalize_text(a)]
        aliases_hi = [normalize_text(a) for a in aliases_res.get("aliases_hi", []) if normalize_text(a)]
        aliases_mr = [normalize_text(a) for a in aliases_res.get("aliases_mr", []) if normalize_text(a)]

        title_hi = aliases_res.get("scheme_name_hi", title_en)
        title_mr = aliases_res.get("scheme_name_mr", title_en)

        scheme_record: dict[str, Any] = {
            "scheme_id": f"S{item['idx'] + 1}",
            "myscheme_slug": slug,
            "source_url": raw_data["source_url"],
            "level": "CENTRAL",
            "state": validated_facets["state"],
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
    # if the floor bites, lower the floor rather than admit a scheme the caller cannot name (T07).
    for s in derived_schemes:
        slug = s["myscheme_slug"]
        for lang in ("en", "hi", "mr"):
            if len(s[f"aliases_{lang}"]) < tunables.ALIAS_FLOOR:
                raise ValueError(
                    f"Scheme {slug} has only {len(s[f'aliases_{lang}'])} aliases in {lang}, required >= {tunables.ALIAS_FLOOR}"
                )
        for lang in ("hi", "mr"):
            if not any(re.search(r"[a-zA-Z]", a) for a in s[f"aliases_{lang}"]):
                raise ValueError(f"Scheme {slug} has no code-mixed alias in {lang}")

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
            occ: OCCUPATION_TRILINGUAL.get(occ, {"en": occ, "hi": occ, "mr": occ})
            for occ in sorted_occupations
        },
    }

    # Invariant verification: every non-ANY facet carries verbatim evidence quote
    for s in derived_schemes:
        slug = s["myscheme_slug"]
        for b in SEVEN_BOXES:
            val = s[b]
            if val != ANY:
                quote = s["evidence_quotes"].get(b)
                if not quote:
                    raise AssertionError(f"Scheme {slug} has non-ANY facet {b}={val} without quote")
                raw_s = next(r for r in raw_schemes if r["myscheme_slug"] == slug)
                if not check_evidence_quote(quote, raw_s["eligibility"]):
                    raise AssertionError(f"Scheme {slug} facet {b}={val} quote not verbatim in eligibility")

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
    print("=" * 60)

    return derived_schemes


if __name__ == "__main__":
    run_pipeline_extract()
