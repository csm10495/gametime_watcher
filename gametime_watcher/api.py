"""Fetching and parsing Gametime event pages.

Gametime server-renders the full set of listings for an event into the event
page HTML (inside the Next.js data stream). This module resolves an event id
from a URL or short link, downloads that page, and extracts structured
``Listing`` and ``Event`` objects from it -- no API key required.
"""

from __future__ import annotations

import gzip
import json
import re
import time
import urllib.error
import urllib.request
from typing import List, Optional

from .models import Event, Listing

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_HEX24 = re.compile(r"^[a-f0-9]{24}$")
_EVENT_ID_IN_URL = re.compile(r"/events/([a-f0-9]{24})")


class GametimeError(RuntimeError):
    """Raised when an event id cannot be resolved or a page cannot be parsed."""


def _http_get(url: str, user_agent: str, timeout: float) -> "urllib.request.addinfourl":
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/json",
            # Ask for plain text so we don't have to guess at content encoding;
            # gzip is still handled below as a fallback.
            "Accept-Encoding": "gzip, identity",
        },
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _read_body(resp) -> str:
    raw = resp.read()
    if resp.headers.get("Content-Encoding", "").lower() == "gzip":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def extract_event_id(
    url_or_id: str,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 30.0,
) -> str:
    """Resolve a Gametime event id from a URL, short link, or bare id.

    Accepts:
      * a bare 24-hex event id
      * any URL containing ``/events/<id>`` (event or listing pages)
      * a short link (e.g. ``https://gtix.co/...``) which is followed via
        HTTP redirects until an event id is found.
    """
    value = url_or_id.strip()
    if _HEX24.match(value):
        return value

    m = _EVENT_ID_IN_URL.search(value)
    if m:
        return m.group(1)

    if "://" not in value:
        raise GametimeError(
            f"Could not find an event id in {url_or_id!r}; pass a gametime.co "
            "event/listing URL, a short link, or a 24-character event id."
        )

    # Short link or other URL without an inline id: follow redirects and inspect
    # both the final URL and the response body.
    try:
        resp = _http_get(value, user_agent, timeout)
        final_url = resp.geturl()
        body_head = _read_body(resp)[:200_000]
    except urllib.error.URLError as exc:  # pragma: no cover - network failure path
        raise GametimeError(f"Failed to resolve short link {url_or_id!r}: {exc}") from exc

    m = _EVENT_ID_IN_URL.search(final_url) or _EVENT_ID_IN_URL.search(body_head)
    if m:
        return m.group(1)
    raise GametimeError(f"Could not resolve an event id from {url_or_id!r}.")


_RETRYABLE_HTTP_CODES = (502, 503, 504, 429)


def fetch_event_html(
    event_id: str,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 30.0,
    retries: int = 3,
    backoff_base: float = 1.0,
) -> str:
    """Download the server-rendered event page HTML for ``event_id``.

    Makes up to *retries* additional attempts with exponential backoff on
    transient HTTP errors (502, 503, 504, 429).
    """
    url = f"https://gametime.co/events/{event_id}"
    last_exc: Optional[Exception] = None
    for attempt in range(1 + retries):
        try:
            resp = _http_get(url, user_agent, timeout)
            return _read_body(resp)
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in _RETRYABLE_HTTP_CODES and attempt < retries:
                time.sleep(backoff_base * (2**attempt))
                continue
            raise GametimeError(f"Failed to fetch event page for {event_id!r}: {exc}") from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network failure path
            raise GametimeError(f"Failed to fetch event page for {event_id!r}: {exc}") from exc
    # Should not be reached, but just in case:
    raise GametimeError(  # pragma: no cover
        f"Failed to fetch event page for {event_id!r}: {last_exc}"
    )


