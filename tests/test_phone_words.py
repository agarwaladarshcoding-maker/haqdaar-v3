"""Step A: the text on the phone follows the caller's languages. The look of the phone is not tested here
(it is the same style and mark-up; see the diff). No network, no SMS, no money."""
import re
import threading
import time
from pathlib import Path

import pytest

from haqdaar.photo import cases, in_call
from tools import mac_call

APP = Path(__file__).parent.parent / "keypad_app"
CODES = ("hi", "mr", "en", "gu", "ta")
DEVANAGARI = re.compile("[ऀ-ॿ]")


def _words(code):
    text = (APP / "words" / f"{code}.js").read_text(encoding="utf-8")
    assert text.startswith(f"W.{code}={{")
    return dict(re.findall(r'^"?(\w+)"?:"(.*)",?$', text, re.M))


@pytest.fixture
def photo_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTO_DIR", str(tmp_path / "photo"))
    monkeypatch.delenv("CALL_ME_NUMBER", raising=False)


def test_every_words_file_has_the_same_keys():
    keys = {c: set(_words(c)) for c in CODES}
    assert len(keys["en"]) > 20
    assert all(k == keys["en"] for k in keys.values())
    assert all(all(v.strip() for v in _words(c).values()) for c in CODES)


def test_index_page_is_under_the_limit_and_takes_its_words_from_files():
    page = (APP / "index.html").read_text(encoding="utf-8")
    assert len(page.encode()) < 20480
    assert "langs=" in page and "words/" in page


def test_pages_hold_no_fixed_devanagari_text():
    # The English fallback is the only text left in the two pages; every Hindi, Marathi, Gujarati and
    # Tamil word is in a words file.
    for name in ("index.html", "demo.html"):
        page = (APP / name).read_text(encoding="utf-8")
        assert not DEVANAGARI.search(page) and not re.search("[઀-૿஀-௿]", page), name


def test_the_english_fallback_in_index_is_the_en_words_file():
    page = (APP / "index.html").read_text(encoding="utf-8")
    table = dict(re.findall(r"(\w+):'([^']*)'", re.search(r"var E=\{(.*?)\};", page).group(1)))
    en = _words("en")
    assert table and all(en[k] == v for k, v in table.items())


def test_the_demo_page_keeps_its_english_and_passes_the_languages_on():
    page = (APP / "demo.html").read_text(encoding="utf-8")
    assert "Open the Haqdaar app" in page and "index.html?embed=1" in page and "MOBILE DATA" in page
    assert page.count("+LQ") == 2          # data ON and data OFF
    en = _words("en")
    for k in ("nonet", "nolink", "opening", "sms"):
        assert f"'{en[k]}'" in page


@pytest.mark.parametrize("code", CODES)
def test_sms_text_of_the_server_is_the_one_of_the_demo(code):
    assert in_call.SMS_TEXTS[code] == _words(code)["sms"]
    assert "{link}" in in_call.SMS_TEXTS[code]


def test_send_link_puts_the_last_language_first_and_prints_langs(photo_dir, monkeypatch, capsys):
    from haqdaar.contracts import tunables
    monkeypatch.setattr(tunables, "PHOTO_SHOW_LINK", True)
    out = in_call.send_link("mr", ["hi", "mr", "en", "hi"], "")
    case = cases.get(out["token"])
    assert case.lang == "mr" and case.langs == ["mr", "hi", "en"]
    assert capsys.readouterr().out == f"PHOTO LINK: {out['link']} LANGS: mr,hi,en\n"


@pytest.mark.parametrize("code", ["hi", "mr", "gu", "ta", "en"])
def test_sms_text_follows_the_main_language_and_holds_the_link(photo_dir, code):
    sent = []
    out = in_call.send_link(code, ["en", code], "+919999900001", sms=lambda to, text: sent.append(text))
    assert sent == [in_call.SMS_TEXTS[code].format(link=out["link"])] and out["link"] in sent[0]


def test_sms_text_for_a_language_with_no_sms_words_is_english_and_the_case_keeps_the_language(photo_dir):
    """6 Oct: the case keeps every Sarvam language (the call-back speaks it); the link SMS has 5 and falls to English."""
    sent = []
    out = in_call.send_link("bn", ["bn"], "+919999900001", sms=lambda to, text: sent.append(text))
    assert cases.get(out["token"]).lang == "bn" and sent == [in_call.SMS_TEXT.format(link=out["link"])]
    out = in_call.send_link("xx", ["xx"], "+919999900001", sms=lambda to, text: sent.append(text))
    assert cases.get(out["token"]).lang == "hi"                     # not a Sarvam language: Hindi, as before


def _watch(tmp_path, monkeypatch, line, demo_up=True):
    opened = []
    monkeypatch.setattr(mac_call.webbrowser, "open", lambda u: opened.append(u))
    monkeypatch.setattr(mac_call, "say", lambda *a, **k: None)

    def conn(addr, timeout=0):
        if addr[1] == 8080 and not demo_up:
            raise OSError
        return type("S", (), {"close": lambda self: None})()
    monkeypatch.setattr(mac_call.socket, "create_connection", conn)
    log = tmp_path / "server.log"
    log.write_text("")
    stop = threading.Event()
    t = threading.Thread(target=mac_call.watch_photo_link, args=(str(log), stop))
    t.start()
    time.sleep(0.4)
    with open(log, "a") as f:
        f.write(line)
    for _ in range(50):
        if opened:
            break
        time.sleep(0.1)
    stop.set()
    t.join(3)
    return opened


def test_mac_call_opens_the_demo_with_the_languages(tmp_path, monkeypatch):
    got = _watch(tmp_path, monkeypatch, "PHOTO LINK: http://h:8002/p/abc123 LANGS: hi,mr\n")
    assert got == ["http://127.0.0.1:8080/demo.html?link=http%3A%2F%2Fh%3A8002%2Fp%2Fabc123&langs=hi,mr"]


def test_mac_call_old_link_line_with_no_langs_still_opens(tmp_path, monkeypatch):
    got = _watch(tmp_path, monkeypatch, "PHOTO LINK: http://h:8002/p/abc123\n")
    assert got == ["http://127.0.0.1:8080/demo.html?link=http%3A%2F%2Fh%3A8002%2Fp%2Fabc123"]


def test_mac_call_opens_the_plain_link_when_the_demo_is_not_running(tmp_path, monkeypatch):
    got = _watch(tmp_path, monkeypatch, "PHOTO LINK: http://h:8002/p/abc123 LANGS: hi\n", demo_up=False)
    assert got == ["http://h:8002/p/abc123"]
