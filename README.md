# Gametime ticket-price watcher

> **Note:** This project was primarily generated and maintained with the assistance of AI (GitHub Copilot).

A small, **dependency-free** (standard-library only) Python tool that lists
current [gametime.co](https://gametime.co) ticket prices for an event and alerts
you when a desired number of seats in chosen sections drops below a target
**per-ticket** price.

It answers questions like:

> *Tell me when **2 seats in the 200s** are available for **under \$100 each**
> for [this game](https://gtix.co/ymvO3hz2xGfg).*

```bash
python -m gametime_watcher https://gtix.co/ymvO3hz2xGfg --sections 200-299 --quantity 2 --max-price 100
```

```
Pittsburgh Pirates at Athletics @ 2026-06-17T18:40:00
Criteria: 2 seat(s) in [200-299] <= $100.00/ticket
Found 0 of 97 listings:
```

(At the time of writing the cheapest 2-seat pair in the 200s is \$101/ticket, so
nothing matches yet — run it with `--watch` to be alerted when one drops below
your threshold.)

## How it works

Gametime server-renders the full set of listings for an event into the event
page HTML. This tool:

1. Resolves an **event id** from whatever you give it — a short link
   (`https://gtix.co/...`), a full event/listing URL, or a bare 24-character id.
2. Downloads `https://gametime.co/events/<id>` (no API key required).
3. Parses every listing's section, row, seats, purchasable lot sizes, and
   **all-in per-ticket price** (the price shown on the site, fees included).
4. Filters by your section / price / quantity criteria and prints the cheapest
   matches first.

> ⚠️ This reads Gametime's public web page. It's intended for personal use;
> be respectful with polling intervals (the default is 5 minutes) and check
> Gametime's Terms of Service. Page structure may change over time.

## Usage

### Scan all games for a team (search + filter in one command)

```
python -m gametime_watcher scan-all <query> [filter options] [--home-only] [--json]

  <query>               Team or performer name (e.g. "Athletics")
  -s, --sections SPEC   Section filter (may be repeated)
  -p, --max-price N     Max all-in price PER TICKET, in dollars
  -q, --quantity N      Seats wanted together (default 1)
  --allow-larger        Also keep larger lots
  --home-only           Only scan home games
  --json                Output JSON instead of text
```

**Example: find all Athletics home games with Solon Club tickets, 2 seats, under
\$100 each:**

```bash
python -m gametime_watcher scan-all Athletics --home-only -s "Solon Club" -q 2 -p 100
```

```
Los Angeles Angels at Athletics @ 2026-06-21T13:05:00 — 2 match(es):
  $  95.00/tkt  sec   201 (Solon Club)  row   2  seats[1,2,3,4]  lots:2/4, face $144.50
  $  98.00/tkt  sec   203 (Solon Club)  row   6  seats[5,6]  lots:2, face $170.00

Athletics at Detroit Tigers @ 2026-07-07T18:40:00 — no matches
...
```

### Search for events (find game links)

```
python -m gametime_watcher search <query> [--home-only] [--json]

  <query>               Team or performer name (e.g. "Athletics")
  --home-only           Show only home games
  --json                Output JSON instead of text
```

Example: find all upcoming Athletics home games:

```bash
python -m gametime_watcher search Athletics --home-only
```

```
Found 55 upcoming home event(s) for 'Athletics':

  2026-06-14T12:05:00  Colorado Rockies at Athletics  from $9
    https://gametime.co/events/68af57d5bf6276ee588dd924
  2026-06-15T18:40:00  Pittsburgh Pirates at Athletics  from $20
    https://gametime.co/events/68af5b70f2def3b1e914a475
  ...
```

### Watch a single event

```
python -m gametime_watcher <event> [options]

  <event>               Gametime event/listing URL, short link, or 24-char id

  -s, --sections SPEC   Section filter. Comma-separated tokens, each one of:
                          200-299        an inclusive numeric range
                          A-D            an inclusive alphabetic range
                          119            an exact section
                          "Solon Club"   a section-group / section name
                        May be given multiple times to combine filters (OR).
                        Default: all sections.
  -p, --max-price N     Maximum all-in price PER TICKET, in dollars.
  -q, --quantity N      Seats wanted together (default 1). Only listings that
                        offer this exact lot size are kept.
  --allow-larger        Also keep listings that only offer a larger lot.

  --json                Emit JSON instead of text.
  --watch               Poll repeatedly, alerting only on newly-seen matches.
  --interval SECONDS    Polling interval for --watch (default 300).
  --webhook URL         POST a JSON payload to URL on new matches.
  --command CMD         Run CMD on new matches (JSON payload sent on stdin).

  --user-agent UA       Override the HTTP User-Agent.
  --timeout SECONDS     HTTP timeout (default 30).
```

The one-shot mode exits `0` when matches are found and `1` when none are, which
makes it easy to drive from `cron` or shell scripts.

### Examples

Flexible by design — change sections and price freely:

```bash
# 4 seats in the lower bowl (sections 100-130) under $75 each
python -m gametime_watcher 68af5b72c95bdeed8553f07f -s 100-130 -q 4 -p 75

# Any 2 seats in a named club section
python -m gametime_watcher <url> -s "Solon Club" -q 2

# Letter sections A through D
python -m gametime_watcher <url> -s A-D -q 2 -p 50

# Mix ranges, exact sections, and names (comma-separated or repeated -s)
python -m gametime_watcher <url> -s "200-299,119,Field Level" -q 2 -p 120
python -m gametime_watcher <url> -s 200-299 -s 119 -s "Field Level" -q 2 -p 120
```

Watch and get notified (every 2 minutes) via a webhook:

```bash
python -m gametime_watcher https://gtix.co/ymvO3hz2xGfg \
  -s 200-299 -q 2 -p 100 \
  --watch --interval 120 --webhook https://hooks.example.com/my-endpoint
```

Or run a local notifier on each new match (payload arrives on stdin):

```bash
python -m gametime_watcher <url> -s 200-299 -q 2 -p 100 \
  --watch --command "python my_notifier.py"
```

## Library API

```python
from gametime_watcher import (
    search_events, extract_event_id, fetch_event_html,
    parse_event, parse_listings, filter_listings,
)

# Find all upcoming Athletics games
events = search_events("Athletics")
for ev in events:
    print(ev.name, ev.datetime_local, ev.extra["url"])

# Then check a specific event for deals
event_id = extract_event_id("https://gtix.co/ymvO3hz2xGfg")
html = fetch_event_html(event_id)
event = parse_event(html)
listings = parse_listings(html)

deals = filter_listings(listings, sections="Solon Club", quantity=2, max_price_dollars=100)
for l in deals:
    print(l.section, l.row, f"${l.price_total_dollars:.2f}/ticket", l.available_lots)
```

`Listing.price_total` is the all-in price **per ticket** in cents;
`Listing.available_lots` lists the group sizes you may buy (e.g. `[2, 4]`).

## Development

```bash
pip install pytest
python -m pytest
```

Tests are fully offline: parsing and CLI tests run against
`tests/fixtures/event_page.html`, and the network is stubbed in the CLI tests.
