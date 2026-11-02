#!/usr/bin/env python3
"""Recheck approved listing pages without claiming their offers are confirmed active.

Only a human review can set verifiedOn in data/approved.json.
"""
from __future__ import annotations
import concurrent.futures as futures
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from discover import fetch, Page, clean, UTC, TODAY

ROOT=Path(__file__).resolve().parents[1]
APPROVED=ROOT/"data/approved.json"
OUTPUT=ROOT/"data/revalidation.json"
CONFIG=ROOT/"data/sources.json"
INDEX=ROOT/"index.html"
SAFE_SEED_HOSTS={"theforage.com","secure-platform.com","splunk.com","attackiq.com","linuxfoundation.org","qualys.com","microsoft.com","isaca.org","isc2.org","pecb.com","owasp.org","cloudsecurityalliance.org"}
MAX_REVIEW_DAYS=14

def review(offer,hosts):
    outcome={"id":offer["id"],"url":offer["source"],"lastChecked":UTC(),"status":"needs_review","reason":"Unable to confirm the offer terms automatically"}
    deadline=offer.get("deadline")
    if deadline and deadline<TODAY.isoformat():
        outcome.update(status="expired",reason="Published expiration date passed")
        return outcome
    try:
        raw=fetch(offer["source"],hosts)
        parsed=Page();parsed.feed(raw)
        title=clean(" ".join(parsed.heading) or parsed.meta.get("og:title") or " ".join(parsed.title),180)
        desc=clean(parsed.meta.get("description") or parsed.meta.get("og:description") or "",320)
        body=clean(" ".join(parsed.body),40000)
        signature=hashlib.sha256((title+"|"+desc+"|"+offer.get("evidence","")).encode()).hexdigest()[:18]
        # Compare only when source fingerprints are comparable to observed text.
        source_fingerprint=offer.get("sourceFingerprint")
        if source_fingerprint:
            from discover import evidence
            actual=hashlib.sha256((title+"|"+desc+"|"+evidence(title,desc,body)).encode()).hexdigest()[:18]
            if source_fingerprint!=actual:
                outcome.update(status="changed",reason="Provider page content differs from the approved evidence")
                return outcome
        verified=offer.get("verifiedOn","")
        try:age=(TODAY-dt.date.fromisoformat(verified)).days
        except ValueError:age=999
        if age>MAX_REVIEW_DAYS:
            outcome.update(status="review_due",reason=f"Last human approval was {age} days ago")
        else:
            outcome.update(status="checked",reason="Page reachable; human-reviewed terms still require independent confirmation")
    except Exception as exc:
        outcome.update(status="unreachable",reason="Provider page could not be fetched: "+str(exc)[:90])
    return outcome

def main():
    sources=json.loads(CONFIG.read_text(encoding="utf-8"))["sources"]
    hosts={urlparse(s["url"]).hostname.lower() for s in sources}|SAFE_SEED_HOSTS
    # Existing initial catalog entries are not in this file, and should not be
    # incorrectly marked as verified through the automated scan.
    offers=json.loads(APPROVED.read_text(encoding="utf-8")).get("offers",[])
    if not isinstance(offers,list):raise SystemExit("Invalid approved offers")
    # Legacy curated cards were embedded before the approval feed existed.
    # Recheck them too, without calling their automated checks "verification".
    page=INDEX.read_text(encoding="utf-8")
    found=re.search(r"(?:let|const) deals=(\[.*?\]);const sections=",page,re.S)
    legacy=json.loads(found.group(1)) if found else []
    existing={o.get("source") for o in offers}
    offers.extend(o for o in legacy if o.get("source") and o["source"] not in existing)
    with futures.ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(lambda d:review(d,hosts),offers))
    output={"lastChecked":UTC(),"reviewAfterDays":MAX_REVIEW_DAYS,"results":results,
            "note":"HTTP checks are not proof that offer terms remain valid. Changed/unreachable/stale listings require renewed human approval."}
    OUTPUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Checked {} approved listings: {}".format(len(results),{name:sum(x["status"]==name for x in results) for name in set(x["status"] for x in results)}))

if __name__=="__main__":main()
