#!/usr/bin/env python3
"""Refresh the 2026 Black Friday collection from v3nomtech's CC0 feed."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "black-friday-2026.json"
SOURCE = "https://github.com/v3nomtech/infosec-cert-black-friday-2026"
FEED = "https://raw.githubusercontent.com/v3nomtech/infosec-cert-black-friday-2026/main/data/deals.json"
GROUPS = {"certification": "Certifications & exams", "training": "Training & courses", "labs": "Labs & platforms"}
MAX_BYTES = 300_000


def date_value(value):
    if not value:
        return None
    parsed = dt.date.fromisoformat(value).isoformat()
    if parsed != value:
        raise ValueError(f"Expected an ISO date, got {value!r}")
    return parsed


def safe_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError(f"Invalid HTTPS provider URL: {value!r}")
    return value


def url_key(value):
    parsed = urlsplit(value)
    return urlunsplit(("", parsed.netloc.lower().removeprefix("www."), parsed.path.rstrip("/"), "", ""))


def build(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Missing upstream deal entries")
    offers, watchlist, keys = [], [], set()
    for row in rows:
        vendor = row["vendor"].strip()
        source = safe_url(row["url"])
        evidence = safe_url(row.get("source_url") or source)
        if not vendor:
            raise ValueError("Missing vendor")
        key = url_key(source)
        if key in keys:
            raise ValueError(f"Duplicate provider URL: {source}")
        keys.add(key)
        status = row["status"]
        if status.startswith("👀"):
            watchlist.append({"provider": vendor, "source": source, "certs": row.get("certs", [])})
            continue
        if not status.startswith(("✅", "⏳", "🔥", "❌")):
            raise ValueError(f"Unrecognized upstream status: {status}")
        title, discount = row["offer"].strip(), row["discount"].strip()
        starts, ends = date_value(row.get("starts")), date_value(row.get("ends"))
        checked = date_value(row.get("last_checked"))
        if not title or not discount or not checked or (starts and ends and starts > ends):
            raise ValueError(f"Incomplete or inconsistent offer: {vendor}")
        if row["source"] not in ("vendor", "third-party"):
            raise ValueError(f"Unrecognized evidence type: {row['source']}")
        entry = {
            "id": "black-friday-2026-" + hashlib.sha256(key.encode()).hexdigest()[:14],
            "provider": vendor,
            "title": title,
            "category": GROUPS[row["category"]],
            "price": discount,
            "code": row.get("code", ""),
            "details": row.get("notes", ""),
            "frameworks": row.get("certs", []),
            "source": source,
            "evidence": evidence,
            "verifiedOn": checked,
            "verification": "vendor" if row["source"] == "vendor" else "reported",
            "startDate": starts,
            "deadline": ends,
        }
        # OnlySecurity publishes a UK-time campaign. Keep its boundaries independent of the viewer's time zone.
        if urlsplit(source).hostname == "onlysecurity.com":
            if starts:
                entry["startAt"] = starts + "T00:00:00Z"
            if ends:
                entry["endAt"] = (dt.date.fromisoformat(ends) + dt.timedelta(days=1)).isoformat() + "T00:00:00Z"
        if status.startswith("❌"):
            entry["closedBySource"] = True
        offers.append(entry)
    return {
        "source": SOURCE,
        "offers": sorted(offers, key=lambda x: (x["provider"].casefold(), x["title"])),
        "watchlist": sorted(watchlist, key=lambda x: x["provider"].casefold()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="Use a local copy of the upstream JSON")
    args = parser.parse_args()
    if not args.input and dt.datetime.now(dt.timezone.utc).date() >= dt.date(2027, 1, 6):
        print("2026 seasonal feed is closed. Keeping its archive.")
        return
    try:
        if args.input:
            raw = args.input.read_bytes()
        else:
            with urlopen(FEED, timeout=12) as response:
                raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Upstream file exceeds the size limit")
        data = build(json.loads(raw))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        if args.input or not OUTPUT.exists():
            raise
        print(f"::warning::Black Friday feed unavailable or invalid. Keeping the last successful snapshot. {exc}")
        return
    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Imported {len(data['offers'])} announced offers and {len(data['watchlist'])} watchlist providers.")


if __name__ == "__main__":
    main()
