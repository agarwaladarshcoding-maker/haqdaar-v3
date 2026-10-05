"""Step 1.3a (b): four kinds of turn, by code. No model."""
from haqdaar.data import scheme_index, scheme_names
from haqdaar.engine import talk_kind


def _index():
    return scheme_index.SchemeIndex.load("CURRENT", embed=lambda texts: 1 / 0)


def test_not_held_list_names_the_four_schemes():
    assert scheme_names.find_not_held("आयुष्मान कार्ड मिलेगा क्या") == "ayushman"
    assert scheme_names.find_not_held("ayushman bharat card") == "ayushman"
    assert scheme_names.find_not_held("राशन कार्ड चाहिए") == "ration_card"
    assert scheme_names.find_not_held("i want a ration card") == "ration_card"
    assert scheme_names.find_not_held("लाडली बहना योजना") == "ladli_behna"
    assert scheme_names.find_not_held("ladli behna ke paise") == "ladli_behna"
    assert scheme_names.find_not_held("उज्ज्वला गैस चाहिए") == "ujjwala"
    assert scheme_names.find_not_held("ujjwala gas connection") == "ujjwala"
    assert scheme_names.find_not_held("मुझे खेती के लिए मदद चाहिए") == ""
    assert scheme_names.find_not_held("पीएम किसान") == ""


def test_four_kinds_are_told_apart():
    idx = _index()
    assert talk_kind.kind("पीएम किसान", idx) == "held_scheme"
    assert talk_kind.kind("tell me about mudra loan", idx) == "held_scheme"
    assert talk_kind.kind("आयुष्मान कार्ड मिलेगा क्या", idx) == "not_held_scheme"
    assert talk_kind.kind("राशन कार्ड चाहिए", idx) == "not_held_scheme"
    assert talk_kind.kind("लाडली बहना के पैसे कब आएंगे", idx) == "not_held_scheme"
    assert talk_kind.kind("उज्ज्वला गैस चाहिए", idx) == "not_held_scheme"
    assert talk_kind.kind("पीएम किसान में कितना पैसा मिलता है", idx) == "held_scheme"
    assert talk_kind.kind("how much money does it give", idx) == "question"
    assert talk_kind.kind("पैसा कब मिलेगा?", idx) == "question"
    assert talk_kind.kind("मेरी फसल खराब हो गई", idx) == "situation"
    assert talk_kind.kind("my husband was a farmer", idx) == "situation"
    assert talk_kind.kind("मैं किसान हूँ", idx) == "situation"
    assert talk_kind.kind("पैसे की तंगी है", idx) == "situation"


def test_marathi_kaa_inside_hindi_is_no_question():
    """1.3b (J): "का" (of) inside a Hindi sentence is not a question word."""
    assert not talk_kind.is_question("मेरे पति का देहांत हो गया")
    assert talk_kind.kind("मेरे पति का देहांत हो गया", _index()) == "situation"
    # Sentence-final "का" still asks (Marathi "will you come?").
    assert talk_kind.is_question("तुम्ही येणार का")
