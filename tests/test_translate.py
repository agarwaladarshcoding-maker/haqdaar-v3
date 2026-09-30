"""Tests for p4_translate.py (plan item 1.9, D4).

No test here touches the network. The live API was probed once by hand and the findings are in
.agent/NOTES.md; what these tests hold down is the behaviour the pipeline depends on: the cache
makes a second run free, a failure leaves the text empty instead of half-written, and the request
we send carries the model and numeral format D4 requires.
"""
from __future__ import annotations

import json

import pytest

from haqdaar.contracts import tunables
from haqdaar.data.pipeline import p2_derive, p4_translate
from haqdaar.data.pipeline.p4_translate import (
    TRANSLATED_FIELDS,
    SarvamTranslator,
    TranslateError,
    _split_for_limit,
    run_translate,
    translate_scheme,
)


class FakeTranslator:
    """Stands in for SarvamTranslator, counting calls the way the real one counts requests."""

    def __init__(self, fail_on: tuple[str, ...] = ()):
        self.requests = 0
        self.chars = 0
        self.calls: list[tuple[str, str, str]] = []
        self.fail_on = fail_on

    def translate(self, text: str, lang: str, slug: str = "", field: str = "") -> str:
        if not (text or "").strip():
            return ""
        self.calls.append((slug, lang, field))
        if field in self.fail_on:
            raise TranslateError(f"forced failure on {field}")
        self.requests += 1
        self.chars += len(text)
        return f"[{lang}] {text}"


def _scheme(slug: str, sha: str) -> dict:
    return {
        "scheme_id": slug,
        "source_sha256": sha,
        "scheme_name_en": f"Scheme {slug}",
        "chunks": {
            "en": {
                "name": f"Scheme {slug}",
                "summary": "Farmers get 6000 rupees a year.",
                "benefit_text": "",
                "who_can_apply": "",
                "documents": "",
                "how_to_apply": "",
            },
            "hi": {"name": "", "summary": "", "benefit_text": "", "who_can_apply": "",
                   "documents": "", "how_to_apply": ""},
            "mr": {"name": "", "summary": "", "benefit_text": "", "who_can_apply": "",
                   "documents": "", "how_to_apply": ""},
        },
    }


def _card_row(slug: str, sha: str, ok: bool = True) -> dict:
    return {
        "slug": slug,
        "source_sha256": sha,
        "cards": {
            "benefit_text": "The scheme gives 6000 rupees.",
            "who_can_apply": "Farmers who own land can apply.",
            "documents": "Aadhaar card and bank passbook.",
            "how_to_apply": "Apply at the CSC centre.",
        },
        "gates": {},
        "ok": ok,
    }


def _write_inputs(tmp_path, n_schemes: int = 12, ok: bool = True):
    derived = tmp_path / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    cards_path = derived / "cards.jsonl"
    with open(derived / "schemes.jsonl", "w", encoding="utf-8") as sf, \
         open(cards_path, "w", encoding="utf-8") as cf:
        for i in range(n_schemes):
            slug, sha = f"scheme-{i}", f"sha{i:064d}"
            sf.write(json.dumps(_scheme(slug, sha), ensure_ascii=False) + "\n")
            cf.write(json.dumps(_card_row(slug, sha, ok=ok), ensure_ascii=False) + "\n")
    return derived, cards_path


# --- the plan's own verify criteria -------------------------------------------------------

def test_twelve_schemes_five_texts_two_languages(tmp_path, monkeypatch):
    """12 x 5 texts x 2 languages, and nothing is left empty."""
    derived, cards_path = _write_inputs(tmp_path, 12)
    fake = FakeTranslator()
    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: fake)

    rc = run_translate(
        derived_dir=derived, cards_path=cards_path,
        reports_dir=tmp_path / "reports", cache_dir=tmp_path / "cache",
    )
    assert rc == 0
    # 12 schemes x 2 languages x 5 texts
    assert len(fake.calls) == 12 * 2 * 5

    rows = [json.loads(l) for l in open(derived / "schemes.jsonl", encoding="utf-8")]
    assert len(rows) == 12
    for row in rows:
        for lang in ("hi", "mr"):
            for field in TRANSLATED_FIELDS:
                assert row["chunks"][lang][field].startswith(f"[{lang}] "), (lang, field)


