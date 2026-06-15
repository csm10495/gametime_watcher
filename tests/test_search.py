"""Tests for the search subcommand and search_events API."""

import json
import os

import pytest

from gametime_watcher import cli
from gametime_watcher.models import Event

FAKE_SEARCH_RESULTS = [
    Event(
        id="aaa111aaa111aaa111aaa111",
        name="Pirates at Athletics",
        datetime_local="2026-06-17T18:40:00",
        venue_id="55313d1878fea568e6000001",
        extra={"url": "https://gametime.co/events/aaa111aaa111aaa111aaa111", "min_price_total": 2000, "is_home": True},
    ),
    Event(
        id="bbb222bbb222bbb222bbb222",
        name="Athletics at Giants",
        datetime_local="2026-06-20T19:05:00",
        venue_id="663344556677889900aabb01",
        extra={"url": "https://gametime.co/events/bbb222bbb222bbb222bbb222", "min_price_total": 3500, "is_home": False},
    ),
]


@pytest.fixture(autouse=True)
def stub_search(monkeypatch):
    monkeypatch.setattr(cli, "search_events", lambda *a, **k: FAKE_SEARCH_RESULTS)
    monkeypatch.setattr(cli, "_resolve_performer_id", lambda *a, **k: "fake_performer_id")
    monkeypatch.setattr(cli, "get_performer_events", lambda *a, **k: FAKE_SEARCH_RESULTS)


def test_search_text_output(capsys):
    rc = cli.main(["search", "Athletics"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Found 2 upcoming event(s)" in out
    assert "Pirates at Athletics" in out
    assert "Athletics at Giants" in out
    assert "https://gametime.co/events/aaa111aaa111aaa111aaa111" in out
    assert "from $20" in out


def test_search_json_output(capsys):
    rc = cli.main(["search", "Athletics", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data["query"] == "Athletics"
    assert data["event_count"] == 2
    assert data["events"][0]["id"] == "aaa111aaa111aaa111aaa111"
    assert data["events"][0]["url"] == "https://gametime.co/events/aaa111aaa111aaa111aaa111"
    assert data["events"][0]["min_price_total_cents"] == 2000


def test_search_exit_1_when_no_results(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_resolve_performer_id", lambda *a, **k: "fake_id")
    monkeypatch.setattr(cli, "get_performer_events", lambda *a, **k: [])
    rc = cli.main(["search", "Nonexistent Team"])
    assert rc == 1
    assert "Found 0 upcoming event(s)" in capsys.readouterr().out


def test_search_sorted_by_datetime(capsys):
    """Results are sorted chronologically."""
    cli.main(["search", "Athletics"])
    out = capsys.readouterr().out
    # Pirates game is on 6/17, Giants game on 6/20
    assert out.index("Pirates") < out.index("Giants")


# --- scan-all subcommand tests ----------------------------------------------

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "event_page.html")


@pytest.fixture
def stub_scan_all(monkeypatch):
    """Stub search_events and fetch_event_html for scan-all tests."""
    with open(FIXTURE, encoding="utf-8") as fh:
        html = fh.read()
    monkeypatch.setattr(cli, "_resolve_performer_id", lambda *a, **k: "fake_performer_id")
    monkeypatch.setattr(cli, "get_performer_events", lambda *a, **k: FAKE_SEARCH_RESULTS)
    monkeypatch.setattr(cli, "fetch_event_html", lambda *a, **k: html)
    monkeypatch.setattr(cli, "parse_listings", cli.parse_listings)  # keep real


def test_scan_all_text_finds_matches(stub_scan_all, capsys):
    rc = cli.main(["scan-all", "Athletics", "-s", "Solon Club", "-q", "2", "-p", "200"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Pirates at Athletics" in out
    assert "match" in out
    assert "Solon Club" in out


def test_scan_all_text_no_matches(stub_scan_all, capsys):
    rc = cli.main(["scan-all", "Athletics", "-s", "Solon Club", "-q", "2", "-p", "5"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "no matches" in out


def test_scan_all_json_output(stub_scan_all, capsys):
    cli.main(["scan-all", "Athletics", "-s", "Solon Club", "-q", "2", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["query"] == "Athletics"
    assert data["events_scanned"] == 2
    assert len(data["results"]) == 2
    # Both events use same fixture, both should have Solon Club matches
    for r in data["results"]:
        assert r["event"]["id"] in ("aaa111aaa111aaa111aaa111", "bbb222bbb222bbb222bbb222")
        assert r["match_count"] > 0


def test_scan_all_no_events_found(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_resolve_performer_id", lambda *a, **k: "fake_id")
    monkeypatch.setattr(cli, "get_performer_events", lambda *a, **k: [])
    rc = cli.main(["scan-all", "Nonexistent", "-s", "200-299", "-q", "2"])
    assert rc == 1


# --- --home-only tests -------------------------------------------------------


def test_search_home_only_filters_away_games(capsys):
    """--home-only should exclude away games."""
    rc = cli.main(["search", "Athletics", "--home-only"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Pirates at Athletics" in out
    assert "Athletics at Giants" not in out
    assert "Found 1 upcoming home event(s)" in out


def test_search_home_only_json(capsys):
    rc = cli.main(["search", "Athletics", "--home-only", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data["event_count"] == 1
    assert data["events"][0]["is_home"] is True
    assert data["events"][0]["name"] == "Pirates at Athletics"


def test_scan_all_home_only(stub_scan_all, capsys):
    """scan-all --home-only should only scan home games."""
    cli.main(["scan-all", "Athletics", "--home-only", "-s", "Solon Club", "-q", "2", "-p", "200"])
    out = capsys.readouterr().out
    assert "Pirates at Athletics" in out
    # The away game should not appear
    assert "Athletics at Giants" not in out


def test_scan_all_home_only_no_home_games(monkeypatch, capsys):
    """scan-all --home-only should return 1 if no home games exist."""
    away_only = [
        Event(
            id="ccc333ccc333ccc333ccc333",
            name="Athletics at Giants",
            datetime_local="2026-06-20T19:05:00",
            venue_id="663344556677889900aabb01",
            extra={
                "url": "https://gametime.co/events/ccc333ccc333ccc333ccc333",
                "min_price_total": 3500,
                "is_home": False,
            },
        ),
    ]
    monkeypatch.setattr(cli, "_resolve_performer_id", lambda *a, **k: "fake_id")
    monkeypatch.setattr(cli, "get_performer_events", lambda *a, **k: away_only)
    rc = cli.main(["scan-all", "Athletics", "--home-only", "-s", "200-299"])
    assert rc == 1


def test_search_fallback_when_no_performer(monkeypatch, capsys):
    """When performer id can't be resolved, fall back to search_events."""
    monkeypatch.setattr(cli, "_resolve_performer_id", lambda *a, **k: None)
    monkeypatch.setattr(cli, "search_events", lambda *a, **k: FAKE_SEARCH_RESULTS)
    rc = cli.main(["search", "Athletics"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Found 2 upcoming event(s)" in out
