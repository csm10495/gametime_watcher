"""Tests for parsing event pages into Event/Listing objects."""

import os

import pytest

from gametime_watcher.api import GametimeError, extract_event_id, parse_event, parse_listings

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "event_page.html")
EVENT_ID = "68af5b72c95bdeed8553f07f"


@pytest.fixture(scope="module")
def html():
    with open(FIXTURE, encoding="utf-8") as fh:
        return fh.read()


# --- extract_event_id (offline, no network) ---------------------------------


def test_extract_bare_id():
    assert extract_event_id(EVENT_ID) == EVENT_ID


def test_extract_from_event_url():
    url = f"https://gametime.co/events/{EVENT_ID}"
    assert extract_event_id(url) == EVENT_ID


def test_extract_from_listing_url():
    url = (
        "https://gametime.co/mlb-baseball/pirates-at-as-tickets/"
        f"6-17-2026-west-sacramento-ca-sutter-health-park/events/{EVENT_ID}/listings/abc"
    )
    assert extract_event_id(url) == EVENT_ID


def test_extract_rejects_unresolvable_non_url():
    with pytest.raises(GametimeError):
        extract_event_id("not-an-id")


# --- parse_event ------------------------------------------------------------


def test_parse_event_name_and_datetime(html):
    event = parse_event(html)
    assert event is not None
    assert event.name == "Test Team A at Test Team B"
    assert event.datetime_local == "2026-06-17T18:40:00"
    assert event.venue_id == "55313d1878fea568e6000001"


def test_parse_event_returns_none_when_absent():
    assert parse_event("<html><body>nothing here</body></html>") is None


# --- parse_listings ---------------------------------------------------------


def test_parse_listings_count_and_dedup(html):
    listings = parse_listings(html)
    # Fixture has 6 listing objects but one is a duplicate id -> 5 unique.
    assert len(listings) == 5
    assert len({listing.id for listing in listings}) == 5


def test_parse_listing_fields(html):
    by_id = {listing.id: listing for listing in parse_listings(html)}
    cheap = by_id["aaaaaaaaaaaaaaaaaaaaaaa1"]
    assert cheap.section == "117"
    assert cheap.section_group == "Field Level"
    assert cheap.row == "12"
    assert cheap.seats == ["9", "10"]
    assert cheap.available_lots == [2]
    assert cheap.price_total == 3800
    assert cheap.price_total_dollars == 38.0
    assert cheap.face_value == 12500
    assert cheap.event_id == EVENT_ID


def test_parse_listing_unescapes_seo_url(html):
    by_id = {listing.id: listing for listing in parse_listings(html)}
    url = by_id["aaaaaaaaaaaaaaaaaaaaaaa1"].url
    assert url.startswith("https://gametime.co/events/")
    assert "\\u002F" not in url and "/listings/" in url


def test_parse_listing_handles_non_numeric_section(html):
    by_id = {listing.id: listing for listing in parse_listings(html)}
    lawn = by_id["aaaaaaaaaaaaaaaaaaaaaaa5"]
    assert lawn.section == "Lawn"
    assert lawn.section_is_numeric is False
    assert lawn.section_number is None


def test_parse_empty_html_returns_no_listings():
    assert parse_listings("<html></html>") == []


# --- search_events (unit test with stubbed HTTP) ----------------------------


def test_search_events_parses_api_response(monkeypatch):
    import json as _json

    from gametime_watcher import api

    fake_response = {
        "events": [
            {
                "event": {
                    "id": "abcdef1234567890abcdef12",
                    "name": "Team A at Team B",
                    "datetime_local": "2026-07-01T19:00:00",
                    "venue_id": "112233445566778899aabbcc",
                    "min_price": {"total": 1500, "prefee": 1200},
                }
            }
        ],
        "performers": [],
        "venues": [],
    }

    class FakeResp:
        def __init__(self):
            self.headers = {}

        def read(self):
            return _json.dumps(fake_response).encode()

        def geturl(self):
            return "https://mobile.gametime.co/v1/search?q=Team"

    monkeypatch.setattr(api, "_http_get", lambda *a, **k: FakeResp())

    results = api.search_events("Team")
    assert len(results) == 1
    assert results[0].id == "abcdef1234567890abcdef12"
    assert results[0].name == "Team A at Team B"
    assert results[0].datetime_local == "2026-07-01T19:00:00"
    assert results[0].extra["url"] == "https://gametime.co/events/abcdef1234567890abcdef12"
    assert results[0].extra["min_price_total"] == 1500