def test_second_run_makes_zero_requests(tmp_path, monkeypatch):
    """The plan's cache test: a second run must not spend anything."""
    derived, cards_path = _write_inputs(tmp_path, 12)
    cache_dir, reports = tmp_path / "cache", tmp_path / "reports"

    first = FakeTranslator()
    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: first)
    run_translate(derived_dir=derived, cards_path=cards_path,
                  reports_dir=reports, cache_dir=cache_dir)
    assert first.requests == 12 * 2 * 5

    second = FakeTranslator()
    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: second)
    run_translate(derived_dir=derived, cards_path=cards_path,
                  reports_dir=reports, cache_dir=cache_dir)
    assert second.requests == 0
    assert second.calls == []

    report = json.loads((reports / "translate.json").read_text(encoding="utf-8"))
    assert report["requests"] == 0


def test_warm_cache_needs_no_api_key(tmp_path, monkeypatch):
    """A fully warm run must work with no SARVAM_API_KEY at all."""
    derived, cards_path = _write_inputs(tmp_path, 2)
    cache_dir, reports = tmp_path / "cache", tmp_path / "reports"

    fake = FakeTranslator()
    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: fake)
    run_translate(derived_dir=derived, cards_path=cards_path,
                  reports_dir=reports, cache_dir=cache_dir)

    def boom(*a, **k):
        raise AssertionError("a warm run must not build a client")

    monkeypatch.setattr(p4_translate, "SarvamTranslator", boom)
    assert run_translate(derived_dir=derived, cards_path=cards_path,
                         reports_dir=reports, cache_dir=cache_dir) == 0


# --- honesty rules -------------------------------------------------------------------------

def test_failed_cards_are_not_translated(tmp_path, monkeypatch):
    """A scheme whose cards failed p3's gates must not be translated at all."""
    derived, cards_path = _write_inputs(tmp_path, 3, ok=False)
    fake = FakeTranslator()
    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: fake)

    run_translate(derived_dir=derived, cards_path=cards_path,
                  reports_dir=tmp_path / "reports", cache_dir=tmp_path / "cache")
    assert fake.calls == []
    report = json.loads((tmp_path / "reports" / "translate.json").read_text(encoding="utf-8"))
    assert report["translated"] == 0
    assert len(report["failures"]) == 3


def test_failure_leaves_text_empty_not_half_written(tmp_path, monkeypatch):
    """A mid-scheme failure must not write a partly translated scheme."""
    derived, cards_path = _write_inputs(tmp_path, 1)
    fake = FakeTranslator(fail_on=("documents",))
    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: fake)

    run_translate(derived_dir=derived, cards_path=cards_path,
                  reports_dir=tmp_path / "reports", cache_dir=tmp_path / "cache")

    row = json.loads(open(derived / "schemes.jsonl", encoding="utf-8").readline())
    for lang in ("hi", "mr"):
        for field in TRANSLATED_FIELDS:
            assert row["chunks"][lang][field] == "", (lang, field)


def test_failed_scheme_is_not_cached(tmp_path, monkeypatch):
    """A failure must stay retryable: nothing is written to the cache."""
    derived, cards_path = _write_inputs(tmp_path, 1)
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(p4_translate, "SarvamTranslator",
                        lambda *a, **k: FakeTranslator(fail_on=("summary",)))
    run_translate(derived_dir=derived, cards_path=cards_path,
                  reports_dir=tmp_path / "reports", cache_dir=cache_dir)

    good = FakeTranslator()
    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: good)
    run_translate(derived_dir=derived, cards_path=cards_path,
                  reports_dir=tmp_path / "reports", cache_dir=cache_dir)
    assert good.requests == 2 * 5


def test_cache_version_invalidates(tmp_path, monkeypatch):
    """Changing the model or numeral format must not silently reuse old rows."""
    derived, cards_path = _write_inputs(tmp_path, 1)
    cache_dir, reports = tmp_path / "cache", tmp_path / "reports"
    first = FakeTranslator()
    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: first)
    run_translate(derived_dir=derived, cards_path=cards_path,
                  reports_dir=reports, cache_dir=cache_dir)

    monkeypatch.setitem(p2_derive.PROMPT_VERSIONS, "translate_hi",
                        p2_derive.PROMPT_VERSIONS["translate_hi"] + 1)
    monkeypatch.setitem(p2_derive.PROMPT_VERSIONS, "translate_mr",
                        p2_derive.PROMPT_VERSIONS["translate_mr"] + 1)
    second = FakeTranslator()
    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: second)
    run_translate(derived_dir=derived, cards_path=cards_path,
                  reports_dir=reports, cache_dir=cache_dir)
    assert second.requests == 2 * 5


# --- the API contract the probe pinned -----------------------------------------------------