def search_events(
    query: str,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 30.0,
) -> List[Event]:
    """Search Gametime for upcoming events matching ``query`` (e.g. a team name).

    Returns a list of :class:`Event` objects with ``id``, ``name``,
    ``datetime_local``, and ``extra["url"]`` populated.

    .. note::

       The search endpoint only returns ~10 results. Use
       :func:`get_performer_events` with a performer id to retrieve *all*
       upcoming events for a team/performer.
    """
    url = f"https://mobile.gametime.co/v1/search?q={urllib.request.quote(query)}"
    try:
        resp = _http_get(url, user_agent, timeout)
        body = _read_body(resp)
    except urllib.error.URLError as exc:  # pragma: no cover - network failure path
        raise GametimeError(f"Search request failed for {query!r}: {exc}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise GametimeError(f"Invalid search response for {query!r}: {exc}") from exc

    results: List[Event] = []
    for entry in data.get("events", []):
        ev = entry.get("event", entry)
        event_id = ev.get("id", "")
        event_url = f"https://gametime.co/events/{event_id}" if event_id else None
        performers = ev.get("performers", [])
        matched_id = _find_performer_id_in_entry(entry, query)
        is_home = bool(matched_id) and any(p.get("primary", False) for p in performers if p.get("id") == matched_id)
        results.append(
            Event(
                id=event_id,
                name=ev.get("name"),
                datetime_local=ev.get("datetime_local"),
                venue_id=ev.get("venue_id"),
                extra={
                    "url": event_url,
                    "min_price_total": ev.get("min_price", {}).get("total"),
                    "is_home": is_home,
                },
            )
        )
    return results


def _find_performer_id_in_entry(entry: dict, query: str) -> Optional[str]:
    """Find the performer id matching *query* in a search result entry."""
    for p in entry.get("performers", []):
        name = p.get("name", "") or ""
        if query.lower() in name.lower():
            return p.get("id")
    return None


def _resolve_performer_id(
    query: str,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 30.0,
) -> Optional[str]:
    """Resolve a performer id from a search query.

    Searches Gametime and returns the performer id whose name best matches
    *query*, or ``None`` if no match is found.
    """
    url = f"https://mobile.gametime.co/v1/search?q={urllib.request.quote(query)}"
    try:
        resp = _http_get(url, user_agent, timeout)
        body = _read_body(resp)
    except urllib.error.URLError:  # pragma: no cover
        return None

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None

    for entry in data.get("performers", []):
        p = entry.get("performer", entry)
        name = p.get("name", "")
        if query.lower() in name.lower():
            return p.get("id")
    return None


def get_performer_events(
    performer_id: str,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 30.0,
) -> List[Event]:
    """Fetch *all* upcoming events for a performer using the paginated API.

    This uses the ``/v1/events?performer_id=`` endpoint which returns events
    in pages and supports cursor-based pagination, ensuring all games are
    returned (not just the first ~10 from the search endpoint).

    Each returned :class:`Event` has ``extra["is_home"]`` set to ``True`` when
    the performer is the primary (home) performer for that event.
    """
    results: List[Event] = []
    cursor: Optional[str] = None
    max_pages = 20  # Safety limit

    for _ in range(max_pages):
        url = f"https://mobile.gametime.co/v1/events?performer_id={performer_id}&per_page=50"
        if cursor:
            url += f"&cursor={cursor}"
        try:
            resp = _http_get(url, user_agent, timeout)
            body = _read_body(resp)
        except urllib.error.URLError as exc:  # pragma: no cover
            raise GametimeError(f"Failed to fetch events for performer {performer_id!r}: {exc}") from exc

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GametimeError(f"Invalid response for performer {performer_id!r}: {exc}") from exc

        for entry in data.get("events", []):
            ev = entry.get("event", entry)
            event_id = ev.get("id", "")
            event_url = f"https://gametime.co/events/{event_id}" if event_id else None
            # Determine if this performer is the home (primary) team
            performers = ev.get("performers", [])
            is_home = any(p.get("id") == performer_id and p.get("primary", False) for p in performers)
            results.append(
                Event(
                    id=event_id,
                    name=ev.get("name"),
                    datetime_local=ev.get("datetime_local"),
                    venue_id=ev.get("venue_id"),
                    extra={
                        "url": event_url,
                        "min_price_total": ev.get("min_price", {}).get("total"),
                        "is_home": is_home,
                    },
                )
            )

        if not data.get("more"):
            break
        cursor = data.get("cursor")
        if not cursor:
            break

    return results


def _find_string(blob: str, key: str) -> Optional[str]:
    m = re.search(r'"%s":"((?:[^"\\]|\\.)*)"' % re.escape(key), blob)
    if not m:
        return None
    # Decode the small subset of escapes Gametime uses (\u002F for '/', etc.).
    return json.loads('"%s"' % m.group(1))


def _find_int(blob: str, key: str) -> Optional[int]:
    m = re.search(r'"%s":(\d+)' % re.escape(key), blob)
    return int(m.group(1)) if m else None


def _find_str_list(blob: str, key: str) -> List[str]:
    m = re.search(r'"%s":\[([^\]]*)\]' % re.escape(key), blob)
    if not m:
        return []
    return re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))