# --- _resolve_performer_id (unit test with stubbed HTTP) --------------------


def test_resolve_performer_id(monkeypatch):
    import json as _json

    from gametime_watcher import api

    fake_response = {
        "events": [],
        "performers": [
            {"performer": {"id": "perf123", "name": "Athletics"}},
            {"performer": {"id": "perf456", "name": "World Athletics Championships"}},
        ],
        "venues": [],
    }

    class FakeResp:
        def __init__(self):
            self.headers = {}

        def read(self):
            return _json.dumps(fake_response).encode()

        def geturl(self):
            return "https://mobile.gametime.co/v1/search?q=Athletics"

    monkeypatch.setattr(api, "_http_get", lambda *a, **k: FakeResp())

    result = api._resolve_performer_id("Athletics")
    assert result == "perf123"


def test_resolve_performer_id_no_match(monkeypatch):
    import json as _json

    from gametime_watcher import api

    fake_response = {"events": [], "performers": [], "venues": []}

    class FakeResp:
        def __init__(self):
            self.headers = {}

        def read(self):
            return _json.dumps(fake_response).encode()

        def geturl(self):
            return "https://mobile.gametime.co/v1/search?q=Nope"

    monkeypatch.setattr(api, "_http_get", lambda *a, **k: FakeResp())

    result = api._resolve_performer_id("Nope")
    assert result is None


# --- get_performer_events (unit test with stubbed HTTP) ---------------------


def test_get_performer_events_single_page(monkeypatch):
    import json as _json

    from gametime_watcher import api

    fake_response = {
        "events": [
            {
                "event": {
                    "id": "evt111",
                    "name": "Visitors at Home",
                    "datetime_local": "2026-07-01T19:00:00",
                    "venue_id": "ven111",
                    "min_price": {"total": 2000},
                    "performers": [
                        {"id": "perf_home", "primary": True},
                        {"id": "perf_away", "primary": False},
                    ],
                }
            },
            {
                "event": {
                    "id": "evt222",
                    "name": "Home at Away",
                    "datetime_local": "2026-07-05T19:00:00",
                    "venue_id": "ven222",
                    "min_price": {"total": 3000},
                    "performers": [
                        {"id": "perf_away2", "primary": True},
                        {"id": "perf_home", "primary": False},
                    ],
                }
            },
        ],
        "more": False,
        "page": 1,
        "per_page": 50,
        "cursor": None,
    }

    class FakeResp:
        def __init__(self):
            self.headers = {}

        def read(self):
            return _json.dumps(fake_response).encode()

        def geturl(self):
            return "https://mobile.gametime.co/v1/events?performer_id=perf_home"

    monkeypatch.setattr(api, "_http_get", lambda *a, **k: FakeResp())

    results = api.get_performer_events("perf_home")
    assert len(results) == 2
    # First event: perf_home is primary -> is_home = True
    assert results[0].extra["is_home"] is True
    assert results[0].name == "Visitors at Home"
    # Second event: perf_home is not primary -> is_home = False
    assert results[1].extra["is_home"] is False
    assert results[1].name == "Home at Away"


