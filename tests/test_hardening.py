"""Plan 5.3 — `make run` restarts after a crash, `make smoke` prints the checklist. No network."""
from __future__ import annotations

import sys

from haqdaar.contracts import tunables
from tools import keep_running as kr
from tools import smoke


def _runner(codes, calls):
    """A fake server: each run returns the next exit code, or raises it if it is an exception."""
    def run(cmd):
        calls.append(list(cmd))
        code = codes.pop(0)
        if isinstance(code, BaseException):
            raise code
        return code
    return run


def test_a_crash_is_followed_by_a_restart_and_ctrl_c_stops_for_good():
    calls, said, slept = [], [], []
    clock = iter(range(0, 10_000, 1000))  # stops far apart: never a crash loop
    code = kr.keep_running(
        ["server"],
        run=_runner([1, -9, 0, KeyboardInterrupt()], calls),
        sleep=slept.append,
        clock=lambda: next(clock),
        say=said.append,
    )
    assert code == 0
    assert len(calls) == 4  # crash, kill and a clean exit each got a restart
    assert slept == [tunables.RESTART_WAIT_S] * 3
    assert "Ctrl-C" in said[-1]


def test_ctrl_c_while_waiting_to_restart_also_stops():
    def sleep(_):
        raise KeyboardInterrupt()

    calls = []
    assert kr.keep_running(["server"], run=_runner([1], calls), sleep=sleep, clock=lambda: 0.0, say=lambda s: None) == 0
    assert len(calls) == 1


def test_a_crash_loop_gives_up():
    calls, said = [], []
    code = kr.keep_running(
        ["server"],
        run=_runner([1] * 50, calls),
        sleep=lambda s: None,
        clock=lambda: 0.0,  # every stop inside one window
        say=said.append,
    )
    assert code == 1
    assert len(calls) == tunables.RESTART_MAX_STOPS
    assert "giving up" in said[-1]


def test_a_real_dying_process_is_restarted():
    calls = []

    def run(cmd):
        import subprocess

        calls.append(1)
        if len(calls) == 3:
            raise KeyboardInterrupt()
        return subprocess.call(cmd)

    cmd = [sys.executable, "-c", "import sys; sys.exit(3)"]
    assert kr.keep_running(cmd, run=run, sleep=lambda s: None, say=lambda s: None) == 0
    assert len(calls) == 3


def test_no_command_is_a_usage_error():
    assert kr.main([]) == 2


def test_smoke_prints_checked_items_and_the_drills():
    lines = []
    assert smoke.run_smoke(checks=(lambda: "fine one", lambda: "fine two"), say=lines.append) == 0
    text = "\n".join(lines)
    assert "[ok]   fine one" in text and "[ok]   fine two" in text
    for word in ("Wi-Fi", "killed", "30 minutes idle"):  # the three 5.3 drills
        assert word in text
    assert text.count("[ ]") == len(smoke.BY_HAND)


def test_smoke_reports_a_failed_check_without_a_traceback():
    def bad():
        raise RuntimeError("snapshot is broken")

    lines = []
    assert smoke.run_smoke(checks=(bad,), say=lines.append) == 1
    assert any("[FAIL] snapshot is broken" in line for line in lines)


def test_smoke_key_check_names_missing_keys_and_never_prints_values(tmp_path, monkeypatch):
    (tmp_path / ".env.example").write_text("ALPHA_KEY=\nBETA_KEY=\nNGROK_DOMAIN=\n")
    (tmp_path / ".env").write_text("ALPHA_KEY=super-secret-value\n")
    monkeypatch.delenv("BETA_KEY", raising=False)
    try:
        smoke._check_keys(tmp_path)
        raise AssertionError("a missing key must fail the check")
    except RuntimeError as e:
        assert "BETA_KEY" in str(e) and "super-secret-value" not in str(e)

    (tmp_path / ".env").write_text("ALPHA_KEY=super-secret-value\nBETA_KEY=x\n")
    out = smoke._check_keys(tmp_path)
    assert "2 keys" in out and "super-secret-value" not in out
