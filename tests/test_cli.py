"""Tests for the CLI, with network calls stubbed out."""

import json
import os

import pytest

from gametime_watcher import cli

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "event_page.html")
EVENT_ID = "68af5b72c95bdeed8553f07f"


@pytest.fixture(autouse=True)
def stub_network(monkeypatch):
    with open(FIXTURE, encoding="utf-8") as fh:
        html = fh.read()
    monkeypatch.setattr(cli, "extract_event_id", lambda *a, **k: EVENT_ID)
    monkeypatch.setattr(cli, "fetch_event_html", lambda *a, **k: html)
    return html


def test_cli_text_output_match_found(capsys):
    rc = cli.main([EVENT_ID, "--sections", "200-299", "--quantity", "2", "--max-price", "100"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Test Team A at Test Team B" in out
    assert "Found 1 of 5 listings" in out
    assert "sec   203" in out


def test_cli_exit_code_1_when_no_match(capsys):
    rc = cli.main([EVENT_ID, "--sections", "200-299", "--quantity", "2", "--max-price", "50"])
    assert rc == 1
    assert "Found 0 of 5 listings" in capsys.readouterr().out


def test_cli_json_output(capsys):
    rc = cli.main([EVENT_ID, "-s", "200-299", "-q", "2", "-p", "100", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data["match_count"] == 1
    assert data["matches"][0]["section"] == "203"
    assert data["matches"][0]["price_total_dollars"] == 95.0
    assert data["event"]["name"] == "Test Team A at Test Team B"


def test_cli_quantity_must_be_positive():
    with pytest.raises(SystemExit):
        cli.main([EVENT_ID, "-q", "0"])


def test_cli_default_quantity_one_lists_all_sections(capsys):
    rc = cli.main([EVENT_ID, "--json"])
    data = json.loads(capsys.readouterr().out)
    # quantity defaults to 1; only listing 'd' (lots [1,2]) offers a single seat.
    assert rc == 0
    assert {m["id"] for m in data["matches"]} == {"aaaaaaaaaaaaaaaaaaaaaaa4"}


def test_cli_repeated_sections_flag(capsys):
    """--sections given multiple times combines them (OR logic)."""
    rc = cli.main([EVENT_ID, "-s", "200-299", "-s", "117", "-q", "2", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    # 117 (a), 201 (b), 203 (c) all have lot=2
    assert {m["section"] for m in data["matches"]} == {"117", "201", "203"}


def test_cli_repeated_sections_with_group_name(capsys):
    """Mixing range and name across multiple --sections flags."""
    rc = cli.main([EVENT_ID, "-s", "119", "-s", "General Admission", "-q", "2", "--json"])
    data = json.loads(capsys.readouterr().out)
    # 119 (d) has lot [1,2], "General Admission" is Lawn (e) lot [4] -> excluded by qty=2
    assert rc == 0
    assert {m["section"] for m in data["matches"]} == {"119"}
