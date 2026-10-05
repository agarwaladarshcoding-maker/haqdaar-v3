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