def test_request_carries_model_and_international_numerals():
    """D4: the call must ask for sarvam-translate:v1 and international digits."""
    sent: dict = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"translated_text": "किसानों को 6000 रुपये मिलते हैं।"}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent["url"], sent["headers"], sent["json"] = url, headers, json
        return FakeResponse()

    translator = SarvamTranslator(api_key="test-key", ledger_path=None)
    import httpx
    original, httpx.post = httpx.post, fake_post
    try:
        out = translator.translate("Farmers get 6000 rupees.", "hi", slug="s", field="summary")
    finally:
        httpx.post = original

    assert out == "किसानों को 6000 रुपये मिलते हैं।"
    assert sent["json"]["model"] == tunables.TRANSLATE_MODEL == "sarvam-translate:v1"
    assert sent["json"]["numerals_format"] == "international"
    assert sent["json"]["target_language_code"] == "hi-IN"
    assert sent["json"]["source_language_code"] == "en-IN"
    assert sent["headers"]["api-subscription-key"] == "test-key"
    assert translator.requests == 1


def test_non_200_raises_rather_than_returning_english():
    """A refused request must fail loudly, never fall through as untranslated English."""
    class FakeResponse:
        status_code = 402
        text = '{"error": "No credits available"}'

    def fake_post(*a, **k):
        return FakeResponse()

    translator = SarvamTranslator(api_key="test-key")
    import httpx
    original, httpx.post = httpx.post, fake_post
    try:
        with pytest.raises(TranslateError, match="402"):
            translator.translate("Farmers get 6000 rupees.", "hi")
    finally:
        httpx.post = original


def test_empty_text_costs_nothing():
    translator = SarvamTranslator(api_key="test-key")
    assert translator.translate("", "hi") == ""
    assert translator.translate("   ", "mr") == ""
    assert translator.requests == 0


def test_unknown_language_rejected():
    translator = SarvamTranslator(api_key="test-key")
    with pytest.raises(TranslateError):
        translator.translate("text", "ta")


# --- the 2000-character cap the probe found ------------------------------------------------

def test_split_respects_the_two_thousand_char_cap():
    limit = tunables.TRANSLATE_CHAR_LIMIT
    assert limit == 2000
    text = ("Farmers get 6000 rupees a year. " * 200).strip()
    parts = _split_for_limit(text, limit)
    assert len(parts) > 1
    assert all(len(p) <= limit for p in parts)
    # nothing is dropped on the way
    assert "".join(p.replace(" ", "") for p in parts) == text.replace(" ", "")


def test_short_text_is_one_piece():
    assert _split_for_limit("Farmers get 6000 rupees.", 2000) == ["Farmers get 6000 rupees."]


def test_unbroken_run_still_splits():
    """A text with no spaces must not loop forever."""
    parts = _split_for_limit("x" * 4500, 2000)
    assert all(len(p) <= 2000 for p in parts)
    assert sum(len(p) for p in parts) == 4500


def test_translate_scheme_returns_from_cache_flag(tmp_path):
    english = {f: f"English {f}." for f in TRANSLATED_FIELDS}
    fake = FakeTranslator()
    texts, from_cache = translate_scheme(
        "slug", "sha-1", english, "hi", translator=fake, cache_dir=tmp_path / "cache")
    assert from_cache is False
    assert set(texts) == set(TRANSLATED_FIELDS)

    texts2, from_cache2 = translate_scheme(
        "slug", "sha-1", english, "hi", translator=fake, cache_dir=tmp_path / "cache")
    assert from_cache2 is True
    assert texts2 == texts


# --- retry: only what is worth retrying ----------------------------------------------------

def _stub_post(responses):
    """Replace httpx.post with a scripted sequence of responses or exceptions."""
    calls = {"n": 0}

    def fake_post(*a, **k):
        item = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        if isinstance(item, Exception):
            raise item
        return item

    return fake_post, calls


class _Resp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_timeout_is_retried_then_succeeds(monkeypatch):
    """The exact failure seen on the real run: one read timeout must not lose the text."""
    import httpx
    monkeypatch.setattr(tunables, "TRANSLATE_RETRY_BACKOFF_S", 0.0)
    fake_post, calls = _stub_post([
        httpx.ReadTimeout("read timed out"),
        _Resp(200, {"translated_text": "किसानों को 6000 रुपये।"}),
    ])
    monkeypatch.setattr(httpx, "post", fake_post)

    translator = SarvamTranslator(api_key="test-key")
    assert translator.translate("Farmers get 6000 rupees.", "hi") == "किसानों को 6000 रुपये।"
    assert calls["n"] == 2
    assert translator.requests == 1  # the failed attempt is not billed


