"""tests/test_vocab.py

Unit tests for haqdaar/contracts/vocab.py (D6, step 1.4).
"""
from haqdaar.contracts import vocab


def test_keypad_lists_have_1_to_9_unique_values():
    for box, values in vocab.KEYPAD_LISTS.items():
        assert 1 <= len(values) <= 9, f"{box} has {len(values)} values, must be 1..9"
        assert len(values) == len(set(values)), f"{box} has duplicate values"


def test_every_keypad_value_has_trilingual_labels():
    for box, values in vocab.KEYPAD_LISTS.items():
        for value in values:
            assert value in vocab.LABELS, f"{box} value {value!r} has no LABELS entry"
            labels = vocab.LABELS[value]
            for lang in ("en", "hi", "mr"):
                assert labels.get(lang), f"{box} value {value!r} has no {lang} label"


def test_old_category_map_values_are_all_in_category():
    for old, new in vocab.OLD_CATEGORY_MAP.items():
        assert new in vocab.CATEGORY, f"OLD_CATEGORY_MAP[{old!r}] = {new!r} not in CATEGORY"


def test_find_forbidden_does_not_flag_honest_single_words():
    assert vocab.find_forbidden("पात्रता की शर्तें", "hi") is None
    assert vocab.find_forbidden("eligible farmers get Rs 6000", "en") is None


def test_find_forbidden_flags_second_person_promises():
    assert vocab.find_forbidden("आपको ज़रूर मिलेगा", "hi") is not None
    # same text without the nukta on ज़ must still match (NFC + nukta-stripped compare)
    assert vocab.find_forbidden("आपको जरूर मिलेगा", "hi") is not None
    assert vocab.find_forbidden("You are eligible for this", "en") is not None
