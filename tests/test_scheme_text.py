"""tests/test_scheme_text.py — SchemeText (step 7.1)."""
import json

from haqdaar.contracts import tunables
from haqdaar.data.scheme_text import SchemeText


def make_snapshot(tmp_path, monkeypatch):
    snap = tmp_path / "snapshots" / "snap_x"
    snap.mkdir(parents=True)
    row = {"scheme_id": "pm-kisan", "gate_notes": ["Land in family's name."],
           "chunks": {"en": {"name": "PM Kisan", "benefit_text": "Rs. 6,000"}, "hi": {"name": "पीएम किसान"}}}
    (snap / "schemes.jsonl").write_text(json.dumps(row) + "\nnot json\n\n", encoding="utf-8")
    (tmp_path / "snapshots" / "CURRENT").write_text("snap_x\n", encoding="utf-8")
    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(tmp_path / "snapshots"))


def test_card_has_fields_and_exclusions(tmp_path, monkeypatch):
    make_snapshot(tmp_path, monkeypatch)
    card = SchemeText.load("snap_x").card("pm-kisan", "en")
    assert card.startswith("[pm-kisan]") and "benefit_text: Rs. 6,000" in card
    assert "exclusions: Land in family's name." in card
    assert "पीएम किसान" in SchemeText.load("CURRENT").card("pm-kisan", "hi")


def test_unknown_id_language_or_snapshot_gives_empty(tmp_path, monkeypatch):
    make_snapshot(tmp_path, monkeypatch)
    t = SchemeText.load("snap_x")
    assert t.card("nope", "en") == "" and t.card("pm-kisan", "mr") == "" and t.card("pm-kisan", "xx") == ""
    assert SchemeText.load("missing").card("pm-kisan", "en") == ""
