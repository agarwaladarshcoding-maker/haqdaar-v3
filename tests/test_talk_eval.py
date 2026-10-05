"""7.14 (B6.b): a small cut of the scripted talk calls; the whole set is `make talk-eval`."""
from tools import talk_eval


def test_scripted_talk_calls_keep_the_rules_with_the_gate_off_and_on():
    cases = talk_eval.run_all(scripts=["ask", "sidetalk"], places=6)
    assert len(cases) >= 150
    assert [(c["n"], c["kind"], c["bad"]) for c in cases if c["bad"]] == []
    on = [c for c in cases if c["gate"]]
    off = [c for c in cases if not c["gate"]]
    # with the gate on the agent is stopped by voice; with it off only a key or the "one moment" stop does it
    assert sum(len(c["res"].clears) for c in on) > sum(len(c["res"].clears) for c in off)


def test_the_rules_catch_a_bad_call():
    case = talk_eval.run_all(scripts=["ask"], kinds=["hmm"], places=1)[0]
    res = case["res"]
    assert talk_eval.check(res) == []
    said = [r for r in res.log_rows if r.get("ev") == "said" and r.get("tokens") == ["answer"]]
    res.log_rows.insert(res.log_rows.index(said[-1]), dict(said[-1]))
    assert any(line.startswith("R3") for line in talk_eval.check(res))
    res.clips = [c for c in res.clips if c["name"] != "answer"]
    assert any(line.startswith("R2") for line in talk_eval.check(res))
