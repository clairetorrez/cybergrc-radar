#!/usr/bin/env python3
"""Conservative, fully automatic promotion from provider pages to the live catalog.

Every listed price, deadline, and type must be supported by the provider page.
Unclear leads are withheld, not presented as verified. No LLM/API key needed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from discover import (
    ROOT, TODAY, UTC, Page, TOPICS, clean, evidence, fetch, deadline_from_text,
)

FEED=ROOT/"data/discovery.json"
OUTPUT=ROOT/"data/approved.json"
AUDIT=ROOT/"data/auto_decisions.json"
CONFIG=ROOT/"data/sources.json"
DENY=re.compile(r"\b(application period is now closed|applications? (?:are )?closed|registration (?:is )?closed|no longer accepting|no longer available|sold out|campaign has ended|offer has expired|expired offer)\b",re.I)
BAD_TITLE=re.compile(r"\b(research|report|recipients|awarded|announces winners|exam outline|press release|training catalog|your journey|exam prep)\b",re.I)
GENERAL=re.compile(r"^(?:AI Security Certification|Free Courses|Free Resources|Participate & Volunteer|ISACA Foundation Scholarships|Training Events|Membership|News|Training|Shop)$",re.I)
FREE_EXAM=[
    re.compile(r"\b(?:pilot|beta|certification)?\s*exams?\s+free of charge\b",re.I),
    re.compile(r"\bfree(?:\s+of\s+charge)?\s+(?:[a-z-]+\s+){0,4}(?:exam|examination|voucher|assessment)\b",re.I),
    re.compile(r"\b(?:exam|pilot exam|examination)\s+(?:is|are|will be)\s+(?:completely )?free\b",re.I),
    re.compile(r"\bno charge to (?:participate in|take|sit for|register for)\s+(?:the |a |an )?(?:pilot |beta |certification )?exam\b",re.I),
    re.compile(r"\b(?:pilot|beta)\s+exams?\s+(?:at no cost|without charge)\b",re.I),
]
FREE_COURSE=re.compile(r"\bfree (?:online |self-paced )?(?:training|course|webinar|workshop)\b|\b(?:training|course|webinar)\s+(?:is|are)\s+free\b",re.I)
DISCOUNT=re.compile(r"\b(?:save|get|enjoy|receive|discount(?:ed)?(?: by| of)?|offer|take)\s+(?:up to\s+)?(\d{2})\s?%\s*(?:off|discount)?\b|\b(\d{2})\s?%\s*off\b",re.I)
ACTIVE=re.compile(r"\b(?:apply|register|join|participate|volunteer|sign up|enroll|claim|redeem|use code|book)\b",re.I)
FREE_VOUCHER=re.compile(r"\b(?:free|no-cost|complimentary)\b.{0,55}\b(?:voucher|exam|assessment|certification)\b|\b(?:voucher|exam|assessment)\b.{0,55}\b(?:free|no charge|without cost)\b",re.I)

def page_text(parsed):
    full=clean(" ".join(parsed.body),120000)
    heading=clean(" ".join(parsed.heading),170)
    idx=full.lower().find(heading.lower()) if heading else -1
    return full[idx:] if idx>=0 else full

def quote_clue(text,marker):
    lo=max(0,marker.start()-65);hi=min(len(text),marker.end()+160)
    return " ".join(text[lo:hi].strip().split()[:23])

def parse_offer(lead,raw):
    parsed=Page();parsed.feed(raw)
    title=clean(" ".join(parsed.heading) or parsed.meta.get("og:title") or lead.get("title"),170)
    desc=clean(parsed.meta.get("description") or parsed.meta.get("og:description"),380)
    body=page_text(parsed)
    # A specific announcement is required, not a generic provider landing page.
    if not title or GENERAL.fullmatch(title):return None,"generic_page"
    if BAD_TITLE.search(title) and not re.search(r"\b(beta|pilot|free|discount|scholarship)\b",title,re.I):
        return None,"editorial_or_evergreen"
    if not body or len(body)<130:return None,"not_enough_page_text"
    # Before approving, avoid pages that explicitly close applications.
    intro=(title+" "+body[:3500]).lower()
    if DENY.search(intro):return None,"offer_closed"
    deadline=deadline_from_text(body[:32000])
    if deadline and deadline<TODAY.isoformat():return None,"deadline_passed"
    published=lead.get("publishedAt")
    if published:
        try:
            age=(TODAY-dt.date.fromisoformat(published)).days
            if age>240 and not re.search(r"\b(?:ongoing|always free|free online course)\b",intro):
                return None,"old_announcement"
        except ValueError:pass

    kind=None;price=None;detail=None;confidence=0
    # Use the current provider's page itself for all evidence.
    # No pilot or beta is automatically free simply because it's a pilot.
    # Content after the heading avoids site-wide promotional navigation.
    for pattern in FREE_EXAM:
        match=pattern.search(body)
        if match:
            kind="Free exam";price="$0 exam";detail=match;confidence=95
            break
    if not kind:
        m=DISCOUNT.search(body[:11500])
        if m and (re.search(r"discount|sale|promotion|special offer|\d{2}\s?% off",title,re.I)
                  or re.search(r"\b(?:discount|promo code|special offer)\b",desc,re.I)):
            pct=int(m.group(1) or m.group(2))
            if 20<=pct<=90:
                kind="Discount";price=f"{pct}% off";detail=m;confidence=91
    if not kind and re.search(r"\b(?:free|complimentary)\b",title,re.I):
        m=FREE_COURSE.search(body[:16000])
        if m and re.search(r"course|training|webinar|workshop",title,re.I):
            kind="Free training";price="Free training";detail=m;confidence=90
    if not kind and re.search(r"scholarship|grant|fellowship",title,re.I):
        m=re.search(r"\b(?:apply now|applications? open|accepting applications)\b",body[:11000],re.I)
        if m and deadline:
            kind="Scholarship";price="Award value varies";detail=m;confidence=92
    if not kind and re.search(r"volunteer|working group|contribut",title,re.I):
        m=re.search(r"\b(?:volunteer|participate|contribute|join)\b.{0,120}\b(?:opportunities|project|group|program|community|initiative)\b",body[:16000],re.I)
        if m and not re.search(r"recap|has concluded|past volunteers",body[:1400],re.I):
            kind="Volunteer";price="Volunteer participation";detail=m;confidence=91
    # A monitored beta program that explicitly invites applications may
    # qualify even if price is unknown, but only if its heading names a pilot.
    if not kind and re.search(r"\b(?:beta|pilot)\b",title,re.I):
        m=re.search(r"(?:volunteer|apply|register|participate)\b.{0,140}\b(?:pilot|beta)\b|\b(?:pilot|beta)\b.{0,140}\b(?:volunteer|apply|register|participate)\b",body[:22000],re.I)
        if m and deadline:
            kind="Volunteer";price="Pilot participation, fee not confirmed";detail=m;confidence=90
    if not kind or not detail:return None,"insufficient_offer_evidence"
    # Time-sensitive campaigns require a clearly published current deadline.
    if kind in ("Free exam","Discount","Scholarship") and not deadline:
        # Truly evergreen free training has its own category above.
        return None,"deadline_not_confirmed"
    if kind=="Discount" and not re.search(r"\b(?:offer|discount|promotion|save|valid|expires|ends)\b",body[max(0,detail.start()-80):detail.end()+120],re.I):
        return None,"discount_context_unconfirmed"
    # Prevent a generic free training section from being mislabeled a free exam.
    if kind=="Free exam" and not (re.search(r"exam|certification|pilot",title,re.I)
                                or re.search(r"exam",body[max(0,detail.start()-110):detail.end()+120],re.I)):
        return None,"exam_type_unclear"
    if deadline and (dt.date.fromisoformat(deadline)-TODAY).days>370:
        return None,"deadline_implausibly_distant"

    topics=[k for k,pat in TOPICS.items() if re.search(pat,title+" "+desc+" "+body[:6000],re.I)]
    label=dt.date.fromisoformat(deadline).strftime("Ends %b %d, %Y") if deadline else "No listed deadline"
    if kind=="Free exam":
        eligibility="Check the provider's selection, experience, exam, and scheduling requirements."
    elif kind=="Scholarship":
        eligibility="Review the application requirements on the provider's page."
    else:
        eligibility="Review provider eligibility, location, membership, and availability conditions."
    # Document evidence without copying full protected source paragraphs.
    clue=quote_clue(body,detail)
    if not clue:return None,"missing_evidence"
    identity="auto-"+hashlib.sha256(lead["url"].encode()).hexdigest()[:14]
    fingerprint=hashlib.sha256((title+"|"+desc+"|"+evidence(title,desc,clean(" ".join(parsed.body),40000))).encode()).hexdigest()[:18]
    offer={
      "id":identity,"title":title,"provider":lead["source"],"category":lead.get("group") or "GRC",
      "kind":kind,"price":price,"discount":price if kind=="Discount" else "",
      "description":f"{kind} listed by the provider. Check the official source for full details.",
      "eligibility":eligibility,"deadline":deadline,"dateLabel":label,
      "frameworks":topics[:8],"tags":["Automatically checked","Official provider"],
      "source":lead["url"],"verifiedOn":TODAY.isoformat(),
      "reviewStatus":"auto_verified","verificationMethod":"official_source_rules",
      "confidence":confidence,"evidence":clue,"sourceFingerprint":fingerprint,
      "autoApproved":True,"publicationStatus":"active","featured":False,
      "score":max(80,min(99,lead.get("score") or 85)),
    }
    return offer,None

def run():
    config=json.loads(CONFIG.read_text(encoding="utf-8"))
    hosts={urlparse(s["url"]).hostname.lower() for s in config["sources"]}
    sources={s["url"]:s for s in config["sources"]}
    discovered=json.loads(FEED.read_text(encoding="utf-8"))
    data=json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {"version":2,"offers":[]}
    existing=list(data.get("offers") or [])
    manual=[x for x in existing if not x.get("autoApproved")]
    previous={x["source"]:x for x in existing if x.get("autoApproved") and x.get("source")}
    # Maintain previously published programs even when they drop out of the RSS feed.
    targets={}
    for lead in discovered.get("leads",[]):
        if not lead.get("url") or lead.get("status") not in ("needs_review","needs_recheck"):continue
        if lead.get("lastSeen")!=TODAY.isoformat():continue
        if (lead.get("score") or 0)<50:continue
        targets[lead["url"]]=lead
    for u,old in previous.items():
        targets.setdefault(u,{
          "url":u,"title":old.get("title"),"source":old.get("provider"),
          "group":old.get("category"),"publishedAt":None,"score":old.get("score",85),
        })
    active=[];decisions=[];inactive=[];status_counts={}
    for url,lead in sorted(targets.items()):
        if not urlparse(url).hostname or not any(urlparse(url).hostname==x or urlparse(url).hostname.endswith("."+x) for x in hosts):
            decisions.append({"url":url,"status":"withheld","reason":"not_official_source"});continue
        try:
            page=fetch(url,hosts)
            new,reason=parse_offer(lead,page)
            if new:
                active.append(new)
                decisions.append({"url":url,"status":"auto_published","kind":new["kind"],"confidence":new["confidence"],"expires":new["deadline"]})
            else:
                decisions.append({"url":url,"status":"withheld","reason":reason})
                if url in previous:
                    old=dict(previous[url]);old["publicationStatus"]="paused"
                    inactive.append(old)
        except Exception as exc:
            decisions.append({"url":url,"status":"fetch_failed","reason":type(exc).__name__})
            if url in previous:
                old=dict(previous[url]);old["publicationStatus"]="paused"
                inactive.append(old)
    # Maintain only active, machine-confirmed offers in the public catalog.
    # Keep a separate record of deactivated opportunities for traceability.
    for x in decisions:status_counts[x["status"]]=status_counts.get(x["status"],0)+1
    active.sort(key=lambda x:(x["confidence"],x.get("deadline") or "9999-99-99"),reverse=True)
    data={"version":2,"lastChecked":UTC(),"offers":manual+active,
          "inactive":inactive[:100],"automation":{"enabled":True,"method":"provider_page_rules",
          "minConfidence":90,"statistics":status_counts}}
    OUTPUT.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    AUDIT.write_text(json.dumps({"lastChecked":UTC(),"decisions":decisions},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Auto-publication: {len(active)} current provider-supported offers; {len(inactive)} paused; {len(decisions)} reviewed URLs")

if __name__=="__main__":run()