def parse_event(html: str) -> Optional[Event]:
    """Extract lightweight event metadata, if present in the page.

    The server-rendered event object names the matchup with
    ``"name":"...","nameOverride":...,"performers"`` and uses camelCase
    ``datetimeLocal``; we anchor on those to avoid picking up unrelated
    ``name`` fields (performers, sections, etc.).
    """
    name = None
    mname = re.search(r'"name":"((?:[^"\\]|\\.)*)","nameOverride":[^,]*,"performers"', html)
    if mname:
        name = json.loads('"%s"' % mname.group(1))

    dt = None
    mdt = re.search(r'"datetimeLocal":"([^"]+)"', html) or re.search(r'"datetime_local":"([^"]+)"', html)
    if mdt:
        dt = mdt.group(1)

    venue = None
    mven = re.search(r'"venue_id":"([a-f0-9]{24})"', html) or re.search(r'"venueId":"([a-f0-9]{24})"', html)
    if mven:
        venue = mven.group(1)

    eid = None
    meid = re.search(r'"id":"([a-f0-9]{24})","performers"', html)
    if meid:
        eid = meid.group(1)

    if not any([name, dt, venue, eid]):
        return None
    return Event(id=eid or "", name=name, datetime_local=dt, venue_id=venue)


def parse_listings(html: str) -> List[Listing]:
    """Parse all ticket listings embedded in an event page.

    Each listing object in the Next.js stream begins with ``{"availableLots":``
    and carries an ``id``, ``price`` block (all-in ``total`` in cents per
    ticket), ``seats`` and a ``spot`` describing ``section``/``row``. We split
    on the stable ``availableLots`` anchor and extract fields per chunk, which
    is resilient to key-ordering changes.
    """
    listings: List[Listing] = []
    seen = set()
    parts = html.split('{"availableLots":')
    for part in parts[1:]:
        chunk = part[:4000]

        lots_match = re.match(r"\[([0-9,\s]*)\]", chunk)
        if not lots_match:
            continue
        available_lots = [int(x) for x in re.findall(r"\d+", lots_match.group(1))]

        # All-in per-ticket price: the "total" inside the price block.
        price_match = re.search(r'"price":\{[^{}]*?"total":(\d+)\}', chunk)
        if not price_match:
            continue
        price_total = int(price_match.group(1))

        section = _find_string(chunk, "section")
        if section is None:
            continue

        listing_id = _find_string(chunk, "id")
        if not listing_id or listing_id in seen:
            # Skip duplicates (e.g. a listing echoed in map-pin data).
            if listing_id and listing_id in seen:
                continue
        if listing_id:
            seen.add(listing_id)

        listings.append(
            Listing(
                id=listing_id or "",
                section=section,
                section_group=_find_string(chunk, "sectionGroup"),
                row=_find_string(chunk, "row"),
                seats=_find_str_list(chunk, "seats"),
                available_lots=available_lots,
                price_total=price_total,
                face_value=_find_int(chunk, "faceValue"),
                event_id=_find_string(chunk, "eventId"),
                url=_find_string(chunk, "seoUrl"),
            )
        )
    return listings
