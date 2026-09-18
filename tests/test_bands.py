"""Step 1.5b: age / income_band keypad bands (p6)."""
import pytest

from haqdaar.data.pipeline.p6_snapshot import _band_wholly_inside, build_range_bands


def _codes(schemes, max_bands=9):
    return [b["code"] for b in build_range_bands(schemes, "age", max_bands=max_bands)]


def test_edges_are_min_and_max_plus_one():
    schemes = [
        {"scheme_id": "a", "age": {"min": 18, "max": 40}},
        {"scheme_id": "b", "age": "ANY"},
    ]
    assert _codes(schemes) == ["0-17", "18-40", "41+"]


def test_open_ends_and_point_band():
    schemes = [
        {"scheme_id": "a", "age": {"min": 60, "max": None}},
        {"scheme_id": "b", "age": 30},
    ]
    assert _codes(schemes) == ["0-29", "30-30", "31-59", "60+"]


def test_no_constraint_gives_no_bands():
    assert _codes([{"scheme_id": "a", "age": "ANY"}]) == []


def test_bad_value_names_scheme_and_box():
    with pytest.raises(ValueError, match="x: age"):
        _codes([{"scheme_id": "x", "age": "old"}])


def test_prune_drops_least_used_edge_ties_larger():
    schemes = [
        {"scheme_id": "a", "age": {"min": 10, "max": None}},
        {"scheme_id": "b", "age": {"min": 10, "max": None}},
        {"scheme_id": "c", "age": {"min": 20, "max": None}},
        {"scheme_id": "d", "age": {"min": 30, "max": None}},
    ]
    # 4 bands -> 3: edges 20 and 30 have 1 vote each; the larger (30) goes.
    assert _codes(schemes, max_bands=3) == ["0-9", "10-19", "20+"]


def test_mask_rule_never_names_a_scheme_outside_its_range():
    # merged band 20+ reaches past a scheme that ends at 29 -> not inside
    assert not _band_wholly_inside(20, None, 20, 29)
    assert _band_wholly_inside(20, 29, 18, 40)
    assert _band_wholly_inside(0, None, None, None)
