"""Tests for section matching and listing filtering."""

import pytest

from gametime_watcher.filters import SectionMatcher, filter_listings
from gametime_watcher.models import Listing


def make(listing_id, section, total, lots, group=None, row="1"):
    return Listing(
        id=listing_id,
        section=section,
        section_group=group,
        row=row,
        seats=["1", "2"],
        available_lots=lots,
        price_total=total,
        face_value=None,
    )


@pytest.fixture
def listings():
    return [
        make("a", "117", 3800, [2], group="Field Level"),
        make("b", "201", 10100, [2, 4], group="Solon Club"),
        make("c", "203", 9500, [2], group="Solon Club"),
        make("d", "119", 5000, [1, 2], group="Senate"),
        make("e", "Lawn", 3000, [4], group="General Admission"),
    ]


# --- SectionMatcher ---------------------------------------------------------


def test_empty_matcher_matches_all(listings):
    m = SectionMatcher.parse(None)
    assert m.is_empty
    assert all(m.matches(listing) for listing in listings)


def test_range_matches_numeric_sections(listings):
    m = SectionMatcher.parse("200-299")
    matched = {listing.id for listing in listings if m.matches(listing)}
    assert matched == {"b", "c"}


def test_reversed_range_is_normalized(listings):
    assert SectionMatcher.parse("299-200").matches(make("x", "250", 1, [2]))


def test_exact_numeric_section(listings):
    m = SectionMatcher.parse("119")
    assert {listing.id for listing in listings if m.matches(listing)} == {"d"}


def test_group_name_is_case_insensitive_substring(listings):
    m = SectionMatcher.parse("solon club")
    assert {listing.id for listing in listings if m.matches(listing)} == {"b", "c"}


def test_name_token_matches_non_numeric_section_label(listings):
    m = SectionMatcher.parse("Lawn")
    assert {listing.id for listing in listings if m.matches(listing)} == {"e"}


def test_multiple_tokens_are_ored(listings):
    m = SectionMatcher.parse("200-299, 117")
    assert {listing.id for listing in listings if m.matches(listing)} == {"a", "b", "c"}


def test_parse_accepts_sequence_spec(listings):
    m = SectionMatcher.parse(["200-299", "119"])
    assert {listing.id for listing in listings if m.matches(listing)} == {"b", "c", "d"}


# --- can_buy ----------------------------------------------------------------


def test_can_buy_requires_exact_lot():
    listing = make("x", "100", 1000, [4])
    assert listing.can_buy(4) is True
    assert listing.can_buy(2) is False


def test_can_buy_allow_larger():
    listing = make("x", "100", 1000, [4])
    assert listing.can_buy(2, allow_larger=True) is True
    assert listing.can_buy(5, allow_larger=True) is False


# --- filter_listings --------------------------------------------------------


def test_filter_200s_two_seats_under_100(listings):
    out = filter_listings(listings, sections="200-299", quantity=2, max_price_dollars=100)
    # Only section 203 ($95) qualifies; 201 is $101.
    assert [listing.id for listing in out] == ["c"]


def test_filter_sorted_cheapest_first(listings):
    out = filter_listings(listings, quantity=2)
    # 'e' needs lot of 4, excluded; order by price: a(38), d(50), c(95), b(101)
    assert [listing.id for listing in out] == ["a", "d", "c", "b"]


def test_filter_quantity_excludes_unavailable_lot(listings):
    out = filter_listings(listings, quantity=4)
    # lots containing 4: b ([2,4]) and e ([4])
    assert {listing.id for listing in out} == {"b", "e"}


def test_filter_allow_larger(listings):
    out = filter_listings(listings, sections="Lawn", quantity=2, allow_larger=True)
    assert [listing.id for listing in out] == ["e"]


def test_filter_max_price_boundary_inclusive(listings):
    # 201 is exactly $101.00; threshold 101 keeps it, 100.99 drops it.
    assert any(listing.id == "b" for listing in filter_listings(listings, max_price_dollars=101))
    assert not any(listing.id == "b" for listing in filter_listings(listings, max_price_dollars=100.99))


def test_filter_accepts_prebuilt_matcher(listings):
    matcher = SectionMatcher.parse("200-299")
    out = filter_listings(listings, sections=matcher, quantity=2)
    assert {listing.id for listing in out} == {"b", "c"}


# --- Alphabetic range matching -----------------------------------------------


def test_alpha_range_matches_letter_sections():
    a = make("a", "A", 1000, [2])
    b = make("b", "B", 1000, [2])
    c = make("c", "C", 1000, [2])
    d = make("d", "D", 1000, [2])
    e = make("e", "E", 1000, [2])
    num = make("n", "117", 1000, [2])
    m = SectionMatcher.parse("A-D")
    assert {listing.id for listing in [a, b, c, d, e, num] if m.matches(listing)} == {"a", "b", "c", "d"}


def test_alpha_range_case_insensitive():
    lower = make("lo", "b", 1000, [2])
    upper = make("up", "B", 1000, [2])
    m = SectionMatcher.parse("a-d")
    assert m.matches(lower)
    assert m.matches(upper)


def test_alpha_range_reversed_is_normalized():
    c = make("c", "C", 1000, [2])
    m = SectionMatcher.parse("D-A")
    assert m.matches(c)


def test_alpha_range_single_letter():
    a = make("a", "A", 1000, [2])
    b = make("b", "B", 1000, [2])
    m = SectionMatcher.parse("A-A")
    assert m.matches(a)
    assert not m.matches(b)


def test_alpha_range_combined_with_numeric():
    a = make("a", "A", 1000, [2])
    s117 = make("s", "117", 1000, [2])
    s200 = make("s2", "200", 1000, [2])
    m = SectionMatcher.parse("A-C, 200-299")
    assert m.matches(a)
    assert not m.matches(s117)
    assert m.matches(s200)
