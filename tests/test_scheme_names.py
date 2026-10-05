"""Step 1.3a (a): short names people say, found by name search. No model."""
from haqdaar.data import scheme_index

# What the caller says -> the scheme that must come back by="name" first.
# From PLAN 1.3 additions + fixtures/talk_human.json name-1..name-7.
SAID_NAMES = [
    ("पीएम किसान", "pm-kisan"),
    ("पीएम किसान योजना के बारे में बताइए", "pm-kisan"),
    ("pm kisan", "pm-kisan"),
    ("किसान सम्मान निधि", "pm-kisan"),
    ("मनरेगा", "mgnrega"),
    ("मनरेगा जॉब कार्ड", "mgnrega"),
    ("केसीसी", "kcc"),
    ("केसीसी कैसे बनता है", "kcc"),
    ("pm awas", "pmay-g"),
    ("स्वनिधि", "pm-svanidhi"),
    ("स्वनिधि योजना", "pm-svanidhi"),
    ("मुद्रा लोन", "pmmy"),
    ("mudra loan", "pmmy"),
    ("फसल बीमा", "pmfby"),
    ("अटल पेंशन", "apy"),
    ("विधवा पेंशन", "ignwps"),
]


def _index():
    idx = scheme_index.SchemeIndex.load("CURRENT", embed=lambda texts: 1 / 0)
    assert idx._vectors is None  # name search only, no model
    return idx


def test_short_names_are_found_by_name():
    idx = _index()
    missed = []
    for said, want in SAID_NAMES:
        top = idx.search(said, 1)
        if not top or top[0].scheme_id != want or top[0].by != "name":
            missed.append((said, want, [(h.scheme_id, h.by) for h in top]))
    assert not missed, missed


def test_full_names_still_win_by_name():
    idx = _index()
    assert idx.search("किसान क्रेडिट कार्ड कैसे बनता है", 1)[0].scheme_id == "kcc"
    assert idx.search("जननी सुरक्षा योजना", 1)[0].scheme_id == "jsy1"
    assert idx.search("Atal Pension Yojana", 1)[0].scheme_id == "apy"


def _no_name_hit(idx, said, scheme):
    return [h for h in idx.search(said, 5) if h.scheme_id == scheme and h.by == "name"]


def test_short_names_match_whole_words_only():
    """1.3b (H): a short name inside another word is not a name."""
    idx = _index()
    assert _no_name_hit(idx, "समुद्र के पास रहता हूँ", "pmmy") == []
    assert _no_name_hit(idx, "मुद्रा की कमी है", "pmmy") == []
    assert _no_name_hit(idx, "मेरी आजीविका चली गई", "day-nrlm") == []
    assert _no_name_hit(idx, "my family benefit from farming", "nfbs") == []
    # A bare common word is not the Kisan Credit Card's name.
    assert _no_name_hit(idx, "किसानों को हर साल पैसा मिलता है वो योजना", "kcc") == []
    # But said with योजना / लोन / scheme / loan next to it, they still match.
    assert idx.search("मुद्रा लोन चाहिए", 1)[0].scheme_id == "pmmy"
    assert idx.search("मुद्रा योजना के बारे में बताओ", 1)[0].scheme_id == "pmmy"
    assert idx.search("mudra loan", 1)[0].scheme_id == "pmmy"


def test_short_name_keys_are_scheme_ids():
    """1.3b (I): every key of the short-name data file is a scheme we hold."""
    import json
    from pathlib import Path
    from haqdaar.data import scheme_names
    path = Path(scheme_names.__file__).resolve().parent.parent.parent / "fixtures" / "scheme_short_names.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = set(scheme_index.SchemeIndex.load("CURRENT", embed=lambda texts: 1 / 0).ids)
    assert set(data["short_names"]) <= ids, set(data["short_names"]) - ids
    assert set(data["short_names"]) >= {"pm-kisan", "kcc", "pmmy", "pmay-g", "mgnrega"}
    assert scheme_names.short_names_for("pm-kisan") == tuple(data["short_names"]["pm-kisan"])
