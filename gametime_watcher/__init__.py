"""Gametime ticket-price watcher.

A small, dependency-free toolkit for listing current Gametime ticket prices for
an event and alerting when a desired number of seats in chosen sections drops
below a target per-ticket price.

Public API:
    extract_event_id(url_or_id)      -> str
    fetch_event_html(event_id, ...)  -> str
    parse_event(html)                -> Event
    parse_listings(html)             -> list[Listing]
    search_events(query, ...)        -> list[Event]
    get_performer_events(id, ...)    -> list[Event]
    SectionMatcher.parse(spec)       -> SectionMatcher
    filter_listings(...)             -> list[Listing]
"""

__version__ = "0.0.0"

from .api import extract_event_id, fetch_event_html, get_performer_events, parse_event, parse_listings, search_events
from .filters import SectionMatcher, filter_listings
from .models import Event, Listing

__all__ = [
    "Event",
    "Listing",
    "SectionMatcher",
    "extract_event_id",
    "fetch_event_html",
    "filter_listings",
    "get_performer_events",
    "parse_event",
    "parse_listings",
    "search_events",
]
