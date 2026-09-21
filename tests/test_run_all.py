"""tests/test_run_all.py

Step 1.15 (plan 1.13, D11) — the pipeline runner spends nothing without being asked.
"""
import json

import pytest

from haqdaar.data.pipeline import run_all


@pytest.fixture
def fake_steps(monkeypatch):
    """Replace the real steps with ones that only record that they ran."""
    ran: list[str] = []

    def _step(name, paid, needs_rescrape=False):
        return run_all.Step(name, paid, lambda: ran.append(name) or 0, needs_rescrape)

    monkeypatch.setattr(
        run_all,
        "_steps",
        lambda: [
            _step("p1 scrape", True, needs_rescrape=True),
            _step("p2 derive", True),
            _step("p5 gates", False),
        ],
    )
    return ran


def test_no_paid_step_runs_without_yes(fake_steps, capsys):
    assert run_all.main([]) == 0
    assert fake_steps == ["p5 gates"], "a paid step ran without being asked"
    out = capsys.readouterr().out
    assert "p2 derive: SKIPPED" in out


def test_yes_runs_the_paid_steps(fake_steps):
    assert run_all.main(["--yes"]) == 0
    assert "p2 derive" in fake_steps


def test_scraping_needs_rescrape_as_well_as_yes(fake_steps):
    """The raw cache does not expire, so --yes alone must not re-hit someone's site."""
    assert run_all.main(["--yes"]) == 0
    assert "p1 scrape" not in fake_steps

    fake_steps.clear()
    assert run_all.main(["--yes", "--rescrape"]) == 0
    assert "p1 scrape" in fake_steps


def test_a_failing_step_stops_the_pipeline(monkeypatch, capsys):
    ran: list[str] = []
    monkeypatch.setattr(
        run_all,
        "_steps",
        lambda: [
            run_all.Step("first", False, lambda: ran.append("first") or 3),
            run_all.Step("second", False, lambda: ran.append("second") or 0),
        ],
    )
    assert run_all.main([]) == 3
    assert ran == ["first"], "the pipeline carried on after a failure"


def test_cost_runs_nothing(monkeypatch):
    monkeypatch.setattr(
        run_all, "_steps", lambda: pytest.fail("--cost must not run any step")
    )
    assert run_all.main(["--cost"]) == 0


def test_cost_adds_up_the_ledgers(tmp_path, monkeypatch, capsys):
    groq = tmp_path / "groq.jsonl"
    groq.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"task": "cards", "slug": "a", "prompt_tokens": 100, "completion_tokens": 20},
                {"task": "facets", "slug": "b", "prompt_tokens": 50, "completion_tokens": 5},
            ]
        ),
        encoding="utf-8",
    )
    sarvam = tmp_path / "sarvam.jsonl"
    sarvam.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"slug": "a", "lang": "hi", "chars": 300},
                {"slug": "a", "lang": "mr", "chars": 200},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(run_all, "GROQ_LEDGER", groq)
    monkeypatch.setattr(run_all, "SARVAM_LEDGER", sarvam)

    run_all.print_cost()
    out = capsys.readouterr().out
    assert "requests: 2" in out
    assert "tokens total: 175" in out
    assert "chars: 500" in out
    assert "hi: 300 chars" in out


def test_a_half_written_ledger_line_does_not_break_the_bill(tmp_path, monkeypatch):
    bad = tmp_path / "groq.jsonl"
    bad.write_text('{"prompt_tokens": 1}\n{"prompt_to\n', encoding="utf-8")
    monkeypatch.setattr(run_all, "GROQ_LEDGER", bad)
    monkeypatch.setattr(run_all, "SARVAM_LEDGER", tmp_path / "missing.jsonl")
    assert run_all.print_cost() == 0


def test_a_missing_ledger_reads_as_nothing_spent(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_all, "GROQ_LEDGER", tmp_path / "nope.jsonl")
    monkeypatch.setattr(run_all, "SARVAM_LEDGER", tmp_path / "nope2.jsonl")
    run_all.print_cost()
    assert "requests: 0" in capsys.readouterr().out
