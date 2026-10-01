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


@pytest.fixture(autouse=True)
def _block_unmocked_http_calls(monkeypatch):
    """Guard all tests against making real external HTTP requests.

    Any unmocked HTTP call attempting to reach external endpoints (Groq, Sarvam,
    Together, Twilio, etc.) raises an immediate AssertionError.
    """
    import httpx

    real_send = httpx.Client.send

    def _guarded_send(self, request, *args, **kwargs):
        host = getattr(request.url, "host", "")
        if host in ("localhost", "127.0.0.1", "testserver", "test"):
            return real_send(self, request, *args, **kwargs)
        raise AssertionError(f"Unmocked external HTTP call to {request.url} blocked by conftest.py")

    monkeypatch.setattr(httpx.Client, "send", _guarded_send)

    real_async_send = httpx.AsyncClient.send

    async def _guarded_async_send(self, request, *args, **kwargs):
        host = getattr(request.url, "host", "")
        if host in ("localhost", "127.0.0.1", "testserver", "test"):
            return await real_async_send(self, request, *args, **kwargs)
        raise AssertionError(f"Unmocked external async HTTP call to {request.url} blocked by conftest.py")

    monkeypatch.setattr(httpx.AsyncClient, "send", _guarded_async_send)

