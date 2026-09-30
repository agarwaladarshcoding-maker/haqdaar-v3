import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from haqdaar.contracts import tunables  # noqa: E402


@pytest.fixture(autouse=True)
def _keep_ledgers_out_of_the_real_reports(tmp_path, monkeypatch):
    """Tests must never append to the real usage ledgers.

    They had been: 100 of the 113 rows in data_cache/reports/groq_usage.jsonl were
    slug="demo-scheme" written by the test suite, which made `make pipeline-cost` report a
    bill nobody ran up. The ledger is what says how much real money was spent, so a test
    writing to it is a test corrupting the accounts.
    """
    monkeypatch.setattr(tunables, "REPORTS_DIR", str(tmp_path / "reports"))


@pytest.fixture(autouse=True)
def _never_reach_a_paid_model(tmp_path, monkeypatch):
    """The older tests fake GroqClient / SarvamTranslator. With Muse as the default (3.4) they
    reached the real Muse API and spent ₹0.70 on 30 Sep. Pin the old names, and make any Muse
    call a test did not fake fail at once instead of going out."""
    from haqdaar.data.pipeline import muse

    monkeypatch.setattr(tunables, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(tunables, "TRANSLATE_PROVIDER", "sarvam")
    monkeypatch.setattr(muse, "LEDGER", tmp_path / "reports" / "muse_usage.jsonl")

    def _no_network(self, payload):
        raise AssertionError("a test tried to call the real Muse API")

    monkeypatch.setattr(muse.MuseClient, "_http_post", _no_network)
