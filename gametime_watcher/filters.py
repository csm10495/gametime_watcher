"""Filtering of listings by section, price, and quantity."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Union

from .models import Listing


@dataclass
class _Range:
    low: int
    high: int

    def matches(self, listing: Listing) -> bool:
        n = listing.section_number
        return n is not None and self.low <= n <= self.high


@dataclass
class _Exact:
    value: int

    def matches(self, listing: Listing) -> bool:
        return listing.section_number == self.value


@dataclass
class _AlphaRange:
    low: str
    high: str

    def matches(self, listing: Listing) -> bool:
        s = listing.section.strip().upper()
        if len(s) != 1 or not s.isalpha():
            return False
        return self.low <= s <= self.high


@dataclass
class _Name:
    text: str

    def matches(self, listing: Listing) -> bool:
        needle = self.text.lower()
        if listing.section.lower() == needle:
            return True
        group = (listing.section_group or "").lower()
        return needle in group


_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
_ALPHA_RANGE_RE = re.compile(r"^\s*([A-Za-z])\s*-\s*([A-Za-z])\s*$")


class SectionMatcher:
    """Matches listings against a flexible section specification.

    A spec is one or more tokens (comma-separated string, or a sequence). Each
    token is one of:

      * a numeric range, e.g. ``"200-299"`` (inclusive)
      * an exact numeric section, e.g. ``"119"``
      * a section/group name, e.g. ``"Solon Club"`` (case-insensitive; matches
        the section label exactly or the section group as a substring)

    A listing matches if it satisfies *any* token. An empty spec matches all.
    """

    def __init__(self, matchers: Optional[Sequence] = None):
        self._matchers = list(matchers or [])

    @classmethod
    def parse(cls, spec: Union[str, Sequence[str], None]) -> "SectionMatcher":
        if spec is None:
            return cls([])
        tokens: List[str]
        if isinstance(spec, str):
            tokens = [t for t in (s.strip() for s in spec.split(",")) if t]
        else:
            tokens = [t.strip() for t in spec if t and t.strip()]

        matchers = []
        for token in tokens:
            rng = _RANGE_RE.match(token)
            if rng:
                low, high = int(rng.group(1)), int(rng.group(2))
                if low > high:
                    low, high = high, low
                matchers.append(_Range(low, high))
                continue
            alpha_rng = _ALPHA_RANGE_RE.match(token)
            if alpha_rng:
                low, high = alpha_rng.group(1).upper(), alpha_rng.group(2).upper()
                if low > high:
                    low, high = high, low
                matchers.append(_AlphaRange(low, high))
            elif token.isdigit():
                matchers.append(_Exact(int(token)))
            else:
                matchers.append(_Name(token))
        return cls(matchers)

    @property
    def is_empty(self) -> bool:
        return not self._matchers

    def matches(self, listing: Listing) -> bool:
        if not self._matchers:
            return True
        return any(m.matches(listing) for m in self._matchers)


def filter_listings(
    listings: Iterable[Listing],
    *,
    sections: Union[str, Sequence[str], SectionMatcher, None] = None,
    max_price_dollars: Optional[float] = None,
    quantity: Optional[int] = None,
    allow_larger: bool = False,
) -> List[Listing]:
    """Return listings matching all provided criteria, cheapest first.

    Args:
        sections: section spec (see :class:`SectionMatcher`) or a matcher.
        max_price_dollars: maximum all-in price *per ticket*, in dollars.
        quantity: number of seats you want to buy together; only listings that
            offer this lot size are kept (see :meth:`Listing.can_buy`).
        allow_larger: if True, also keep listings offering a larger lot.
    """
    matcher = sections if isinstance(sections, SectionMatcher) else SectionMatcher.parse(sections)

    result = []
    for listing in listings:
        if not matcher.matches(listing):
            continue
        if max_price_dollars is not None and listing.price_total_dollars > max_price_dollars:
            continue
        if quantity is not None and not listing.can_buy(quantity, allow_larger=allow_larger):
            continue
        result.append(listing)

    result.sort(key=lambda listing: (listing.price_total, listing.section, listing.row or ""))
    return result
