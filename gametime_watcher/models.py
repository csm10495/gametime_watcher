"""Data models for Gametime listings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Listing:
    """A single resale ticket listing for an event.

    Prices are stored in whole cents (as Gametime returns them). ``price_total``
    is the *all-in price per ticket* (what the buyer pays for one seat,
    including fees), matching the price shown on gametime.co.
    """

    id: str
    section: str
    section_group: Optional[str]
    row: Optional[str]
    seats: List[str]
    # Group sizes that can be purchased, e.g. [2, 4] means you may buy 2 or 4.
    available_lots: List[int]
    price_total: int  # all-in price per ticket, in cents
    face_value: Optional[int]  # in cents, if known
    event_id: Optional[str] = None
    url: Optional[str] = None

    @property
    def price_total_dollars(self) -> float:
        """All-in per-ticket price in dollars."""
        return self.price_total / 100.0

    @property
    def face_value_dollars(self) -> Optional[float]:
        if self.face_value is None:
            return None
        return self.face_value / 100.0

    @property
    def section_is_numeric(self) -> bool:
        return self.section.isdigit()

    @property
    def section_number(self) -> Optional[int]:
        return int(self.section) if self.section.isdigit() else None

    def can_buy(self, quantity: int, allow_larger: bool = False) -> bool:
        """Whether ``quantity`` seats can be purchased from this listing.

        By default Gametime only lets you buy one of the exact offered lot
        sizes, so this checks membership in ``available_lots``. With
        ``allow_larger`` it also accepts any offered lot larger than the
        requested quantity.
        """
        if quantity in self.available_lots:
            return True
        if allow_larger and any(lot >= quantity for lot in self.available_lots):
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "section": self.section,
            "section_group": self.section_group,
            "row": self.row,
            "seats": self.seats,
            "available_lots": self.available_lots,
            "price_total_cents": self.price_total,
            "price_total_dollars": round(self.price_total_dollars, 2),
            "face_value_cents": self.face_value,
            "event_id": self.event_id,
            "url": self.url,
        }


@dataclass
class Event:
    """Lightweight metadata about an event."""

    id: str
    name: Optional[str] = None
    datetime_local: Optional[str] = None
    venue_id: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "datetime_local": self.datetime_local,
            "venue_id": self.venue_id,
        }
