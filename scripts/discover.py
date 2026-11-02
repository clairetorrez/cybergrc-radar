#!/usr/bin/env python3
"""Collect source-linked cybersecurity/GRC opportunity leads.

Leads are UNVERIFIED and are never promoted into the curated offer catalog.
Uses only Python standard library and public provider pages.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "discovery.json"
SOURCES = [
    ("ISC2 Insights", "https://www.isc2.org/api/rss/insights", "rss"),
    ("PECB News", "https://pecb.com/en/newsReleases", "html"),
    ("ISACA Offers", "https://www.isaca.org/training-and-events/training-topics/featured-training", "html"),
    ("ISACA Foundation", "https://www.isaca.org/why-isaca/about-us/isaca-foundation", "html"),
    ("Linux Foundation Training", "https://training.linuxfoundation.org/", "html"),
    ("SANS Offers", "https://www.sans.org/specials/north-america", "html"),
    ("Cloud Security Alliance", "https://cloudsecurityalliance.org/blog/", "html"),
    ("OWASP Opportunities", "https://owasp.org/projects/", "html"),
    ("NIST Announcements", "https://www.nist.gov/news-events/news", "html"),
]
ALLOWED = (
    "isc2.org", "pecb.com", "isaca.org", "linuxfoundation.org", "sans.org",
    "cloudsecurityalliance.org", "owasp.org", "nist.gov",
)
OPPORTUNITY = re.compile(
    r"\b(beta|pilot|voucher|coupon|discount|deal|sale|scholarship|grant|"
    r"free|volunteer|working.group|internship|externship|challenge|"
    r"workshop|webinar|fellowship|giveaway|promotion|competition|"
    r"reduced.price|special.offer|cybersecurity.month)\b|\d{1,2}\s?%\s?off", re.I
)
RELEVANCE = re.compile(
    r"\b(cyber|security|audit|iso[\s/-]?\d|soc[\s/-]?[12]|cmmc|fedramp|"
    r"risk|compliance|grc|cert|exam|cloud|AI|governance|privacy|training|"
    r"discount|volunteer|scholarship)\b", re.I
)
BLOCKED = re.compile(
    r"\b(cookie|privacy policy|terms of use|accessibility|sign in|log in|"
    r"facebook|linkedin|youtube|skip to content|subscribe to our newsletter)\b", re.I
)
MAX_DAILY = 45
MAX_ARCHIVE = 140

class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchor = None
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            self.anchor = {"href": href, "text": []}

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            self.items.append((self.anchor["href"], " ".join(self.anchor["text"])))
            self.anchor = None

def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "CyberGRCRadar/1.0 (source monitoring, public provider pages)",
        "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=16) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read(1_600_000)
        return raw.decode("utf-8", errors="replace"), content_type

def valid_url(url):
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and any(host == x or host.endswith("." + x) for x in ALLOWED)
    except ValueError:
        return False

def canonical_url(url, base):
    url = urllib.parse.urljoin(base, html.unescape(url or "").strip())
    if not valid_url(url):
        return None
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    query = [(k, v) for k, v in query if not (k.lower().startswith("utm_") or k.lower() in ("gclid", "fbclid"))]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/") or "/", "", urllib.parse.urlencode(query), ""))

def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()[:210]

def classify(title):
    t = title.lower()
    if re.search(r"\bscholarship|fellowship|grant\b", t):
        return "Scholarships"
    if re.search(r"\bvolunteer|working.group|contribute|mentorship\b", t):
        return "Volunteer"
    if re.search(r"\bfree\b.*\b(exam|certif|voucher)\b|\b(exam|voucher)\b.*\bfree\b", t):
        return "Free exams / vouchers"
    if re.search(r"\bbeta\b|\bpilot\b", t):
        return "Beta / pilot (cost unconfirmed)"
    if re.search(r"\bdiscount|coupon|sale|deal|off\b", t):
        return "Discounts"
    if re.search(r"\bwebinar|course|training|bootcamp|workshop\b", t):
        return "Training"
    return "Other opportunities"

def make_lead(name, base, title, href):
    title = clean(title)
    url = canonical_url(href, base)
    if not url or len(title) < 12 or len(title) > 170 or BLOCKED.search(title) or re.search(r"\b(scholarship recipients|award winners|free resources)\b", title, re.I):
        return None
    if not OPPORTUNITY.search(title) or not RELEVANCE.search(title + " " + url):
        return None
    if url.rstrip("/") == base.rstrip("/"):
        return None
    stable = hashlib.sha256(url.encode("utf-8")).hexdigest()[:18]
    return {
        "id": stable, "title": title, "source": name, "url": url,
        "category": classify(title), "status": "Needs verification",
    }

def collect_html(source, url, data):
    parser = Links()
    parser.feed(data)
    result = []
    for href, text in parser.items:
        lead = make_lead(source, url, text, href)
        if lead:
            result.append(lead)
    return result

def collect_rss(source, url, data):
    results = []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        # Some provider RSS documents contain malformed CDATA. Recover intact item blocks.
        for fragment in re.findall(r"<item(?:\s[^>]*)?>(.*?)</item>", data, re.I | re.S)[:120]:
            title_match = re.search(r"<title[^>]*>(.*?)</title>", fragment, re.I | re.S)
            link_match = re.search(r"<link[^>]*>(.*?)</link>", fragment, re.I | re.S)
            if not title_match or not link_match:
                continue
            title = re.sub(r"^<!\[CDATA\[|\]\]>$", "", title_match.group(1).strip())
            item = make_lead(source, url, title, link_match.group(1).strip())
            if item:
                results.append(item)
        return results
    for entry in list(root.findall(".//item")) + list(root.findall(".//{http://www.w3.org/2005/Atom}entry")):
        title = entry.findtext("title") or entry.findtext("{http://www.w3.org/2005/Atom}title") or ""
        link = entry.findtext("link")
        if not link:
            atom = entry.find("{http://www.w3.org/2005/Atom}link")
            link = atom.attrib.get("href", "") if atom is not None else ""
        item = make_lead(source, url, title, link or "")
        if item:
            results.append(item)
    return results

def main():
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    existing = {}
    if OUTPUT.exists():
        try:
            obj = json.loads(OUTPUT.read_text(encoding="utf-8"))
            existing = {x["id"]: x for x in obj.get("leads", []) if x.get("id") and x.get("url") and OPPORTUNITY.search(x.get("title", ""))}
        except (ValueError, KeyError, TypeError):
            pass

    prior_ids = set(existing)
    fresh = []
    sources = []
    for name, url, mode in SOURCES:
        try:
            page, mime = fetch(url)
            findings = collect_rss(name, url, page) if mode == "rss" else collect_html(name, url, page)
            # Do not list a provider's whole navigation. Keep only strongest leads per source.
            count = 0
            for item in findings:
                if count >= 10:
                    break
                if item["id"] not in {x["id"] for x in fresh}:
                    fresh.append(item)
                    count += 1
            sources.append({"name": name, "ok": True, "matches": count})
            print(f"{name}: {count} possible leads")
        except (OSError, ValueError, ET.ParseError, UnicodeError) as exc:
            sources.append({"name": name, "ok": False, "matches": 0, "error": str(exc)[:120]})
            print(f"{name}: unavailable ({exc})", file=sys.stderr)

    for item in fresh[:MAX_DAILY]:
        old = existing.get(item["id"], {})
        existing[item["id"]] = {
            **item,
            "firstSeen": old.get("firstSeen", now[:10]),
            "lastSeen": now[:10],
        }
    items = sorted(existing.values(), key=lambda x: (x.get("lastSeen", ""), x.get("firstSeen", ""), x.get("id", "")), reverse=True)[:MAX_ARCHIVE]
    status = "ok" if any(s["ok"] for s in sources) else "sources_unavailable"
    result = {
        "lastChecked": now, "status": status,
        "note": "Automatically discovered leads are unverified. Prices, terms and availability must be checked with the provider.",
        "sources": sources, "newLeads": sum(1 for x in fresh[:MAX_DAILY] if x["id"] not in prior_ids),
        "leads": items,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(items)} candidate leads to {OUTPUT}; healthy sources: {sum(x['ok'] for x in sources)}")
    if not any(s["ok"] for s in sources):
        # Preserve old leads but report that this search did not work.
        sys.exit(1)

if __name__ == "__main__":
    main()
