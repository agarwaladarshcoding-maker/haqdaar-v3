"""Step 1.0 tools: the number is not moved without a question, the net check, offline ear check."""
import io
import json
from pathlib import Path

import pytest

from tools import ear_check, run_demo, tunnel

ROOT = Path(__file__).resolve().parent.parent
THIS = str(tunnel.REPO_ROOT)
NEW = "https://new.example/answer"


class FakeStdin(io.StringIO):
    def __init__(self, text: str, tty: bool):
        super().__init__(text)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture
def number(tmp_path, monkeypatch):
    marker = tmp_path / "holder.json"
    monkeypatch.setenv("HAQDAAR_NUMBER_HOLDER", str(marker))
    monkeypatch.delenv("MOVE_NUMBER", raising=False)
    state = {"now": "https://old.example/answer", "pointed": []}
    monkeypatch.setattr(tunnel, "number_answers_at", lambda: state["now"])
    monkeypatch.setattr(tunnel, "point_number_at", lambda url: state["pointed"].append(url) or state["now"])
    state["marker"] = marker
    return state


def answer(monkeypatch, text, tty=True):
    monkeypatch.setattr("sys.stdin", FakeStdin(text, tty))


def test_no_marker_asks_and_no_leaves_number(number, monkeypatch, capsys):
    answer(monkeypatch, "n\n")
    assert tunnel.take_number(NEW) is False
    assert number["pointed"] == []
    assert not number["marker"].exists()
    assert "[y/N]" in capsys.readouterr().out


def test_yes_moves_and_writes_marker(number, monkeypatch):
    answer(monkeypatch, "Yes\n")
    assert tunnel.take_number(NEW) is True
    assert number["pointed"] == [NEW]
    data = json.loads(number["marker"].read_text())
    assert data["folder"] == THIS and data["url"] == NEW and data["at"]


def test_our_marker_and_same_url_does_not_ask(number, monkeypatch):
    number["marker"].write_text(json.dumps({"folder": THIS, "url": number["now"], "at": "x"}))
    monkeypatch.setattr("sys.stdin", None)  # a read would fail
    assert tunnel.take_number(NEW) is True
    assert number["pointed"] == [NEW]
    assert json.loads(number["marker"].read_text())["url"] == NEW


def test_our_marker_but_number_moved_asks_again(number, monkeypatch):
    number["marker"].write_text(json.dumps({"folder": THIS, "url": "https://other/answer", "at": "x"}))
    answer(monkeypatch, "n\n")
    assert tunnel.take_number(NEW) is False
    assert number["pointed"] == []


def test_no_terminal_means_no(number, monkeypatch, capsys):
    answer(monkeypatch, "y\n", tty=False)
    assert tunnel.take_number(NEW) is False
    assert number["pointed"] == []
    assert "MOVE_NUMBER=1" in capsys.readouterr().out


def test_move_number_env_means_yes_without_question(number, monkeypatch, capsys):
    monkeypatch.setenv("MOVE_NUMBER", "1")
    monkeypatch.setattr("sys.stdin", None)
    assert tunnel.take_number(NEW) is True
    assert number["pointed"] == [NEW]
    assert "[y/N]" not in capsys.readouterr().out


def test_network_report_fast_is_not_weak():
    report = run_demo.network_report({"a": lambda: True, "b": lambda: True}, 3)
    assert set(report) == {"a", "b"} and all(t is not None for t in report.values())
    assert run_demo.weak(report, 2.0) == []


def test_slow_place_is_named():
    assert run_demo.weak({"a": 0.1, "b": 3.5}, 2.0) == ["b"]


def test_one_failed_try_is_named():
    calls = iter([True, False, True])
    report = run_demo.network_report({"a": lambda: True, "b": lambda: next(calls)}, 3)
    assert report["b"] is None
    assert run_demo.weak(report, 2.0) == ["b"]


def test_ear_check_default_makes_no_request(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("speech-to-text was called")
    monkeypatch.setattr(ear_check.SpeechToText, "transcribe", boom)
    assert ear_check.main(["--lang", "en"]) in (0, 1)


def test_ear_check_custom_files_need_live(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ear_check.SpeechToText, "transcribe",
                        lambda *a, **k: pytest.fail("speech-to-text was called"))
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"")
    assert ear_check.main([str(wav)]) != 0
    assert "--live" in capsys.readouterr().out


def test_server_listens_on_this_computer_only():
    for name in ("Makefile", "tools/run_demo.py"):
        assert "0.0.0.0" not in (ROOT / name).read_text()
