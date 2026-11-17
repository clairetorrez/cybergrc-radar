#!/usr/bin/env python3
"""Fail CI if a tracked, current campaign disappears from the published catalog."""
import datetime as dt
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
approved = json.loads((root / "data/approved.json").read_text())
sources = json.loads((root / "data/sources.json").read_text())
offers = approved.get("offers", [])
assert isinstance(offers, list)
source_urls = {x["url"] for x in sources["sources"]}
today = dt.datetime.now(dt.timezone.utc).date()
seen = set()
for offer in offers:
    url = offer.get("source")
    assert url and url.startswith("https://"), f"Missing official URL: {offer.get('id')}"
    assert url not in seen, f"Duplicate deal source: {url}"
    seen.add(url)
    assert offer.get("kind") != "Free exam" or "$0" in offer.get("price", ""), f"Free exam without explicit exam pricing: {url}"
    deadline = offer.get("deadline")
    if deadline and dt.date.fromisoformat(deadline) < today:
        continue
    if offer.get("id", "").startswith("curated-"):
        assert url in source_urls, f"Published promotion not monitored: {url}"
        assert offer.get("eligibility") and offer.get("price"), f"Missing deal terms: {url}"
print(f"Validated {len(offers)} approved offers and {len(source_urls)} monitored sources")
