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


# --- step 1.3b: "not" that hides a need vs "not" that takes away ---------------


def test_have_no_x_is_a_need_for_x():
    """"I have no X" / "X नहीं है" / "X नहीं मिला" names the need (D)."""
    corpus = _corpus()
    assert talk_words.spot("मेरे पास नौकरी नहीं है", corpus) == {"category": "jobs_skills"}
    assert talk_words.spot("I have no job", corpus) == {"category": "jobs_skills"}
    assert talk_words.spot("मेरे पास घर नहीं है", corpus) == {"category": "housing"}
    assert talk_words.spot("मुझे लोन नहीं मिला", corpus) == {"category": "business_loans"}
    assert talk_words.spot("I did not get any loan", corpus) == {"category": "business_loans"}


def test_am_not_x_takes_x_away():
    """Only "I am not X" / "I do not want X" unsets (E)."""
    corpus = _corpus()
    assert talk_words.spot("I am not a street vendor", corpus) == {}
    assert talk_words.spot("I don't want any loan", corpus) == {}
    assert talk_words.spot("main kisan nahi hoon", corpus) == {}
    assert talk_words.spot("main kisan nahin hoon", corpus) == {}
    assert talk_words.spot("मुझे लोन मत दो", corpus) == {}
    # A no-comma contrast keeps the affirmed work.
    assert talk_words.spot("मैं किसान नहीं मज़दूर हूँ", corpus) == {"occupation": "worker"}


def test_gender_needs_whole_words_about_the_caller():
    """F: "मां" inside "मांगना" is not female; a wife's death is not hers."""
    corpus = _corpus()
    assert talk_words.spot("मुझे लोन मांगना है", corpus) == {"category": "business_loans"}
    assert talk_words.spot("my wife died I am a farmer", corpus) == {
        "category": "farming", "occupation": "farmer"}
    # A mother named as the one helped keeps her female.
    assert talk_words.spot("मेरी माँ के लिए पेंशन चाहिए", corpus) == {
        "category": "pension", "gender": "female"}


def test_caller_work_next_to_other_person_words():
    """G: no comma, or a "brother" call-out, keeps the caller's own work."""
    corpus = _corpus()
    assert talk_words.spot("मेरा बेटा पढ़ता है मैं मजदूरी करती हूँ", corpus) == {
        "occupation": "worker"}
    assert talk_words.spot("भाई मैं किसान हूँ", corpus) == {
        "category": "farming", "occupation": "farmer"}
    # The old comma cases still hold.
    assert "occupation" not in talk_words.spot("my husband was a farmer", corpus)
    assert "occupation" not in talk_words.spot("मेरे पति किसान थे", corpus)