def test_no_credits_is_not_retried(monkeypatch):
    """402 is final: retrying only burns time and still fails."""
    import httpx
    monkeypatch.setattr(tunables, "TRANSLATE_RETRY_BACKOFF_S", 0.0)
    fake_post, calls = _stub_post([_Resp(402, text='{"error": "No credits available"}')])
    monkeypatch.setattr(httpx, "post", fake_post)

    translator = SarvamTranslator(api_key="test-key")
    with pytest.raises(TranslateError, match="402"):
        translator.translate("Farmers get 6000 rupees.", "hi")
    assert calls["n"] == 1


def test_bad_input_is_not_retried(monkeypatch):
    """400 (over the 2000-char cap) is our bug, not a blip."""
    import httpx
    monkeypatch.setattr(tunables, "TRANSLATE_RETRY_BACKOFF_S", 0.0)
    fake_post, calls = _stub_post([_Resp(400, text="String should have at most 2000 characters")])
    monkeypatch.setattr(httpx, "post", fake_post)

    translator = SarvamTranslator(api_key="test-key")
    with pytest.raises(TranslateError, match="400"):
        translator.translate("Farmers get 6000 rupees.", "hi")
    assert calls["n"] == 1


def test_server_error_is_retried_and_gives_up(monkeypatch):
    """A 5xx is retried, but not forever."""
    import httpx
    monkeypatch.setattr(tunables, "TRANSLATE_RETRY_BACKOFF_S", 0.0)
    fake_post, calls = _stub_post([_Resp(503, text="upstream unavailable")])
    monkeypatch.setattr(httpx, "post", fake_post)

    translator = SarvamTranslator(api_key="test-key")
    with pytest.raises(TranslateError, match="gave up"):
        translator.translate("Farmers get 6000 rupees.", "hi")
    assert calls["n"] == tunables.TRANSLATE_MAX_ATTEMPTS


# --- stale ungated text must not survive (finding F2) --------------------------------------

def test_stale_ungated_hindi_summary_is_cleared(tmp_path, monkeypatch):
    """A scheme we decline to translate must not keep p2's old ungated Hindi summary."""
    derived, cards_path = _write_inputs(tmp_path, 1, ok=False)
    rows = [json.loads(l) for l in open(derived / "schemes.jsonl", encoding="utf-8")]
    rows[0]["chunks"]["hi"]["summary"] = "पाँच लाख रुपये तक का नकद-रहित इलाज"
    rows[0]["chunks"]["mr"]["summary"] = "पाच लाख रुपयांपर्यंत उपचार"
    rows[0]["hi_summary_origin"] = "machine"
    with open(derived / "schemes.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: FakeTranslator())
    run_translate(derived_dir=derived, cards_path=cards_path,
                  reports_dir=tmp_path / "reports", cache_dir=tmp_path / "cache")

    out = json.loads(open(derived / "schemes.jsonl", encoding="utf-8").readline())
    for lang in ("hi", "mr"):
        for field in TRANSLATED_FIELDS:
            assert out["chunks"][lang][field] == "", (lang, field)
        assert out[f"{lang}_summary_origin"] is None
    # the scheme name is deliberately kept: D4 sends it to the owner's review sheet
    assert out["chunks"]["hi"]["name"] == rows[0]["chunks"]["hi"]["name"]


def test_failed_language_is_cleared_not_left_stale(tmp_path, monkeypatch):
    """If one language fails mid-run, its old text is emptied rather than left behind."""
    derived, cards_path = _write_inputs(tmp_path, 1)
    rows = [json.loads(l) for l in open(derived / "schemes.jsonl", encoding="utf-8")]
    rows[0]["chunks"]["hi"]["summary"] = "पुराना बिना जाँचा सारांश"
    with open(derived / "schemes.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    monkeypatch.setattr(p4_translate, "SarvamTranslator",
                        lambda *a, **k: FakeTranslator(fail_on=("summary",)))
    run_translate(derived_dir=derived, cards_path=cards_path,
                  reports_dir=tmp_path / "reports", cache_dir=tmp_path / "cache")

    out = json.loads(open(derived / "schemes.jsonl", encoding="utf-8").readline())
    assert out["chunks"]["hi"]["summary"] == ""


# --- the fixed lines -------------------------------------------------------------------------

import re
import shutil

from haqdaar.audio import lines as lines_mod


class FakeLineTranslator:
    """Turns every English word into a Devanagari one, keeping numbers and {slots} as they are."""

    def __init__(self, broken: tuple[str, ...] = ()):
        self.requests = 0
        self.chars = 0
        self.broken = broken

    def translate(self, text: str, lang: str, slug: str = "", field: str = "") -> str:
        self.requests += 1
        self.chars += len(text)
        if slug in self.broken:
            return text  # comes back untranslated: G4 must stop it
        return re.sub(r"(?<!\{)\b[A-Za-z][A-Za-z']*\b(?![a-z0-9_]*\})", "शब्द", text)


@pytest.fixture
def lines_copy(tmp_path):
    path = tmp_path / "lines.yaml"
    shutil.copy(lines_mod.LINES_PATH, path)
    yield path
    lines_mod.load_lines.cache_clear()


def _untranslated_count(path) -> int:
    lines_mod.load_lines.cache_clear()
    return len(lines_mod.untranslated(path))


def test_lines_are_translated_and_written_back(lines_copy, tmp_path, monkeypatch):
    fake = FakeLineTranslator()
    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: fake)
    before = _untranslated_count(lines_copy)
    assert before > 0

    p4_translate.run_translate_lines(lines_copy, tmp_path / "reports", tmp_path / "cache")

    assert _untranslated_count(lines_copy) == 0
    # Two lines with the same English share one cached translation.
    distinct = {
        (texts["en"], lang) for line_id, texts in lines_mod.load_lines(lines_copy).items()
        if line_id != lines_mod.TRILINGUAL_LINE_ID for lang in ("hi", "mr")
    }
    assert fake.requests == len(distinct) <= before
    texts = lines_mod.load_lines(lines_copy)
    assert "{scheme_1}" in texts["door_a_option_1"]["hi"]
    # The trilingual greeting is one hand-made recording, never machine-translated.
    assert set(texts[lines_mod.TRILINGUAL_LINE_ID]) == {"en"}
    # The house-style comments survive the write.
    assert "House style" in lines_copy.read_text(encoding="utf-8")


