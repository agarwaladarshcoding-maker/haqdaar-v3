"""Step 1.3a (c): the word "not", and another person's work. No model."""
from haqdaar.data.corpus import Corpus
from haqdaar.engine import talk_words


def _corpus():
    return Corpus.load("CURRENT")


def test_not_next_to_a_word_unsets_it():
    corpus = _corpus()
    assert talk_words.spot("मैं किसान नहीं हूँ", corpus) == {}
    assert talk_words.spot("मुझे लोन नहीं चाहिए", corpus) == {}
    assert talk_words.spot("i am not a farmer", corpus) == {}
    assert talk_words.spot("मुझे लोन मत दो", corpus) == {}
    assert talk_words.spot("i do not want a loan", corpus) == {}
    # "not" in another clause does not unset it.
    assert talk_words.spot("मैं किसान हूँ, लोन नहीं चाहिए", corpus) == {
        "category": "farming", "occupation": "farmer"}
    assert talk_words.spot("मैं किसान हूँ", corpus) == {"category": "farming", "occupation": "farmer"}


def test_fixture_not_cases():
    corpus = _corpus()
    got = talk_words.spot("मैं किसान नहीं हूँ, मज़दूरी करता हूँ", corpus)
    assert got.get("occupation") == "worker"
    assert "category" not in got
    assert talk_words.spot("मुझे लोन नहीं चाहिए, बस जानकारी चाहिए", corpus) == {}
    assert talk_words.spot("i am not a farmer i work in a shop", corpus).get("occupation") != "farmer"


def test_another_persons_work_is_not_the_callers():
    corpus = _corpus()
    assert "occupation" not in talk_words.spot("my husband was a farmer", corpus)
    assert "occupation" not in talk_words.spot("मेरे पति किसान थे", corpus)
    assert "occupation" not in talk_words.spot("my mother is pregnant", corpus)
    assert talk_words.spot("मैं किसान हूँ", corpus).get("occupation") == "farmer"
    assert talk_words.spot("मेरे को फार्मर स्कीम्स के बारे में जानना है", corpus).get("occupation") == "farmer"


def test_bare_home_is_a_place_not_a_housing_need():
    corpus = _corpus()
    assert talk_words.spot("घर में कोई कमाने वाला नहीं", corpus) == {}
    assert talk_words.spot("घर के लिए कुछ है क्या", corpus) == {"category": "housing"}
    assert talk_words.spot("मुझे घर चाहिए", corpus) == {"category": "housing"}


def test_spot_all_names_every_value_for_two_needs():
    corpus = _corpus()
    all_named = talk_words.spot_all("खेती और घर दोनों के लिए कुछ है क्या", corpus)
    assert set(all_named.get("category", ())) == {"farming", "housing"}
    # spot itself still fills a box only when exactly one value is named.
    assert "category" not in talk_words.spot("खेती और घर दोनों के लिए कुछ है क्या", corpus)
