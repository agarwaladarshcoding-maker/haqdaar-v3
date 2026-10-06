"""Step 5: the line rings the caller back by itself. Fake clock, fake place_call, fake live check."""
import json
import os

import pytest

from haqdaar.photo import cases
from tools import photo_back

NUMBER = "+919876543210"
URL = "https://line.example/answer"


class Clock:
    def __init__(self):
        self.t = 1_700_000_000.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTO_DIR", str(tmp_path))
    monkeypatch.setenv("PHOTO_BACK_URL", URL)
    monkeypatch.setenv("PHOTO_BACK_WAIT_S", "20")
    clock, calls, lines, bells = Clock(), [], [], []

    def make(place=None, live=lambda u: False, dry=False):
        return photo_back.PhotoBack(dry=dry, now=clock.now, sleep=clock.sleep, place=place or (lambda n, u: calls.append((n, u)) or "CA123"),
                                    live=live, out=lines.append, bell=lambda: bells.append(1),
                                    send=lambda token, why: None)      # never the real SMS / voice from a test
    return make, clock, calls, lines, bells, tmp_path


def _file(tmp_path, clock, number=NUMBER, age=0.0):
    case = cases.new_case("hi", number)
    p = tmp_path / "next_call.json"
    p.write_text(json.dumps({"token": case.token, "lang": "hi", "say": "ok", "made": case.made}))
    os.utime(p, (clock.t - age, clock.t - age))
    return case


def test_no_file_nothing_happens(env):
    make, clock, calls, lines, bells, _ = env
    make().look()
    assert calls == [] and lines == []


def test_new_file_one_call_and_the_same_file_again_no_second_call(env):
    make, clock, calls, lines, bells, tmp = env
    pb = make()
    _file(tmp, clock)
    pb.look()
    pb.look()
    assert calls == [(NUMBER, URL)] and 20 in clock.sleeps
    assert len(lines) == 1 and "CA123" in lines[0]


def test_no_number_or_no_address_says_ready_and_rings_the_bell(env, monkeypatch):
    make, clock, calls, lines, bells, tmp = env
    _file(tmp, clock, number="")
    pb = make(); pb.look()
    assert calls == [] and "make mac-call" in lines[0] and bells == [1]
    monkeypatch.delenv("PHOTO_BACK_URL")
    _file(tmp, clock)
    pb = make(); pb.look()
    assert calls == [] and "make mac-call" in lines[-1]


def test_old_file_is_skipped_and_a_broken_file_does_not_crash(env):
    make, clock, calls, lines, bells, tmp = env
    _file(tmp, clock, age=31 * 60)
    pb = make(); pb.look()
    assert calls == [] and "older than 30 minutes" in lines[0]
    (tmp / "next_call.json").write_text("{not json")
    pb.look()
    assert calls == []


def test_a_failing_call_is_tried_twice_then_dropped(env):
    make, clock, calls, lines, bells, tmp = env
    def boom(n, u):
        calls.append(1)
        raise RuntimeError("no")
    _file(tmp, clock)
    pb = make(place=boom); pb.look(); pb.look()
    assert len(calls) == 2 and "giving up" in lines[-1] and photo_back.RETRY_S in clock.sleeps


def test_waits_while_a_call_is_live_and_a_second_file_waits_ten_minutes(env):
    make, clock, calls, lines, bells, tmp = env
    states = iter([True, True, False])
    pb = make(live=lambda u: next(states, False))
    _file(tmp, clock); pb.look()
    assert len(calls) == 1 and clock.sleeps.count(2) == 2
    first = clock.t
    _file(tmp, clock); pb.look()
    assert len(calls) == 2 and clock.t - first >= photo_back.SPACE_S - 1


def test_dry_places_nothing_and_no_number_is_printed_in_full(env):
    make, clock, calls, lines, bells, tmp = env
    _file(tmp, clock)
    pb = make(dry=True); pb.look()
    assert calls == [] and "(dry)" in lines[0]
    pb2 = make(); _file(tmp, clock); pb2.look()
    assert all("9876543210" not in l and NUMBER not in l for l in lines)


def test_server_live_route_says_if_a_call_is_live(monkeypatch):
    from fastapi.testclient import TestClient
    from haqdaar import server
    client = TestClient(server.app)
    assert client.get("/live").json() == {"active": False}
    monkeypatch.setattr(server, "_ACTIVE_CALL", True)
    assert client.get("/live").json() == {"active": True}
