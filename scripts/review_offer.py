#!/usr/bin/env python3
"""Create a proposed, manually reviewed opportunity for an approval pull request.

An operator must inspect the original provider page before running this script.
The script enforces structure and guards against invalid/expired offers. It does
not independently prove that a claimed promotion is genuine.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DISCOVERED = ROOT / "data" / "discovery.json"
APPROVED = ROOT / "data" / "approved.json"
ALLOWED_KINDS = {
    "Free exam", "Free certification", "Free credential", "Free training",
    "Free simulation", "Discount", "Event discount", "Volunteer", "Scholarship",
}
ALLOWED_HOSTS = {
    "isc2.org", "pecb.com", "isaca.org", "linuxfoundation.org",
    "sans.org", "cloudsecurityalliance.org", "owasp.org", "nist.gov",
}
REQUIRED = ("REVIEW_LEAD_ID", "REVIEW_KIND", "REVIEW_PRICE", "REVIEW_DESCRIPTION", "REVIEW_ELIGIBILITY")

def value(name: str) -> str:
    return os.getenv(name, "").strip()

def official_link(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == domain or host.endswith("." + domain) for domain in ALLOWED_HOSTS)

def main() -> None:
    missing = [key for key in REQUIRED if not value(key)]
    if missing:
        raise SystemExit("Missing review fields: " + ", ".join(missing))
    kind = value("REVIEW_KIND")
    if kind not in ALLOWED_KINDS:
        raise SystemExit("Unsupported opportunity type")
    price = value("REVIEW_PRICE")
    if kind.startswith("Free") and not (price.lower().startswith("free") or "$0" in price):
        raise SystemExit("A free listing must explicitly state Free or $0")
    description = value("REVIEW_DESCRIPTION")
    eligibility = value("REVIEW_ELIGIBILITY")
    if len(description) < 25 or len(eligibility) < 15:
        raise SystemExit("Provide a meaningful description and eligibility information")
    deadline = value("REVIEW_DEADLINE")
    if deadline:
        try:
            deadline_date = dt.date.fromisoformat(deadline)
        except ValueError as exc:
            raise SystemExit("Deadline must be YYYY-MM-DD") from exc
        if deadline_date < dt.datetime.now(dt.timezone.utc).date():
            raise SystemExit("The listed opportunity has expired")
    if not DISCOVERED.exists():
        raise SystemExit("No discovery feed is available")
    candidates = json.loads(DISCOVERED.read_text(encoding="utf-8")).get("leads", [])
    matches = [item for item in candidates if item.get("id") == value("REVIEW_LEAD_ID")]
    if not matches:
        raise SystemExit("Lead ID not found in data/discovery.json. Scan the source again.")
    lead = matches[0]
    url = lead.get("url", "")
    if not official_link(url):
        raise SystemExit("Lead must point to an approved official provider website")
    frameworks = [part.strip() for part in value("REVIEW_FRAMEWORKS").split(",") if part.strip()][:12]
    now = dt.datetime.now(dt.timezone.utc).date().isoformat()
    identifier = "approved-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:14]
    label = dt.date.fromisoformat(deadline).strftime("Ends %b %d, %Y") if deadline else "No published deadline"
    offer = {
        "id": identifier,
        "title": lead["title"],
        "provider": lead["source"],
        "category": value("REVIEW_AREA") or "GRC",
        "kind": kind,
        "price": price,
        "discount": value("REVIEW_CODE"),
        "description": description,
        "eligibility": eligibility,
        "deadline": deadline or None,
        "dateLabel": label,
        "frameworks": frameworks,
        "tags": ["Provider reviewed", "Approved on merge"],
        "source": url,
        "verifiedOn": now,
        "verifiedBy": os.getenv("GITHUB_ACTOR", "maintainer"),
        "reviewStatus": "verified_after_merge",
        "featured": False,
        "score": 85,
    }
    data = {"version": 1, "offers": []}
    if APPROVED.exists():
        data = json.loads(APPROVED.read_text(encoding="utf-8"))
    existing = data.get("offers", [])
    if not isinstance(existing, list):
        raise SystemExit("Invalid approved offers data")
    data["offers"] = [d for d in existing if d.get("id") != identifier and d.get("source") != url] + [offer]
    data["offers"].sort(key=lambda d: (d.get("verifiedOn", ""), d.get("id", "")), reverse=True)
    APPROVED.parent.mkdir(parents=True, exist_ok=True)
    APPROVED.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Proposed {identifier} for pull request review. The offer will go live only after merge.")

if __name__ == "__main__":
    main()