def test_get_performer_events_pagination(monkeypatch):
    import json as _json

    from gametime_watcher import api

    page1 = {
        "events": [
            {
                "event": {
                    "id": "evt1",
                    "name": "Game 1",
                    "datetime_local": "2026-07-01T19:00:00",
                    "venue_id": "v1",
                    "min_price": {"total": 1000},
                    "performers": [{"id": "p1", "primary": True}],
                }
            }
        ],
        "more": True,
        "cursor": "cursor_abc",
        "page": 1,
        "per_page": 1,
    }
    page2 = {
        "events": [
            {
                "event": {
                    "id": "evt2",
                    "name": "Game 2",
                    "datetime_local": "2026-07-02T19:00:00",
                    "venue_id": "v2",
                    "min_price": {"total": 2000},
                    "performers": [{"id": "p1", "primary": True}],
                }
            }
        ],
        "more": False,
        "cursor": None,
        "page": 2,
        "per_page": 1,
    }

    call_count = [0]

    class FakeResp:
        def __init__(self, data):
            self._data = data
            self.headers = {}

        def read(self):
            return _json.dumps(self._data).encode()

        def geturl(self):
            return ""

    def fake_get(url, *a, **k):
        call_count[0] += 1
        if "cursor=cursor_abc" in url:
            return FakeResp(page2)
        return FakeResp(page1)

    monkeypatch.setattr(api, "_http_get", fake_get)

    results = api.get_performer_events("p1")
    assert len(results) == 2
    assert results[0].id == "evt1"
    assert results[1].id == "evt2"
    assert call_count[0] == 2  # Two pages fetched


# --- fetch_event_html retry behavior ----------------------------------------


def test_fetch_event_html_retries_on_502(monkeypatch):
    """fetch_event_html retries on transient HTTP 502 and succeeds."""
    import urllib.error

    from gametime_watcher import api

    call_count = [0]

    class FakeResp:
        def __init__(self):
            self.headers = {}

        def read(self):
            return b"<html>OK</html>"

        def geturl(self):
            return ""

    def fake_get(url, *a, **k):
        call_count[0] += 1
        if call_count[0] <= 2:
            raise urllib.error.HTTPError(url, 502, "Bad Gateway", {}, None)
        return FakeResp()

    monkeypatch.setattr(api, "_http_get", fake_get)
    monkeypatch.setattr(api.time, "sleep", lambda _: None)  # skip actual sleep

    result = api.fetch_event_html("abc123def456abc123def456", retries=3, backoff_base=1.0)
    assert result == "<html>OK</html>"
    assert call_count[0] == 3  # 2 failures + 1 success


def test_fetch_event_html_raises_after_all_retries_exhausted(monkeypatch):
    """fetch_event_html raises GametimeError after all retries fail."""
    import urllib.error

    from gametime_watcher import api

    call_count = [0]

    def fake_get(url, *a, **k):
        call_count[0] += 1
        raise urllib.error.HTTPError(url, 502, "Bad Gateway", {}, None)

    monkeypatch.setattr(api, "_http_get", fake_get)
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    with pytest.raises(GametimeError, match="502"):
        api.fetch_event_html("abc123def456abc123def456", retries=3, backoff_base=1.0)
    assert call_count[0] == 4  # 1 initial + 3 retries


def test_fetch_event_html_no_retry_on_404(monkeypatch):
    """fetch_event_html does NOT retry on non-retryable errors like 404."""
    import urllib.error

    from gametime_watcher import api

    call_count = [0]

    def fake_get(url, *a, **k):
        call_count[0] += 1
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(api, "_http_get", fake_get)
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    with pytest.raises(GametimeError, match="404"):
        api.fetch_event_html("abc123def456abc123def456", retries=3, backoff_base=1.0)
    assert call_count[0] == 1  # No retries


def test_fetch_event_html_exponential_backoff_delays(monkeypatch):
    """Verify exponential backoff delays are correct."""
    import urllib.error

    from gametime_watcher import api

    delays = []

    def fake_get(url, *a, **k):
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)

    monkeypatch.setattr(api, "_http_get", fake_get)
    monkeypatch.setattr(api.time, "sleep", lambda d: delays.append(d))

    with pytest.raises(GametimeError):
        api.fetch_event_html("abc123def456abc123def456", retries=3, backoff_base=2.0)
    # Delays: 2*2^0=2, 2*2^1=4, 2*2^2=8
    assert delays == [2.0, 4.0, 8.0]
