"""tools/mac_call.py: the parts that need no sound device and no network."""
import audioop
import struct

from tools.mac_call import FRAME, PlayQueue, Resampler, split_frames


def test_split_frames_keeps_remainder():
    frames, rest = split_frames(b"\x01" * (FRAME * 2 + 50))
    assert [len(f) for f in frames] == [160, 160]
    assert len(rest) == 50
    frames, rest = split_frames(rest + b"\x01" * (FRAME - 50))
    assert len(frames) == 1 and rest == b""


def test_mark_comes_after_its_sound_is_pulled():
    q = PlayQueue()
    q.push_sound(b"\x10" * 300)
    q.push_mark("a")
    out, done = q.pull(160)
    assert out == b"\x10" * 160 and done == []
    out, done = q.pull(160)
    assert out == b"\x10" * 140 + b"\xff" * 20 and done == ["a"]


def test_two_marks_in_order():
    q = PlayQueue()
    q.push_sound(b"\x10" * 100)
    q.push_mark("a")
    q.push_sound(b"\x20" * 100)
    q.push_mark("b")
    out, done = q.pull(160)
    assert done == ["a"] and out == b"\x10" * 100 + b"\x20" * 60
    out, done = q.pull(160)
    assert done == ["b"]


def test_clear_drops_sound_and_gives_all_marks():
    q = PlayQueue()
    q.push_sound(b"\x10" * 500)
    q.push_mark("a")
    q.push_sound(b"\x10" * 500)
    q.push_mark("b")
    assert q.speaking()
    assert q.clear() == ["a", "b"]
    assert not q.speaking()
    assert q.pull(FRAME) == (b"\xff" * FRAME, [])


def test_empty_queue_gives_silence():
    assert PlayQueue().pull(40) == (b"\xff" * 40, [])


def test_resample_48k_to_8k_and_state_kept():
    pcm = struct.pack("<480h", *[int(8000 * ((i % 48) / 48 - 0.5)) for i in range(480)])   # 10 ms at 48 kHz
    r = Resampler(48000, 8000)
    first = r.feed(pcm)
    assert abs(len(first) // 2 - 80) <= 2
    assert r.state is not None
    second = r.feed(pcm)
    assert abs(len(second) // 2 - 80) <= 2
    # the same two blocks in one go give the same sound: state really carried over
    whole, _ = audioop.ratecv(pcm + pcm, 2, 1, 48000, 8000, None)
    assert first + second == whole


def test_same_rate_is_passed_through():
    assert Resampler(8000, 8000).feed(b"\x00\x01" * 10) == b"\x00\x01" * 10


def test_screen_shows_heard_said_and_times():
    from tools.mac_call import show

    assert show({"ev": "heard", "text": "I want a loan"}) == ("YOU", "I want a loan")
    assert show({"ev": "said", "text": "नमस्ते", "en": "Hello"}) == ("AGENT", "नमस्ते   [Hello]")
    assert show({"ev": "said", "text": "Hello", "en": ""}) == ("AGENT", "Hello")
    who, words = show({"ev": "act", "action": "show_scheme", "scheme": "pm-kisan", "stt_ms": 300,
                       "search_ms": 50, "model_ms": 700, "voice_ms": 200, "wait_ms": 1900})
    assert who == "" and "show_scheme pm-kisan" in words and "reply after 1.9 s" in words and "model 700 ms" in words
    assert show({"ev": "key", "key": "1", "means": "language = Hindi"}) == ("KEY", "1  (language = Hindi)")
    assert show({"turn_n": 1, "class": "ANSWER", "box": "category", "value": "farming"}) == ("", "noted: category = farming")
    assert show({"lang": "en", "lang_source": "voice", "turn_n": 0}) == ("", "language: English (by voice)")
    assert show({"ev": "blocked", "rule": "number", "text": "x"})[0] == "!"


def test_screen_leaves_out_the_plumbing_rows():
    from tools.mac_call import show

    assert show({"call_id": "mac_1", "snapshot_id": "s", "lang": "hi", "lang_source": "default", "t0": 0.0}) is None
    assert show({"turn_n": 0, "class": "ANSWER", "transcript": "en"}) is None
    assert show({"stop": "zero_survivors", "ladder_rung": 0, "mode": "voice"}) is None


def test_log_tail_gives_each_whole_row_once(tmp_path):
    from tools.mac_call import LogTail

    path = tmp_path / "mac_1.jsonl"
    tail = LogTail(path)
    assert tail.rows() == []                                  # no file yet
    path.write_bytes('{"ev": "heard", "text": "नमस्ते"}\n{"ev": "sa'.encode())
    assert tail.rows() == [{"ev": "heard", "text": "नमस्ते"}]   # the half line waits
    with open(path, "ab") as f:
        f.write(b'id", "text": "hi"}\nnot json\n')
    assert tail.rows() == [{"ev": "said", "text": "hi"}]
    assert tail.rows() == []


def test_wait_for_answer_rings_back_when_the_answer_is_ready(monkeypatch):
    from haqdaar.photo import in_call
    from tools import mac_call

    seen = iter([None, None, {"token": "t"}])
    monkeypatch.setattr(in_call, "pending", lambda: next(seen))
    monkeypatch.setattr(mac_call.time, "sleep", lambda s: None)
    assert mac_call.wait_for_answer(60) is True


def test_wait_for_answer_gives_up_in_time(monkeypatch):
    from haqdaar.photo import in_call
    from tools import mac_call

    monkeypatch.setattr(in_call, "pending", lambda: None)
    monkeypatch.setattr(mac_call.time, "sleep", lambda s: None)
    assert mac_call.wait_for_answer(0.01) is False


def test_wait_for_answer_has_no_clock_by_default(monkeypatch):
    """Owner, 6 Oct: no 60 s timer. The call comes when the answer is ready, however long the photo takes."""
    from haqdaar.photo import in_call
    from tools import mac_call

    now = [1000.0]
    monkeypatch.setattr(mac_call.time, "time", lambda: now[0])
    monkeypatch.setattr(mac_call.time, "sleep", lambda s: now.__setitem__(0, now[0] + 600))     # ten minutes a look
    seen = iter([None] * 30 + [{"token": "t"}])
    monkeypatch.setattr(in_call, "pending", lambda: next(seen))
    assert mac_call.wait_for_answer() is True


def test_cut_in_only_when_the_sound_goes_into_the_ears():
    from tools.mac_call import cut_in_safe

    assert cut_in_safe("Adarsh's OnePlus Nord Buds 3r") and cut_in_safe("External Headphones")
    assert not cut_in_safe("MacBook Air Speakers")
