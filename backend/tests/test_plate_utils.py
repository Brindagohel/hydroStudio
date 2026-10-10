from app.utils.plate_utils import looks_like_plate, normalize_plate


def test_removes_spaces_and_uppercases():
    assert normalize_plate(" GJ 01 AB 1234 ") == "GJ01AB1234"


def test_removes_hyphens_and_symbols():
    assert normalize_plate("gj-01-ab-1234") == "GJ01AB1234"
    assert normalize_plate("GJ01 AB.1234!") == "GJ01AB1234"


def test_does_not_swap_similar_characters():
    # O and 0 are different characters, we must not guess
    assert normalize_plate("GJ01AB12O4") == "GJ01AB12O4"


def test_empty_values():
    assert normalize_plate(None) == ""
    assert normalize_plate("  - ") == ""


def test_looks_like_plate():
    assert looks_like_plate("gj 01 ab 1234")
    assert not looks_like_plate("HELLO")