def test_second_lines_run_makes_zero_requests(lines_copy, tmp_path, monkeypatch):
    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: FakeLineTranslator())
    p4_translate.run_translate_lines(lines_copy, tmp_path / "reports", tmp_path / "cache")

    fresh = tmp_path / "fresh.yaml"
    shutil.copy(lines_mod.LINES_PATH, fresh)
    boom = lambda *a, **k: pytest.fail("a warm run must not need Sarvam")
    monkeypatch.setattr(p4_translate, "SarvamTranslator", boom)
    p4_translate.run_translate_lines(fresh, tmp_path / "reports", tmp_path / "cache")
    assert _untranslated_count(fresh) == 0


def test_pinned_line_is_left_alone(lines_copy, tmp_path, monkeypatch):
    text = lines_copy.read_text(encoding="utf-8")
    lines_copy.write_text(
        text.replace("  consent_notice:\n", "  consent_notice:\n    pinned: true\n"), encoding="utf-8"
    )
    monkeypatch.setattr(p4_translate, "SarvamTranslator", lambda *a, **k: FakeLineTranslator())
    p4_translate.run_translate_lines(lines_copy, tmp_path / "reports", tmp_path / "cache")

    lines_mod.load_lines.cache_clear()
    assert set(lines_mod.load_lines(lines_copy)["consent_notice"]) == {"en"}


def test_a_line_that_fails_a_gate_is_not_written(lines_copy, tmp_path, monkeypatch):
    monkeypatch.setattr(
        p4_translate, "SarvamTranslator", lambda *a, **k: FakeLineTranslator(broken=("opener_prompt",))
    )
    p4_translate.run_translate_lines(lines_copy, tmp_path / "reports", tmp_path / "cache")

    lines_mod.load_lines.cache_clear()
    assert set(lines_mod.load_lines(lines_copy)["opener_prompt"]) == {"en"}
    report = json.loads((tmp_path / "reports" / "lines_translate.json").read_text(encoding="utf-8"))
    assert {f["line"] for f in report["failures"]} == {"opener_prompt"}


def test_gate_line_catches_a_lost_slot():
    assert p4_translate.gate_line("Press 1 for {scheme_1}.", "1 दबाएँ योजना के लिए।", "hi")
    assert not p4_translate.gate_line("Press 1 for {scheme_1}.", "{scheme_1} के लिए 1 दबाएँ।", "hi")
