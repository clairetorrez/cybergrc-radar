#!/usr/bin/env python3
"""Merge researched opportunities into the unverified discovery review queue.

Entries in data/research_intake.json are never automatically marked verified.
The source scanner remains responsible for finding official-page changes.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "data/discovery.json"
INBOX = ROOT / "data/research_intake.json"

def merge():
    feed = json.loads(FEED.read_text(encoding="utf-8"))
    inbox = json.loads(INBOX.read_text(encoding="utf-8"))
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    existing = {x.get("url"): x for x in feed.get("leads", [])}
    added = 0
    for item in inbox.get("opportunities", []):
        url = item.get("url", "")
        if urlparse(url).scheme != "https" or not item.get("title"):
            continue
        if item.get("expires") and item["expires"] < today:
            continue
        if url in existing:
            continue
        key = hashlib.sha256(url.encode()).hexdigest()[:18]
        lead = {
            "id": key, "title": item["title"], "source": item.get("provider", "Research intake"),
            "url": url, "category": item.get("category", "Certification and training"),
            "topics": item.get("topics", []), "group": item.get("group", "Research intake"),
            "status": "pending_verification", "score": 75,
            "why": ["Research intake", "Official provider link", "Awaiting terms verification"],
            "evidence": item.get("notes", "Terms require provider confirmation"),
            "priceHint": item.get("priceHint", "Not confirmed"),
            "deadlineHint": item.get("expires"), "publishedAt": None,
            "firstSeen": item.get("firstSeen", today), "lastSeen": today,
            "lastChecked": None, "fingerprint": key,
            "verified": False, "reviewRequired": True
        }
        feed["leads"].append(lead)
        existing[url] = lead
        added += 1
    feed["leads"].sort(key=lambda x: (x.get("firstSeen") or "", x.get("score", 0)), reverse=True)
    feed["leads"] = feed["leads"][:200]
    feed["newLeads"] = feed.get("newLeads", 0) + added
    FEED.write_text(json.dumps(feed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Research intake: {added} new leads queued")

if __name__ == "__main__":
    merge()
