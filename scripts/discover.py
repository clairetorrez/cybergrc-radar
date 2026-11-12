#!/usr/bin/env python3
"""Discover cybersecurity/GRC opportunities using official pages.

All findings are UNVERIFIED. The collector never writes approved.json.
Only source hosts configured in data/sources.json are fetched.
"""
from __future__ import annotations
import concurrent.futures as futures
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/discovery.json"
CONFIG = ROOT / "data/sources.json"
TODAY = dt.datetime.now(dt.timezone.utc).date()
UTC = lambda: dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
PROMOTION = re.compile(r"\b(beta|pilot|voucher|discount|coupon|scholarship|giveaway|volunteer|externship|fellowship|apprenticeship|apprentice|internship|intern|rotational program|cohort|grant|sweepstakes|competition|promotion|special offer|freelance|contract opportunity|paid project|bug bounty|security researcher|student program|early career|free (?:exam|certif|course|training|voucher|workshop)|certification month)\b|\d{1,2}\s?%\s?off", re.I)
SUBJECT = re.compile(r"\b(iso[\s/-]?\d{4,5}|soc\s?[12]|sox|itgc|fedramp|cmmc|nist|isaca|isc2|aws|azure|compTIA|cyber|security|risk|audit|grc|governance|AI|cloud|certification|CISA|CISSP|CRISC|internship|apprenticeship|freelance|contractor|penetration testing|bug bounty)\b", re.I)
GENERIC = re.compile(r"^(free resources|free courses|training catalog|training events|view training|certification training partners|regional training|all training courses|subscribe|learn more|read more|ways to train|training for government|it certification journey|career|research|events|scholarships|news|blog|resources)$", re.I)
BLOCK = re.compile(r"sign in|log in|cookie|privacy policy|terms of use|accessibility|linkedin|youtube|facebook|scholarship recipients|award winners", re.I)
TOPICS = {
    "ISO 27001":r"iso[\s/-]?(?:iec[\s/-]?)?27001","ISO 42001":r"iso[\s/-]?(?:iec[\s/-]?)?42001",
    "ISO 22301":r"iso[\s/-]?(?:iec[\s/-]?)?22301","ISO 27017":r"iso[\s/-]?(?:iec[\s/-]?)?27017",
    "ISO 27018":r"iso[\s/-]?(?:iec[\s/-]?)?27018","SOC 2":r"soc[\s/-]?2",
    "SOX/ITGC":r"\bsox\b|\bitgc\b", "FedRAMP":r"\bfedramp\b",
    "CMMC":r"\bcmmc\b", "TPRM":r"\btprm\b|third[- ]party risk|vendor risk|supplier due diligence|supply chain risk", "GRC engineering":r"grc engineering|grc automation|compliance automation|compliance as code", "AI governance":r"ai governance|\bai security\b",
    "Cloud security":r"cloud security|kubernetes", "IT audit":r"\bcisa\b|it audit"
}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec January February March April June July August September October November December"
MONTHS_SET = {s.lower() for s in MONTHS.split()}
MAX_BODY = 40000

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[];self.meta={};self.title=[];self.heading=[];self.body=[]
        self.anchor=None;self.depth_skip=0;self.in_title=False;self.in_h1=False
    def handle_starttag(self, tag, attrs):
        props=dict(attrs)
        if tag in ("script","style","svg","noscript"):
            self.depth_skip+=1;return
        if self.depth_skip:return
        if tag=="meta":
            key=(props.get("name") or props.get("property") or "").lower()
            if key and props.get("content"):self.meta[key]=props["content"]
        if tag=="a":self.anchor={"url":props.get("href",""),"parts":[]}
        if tag=="title":self.in_title=True
        if tag=="h1":self.in_h1=True
    def handle_data(self, value):
        if self.depth_skip:return
        value=value.strip()
        if not value:return
        if self.in_title:self.title.append(value)
        if self.in_h1:self.heading.append(value)
        if self.anchor is not None:self.anchor["parts"].append(value)
        self.body.append(value)
    def handle_endtag(self, tag):
        if tag in ("script","style","svg","noscript"):
            self.depth_skip=max(0,self.depth_skip-1);return
        if self.depth_skip:return
        if tag=="a" and self.anchor:
            self.links.append((self.anchor["url"]," ".join(self.anchor["parts"])))
            self.anchor=None
        if tag=="title":self.in_title=False
        if tag=="h1":self.in_h1=False

def clean(x,n=250):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",x or ""))).strip()[:n]

def allowed(url,hosts):
    try:
        parsed=urllib.parse.urlparse(url)
        host=(parsed.hostname or "").lower()
        return parsed.scheme=="https" and any(host==x or host.endswith("."+x) for x in hosts)
    except ValueError:return False

def normalize(href,base,hosts):
    if not href or href.startswith(("#","mailto:","javascript:")):return None
    url=urllib.parse.urljoin(base,html.unescape(href.strip()))
    if not allowed(url,hosts):return None
    parsed=urllib.parse.urlparse(url)
    params=[(k,v) for k,v in urllib.parse.parse_qsl(parsed.query) if not (k.lower().startswith("utm_") or k.lower() in ("fbclid","gclid"))]
    return urllib.parse.urlunparse((parsed.scheme,parsed.netloc,parsed.path.rstrip("/") or "/","",urllib.parse.urlencode(params),""))

def fetch(url,hosts):
    if not allowed(url,hosts):raise ValueError("URL outside configured source hosts")
    req=urllib.request.Request(url,headers={"User-Agent":"CyberGRCRadar/2.0 (public page monitoring)","Accept":"text/html, application/rss+xml, application/xml;q=0.9"})
    with urllib.request.urlopen(req,timeout=14) as response:
        final=response.geturl()
        if not allowed(final,hosts):raise ValueError("Redirect outside configured source hosts")
        raw=response.read(1100000)
    return raw.decode("utf-8","replace")

def parse_rss(raw):
    try:
        tree=ET.fromstring(raw)
        entries=list(tree.findall(".//item"))+list(tree.findall(".//{http://www.w3.org/2005/Atom}entry"))
        out=[]
        for x in entries[:120]:
            title=x.findtext("title") or x.findtext("{http://www.w3.org/2005/Atom}title") or ""
            url=x.findtext("link") or ""
            if not url:
                node=x.find("{http://www.w3.org/2005/Atom}link")
                if node is not None:url=node.get("href","")
            out.append((url,title))
        return out
    except ET.ParseError:
        out=[]
        for block in re.findall(r"<item(?:\s[^>]*)?>(.*?)</item>",raw,re.I|re.S)[:120]:
            title=re.search(r"<title[^>]*>(.*?)</title>",block,re.I|re.S)
            link=re.search(r"<link[^>]*>(.*?)</link>",block,re.I|re.S)
            if title and link:
                out.append((clean(title.group(1).replace("<![CDATA[","").replace("]]>","")),clean(link.group(1),1000)))
        return out

def published(meta):
    for name in ("article:published_time","date","datepublished","pubdate","article:modified_time"):
        value=meta.get(name,"")[:10]
        if re.match(r"\d{4}-\d\d-\d\d",value):return value
    return None

def deadline_from_text(text):
    # Date extraction only near explicit deadline phrases, never from unrelated page dates.
    month_re=r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    patterns=[
        rf"(?:deadline|expires?|ends?|closes?|apply by|before|until|through|valid until|remain available until|registration closes?)\s*(?:on|:|is|at|until|by|the)?\s*({month_re}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+20\d{{2}})",
        r"(?:deadline|expires?|ends?|closes?|apply by|before|until|through|valid until|remain available until|registration closes?)\s*(?:on|:|is|at|until|by|the)?\s*(20\d{2}-\d{2}-\d{2})"
    ]
    # Scholarship portals commonly write "Applications Due: 11:59 pm US CT, 30 November 2026".
    patterns.extend([
        rf"(?:applications?\s+due|applications?\s+close|application\s+deadline)\s*[:\-]?\s*.{{0,55}}?\b(\d{{1,2}}\s+{month_re}\s+20\d{{2}})",
        rf"(?:applications?\s+due|applications?\s+close|application\s+deadline)\s*[:\-]?\s*.{{0,55}}?\b({month_re}\s+\d{{1,2}},?\s+20\d{{2}})",
    ])
    for pattern in patterns:
        for m in re.finditer(pattern,text,re.I):
            raw=re.sub(r"(\d)(?:st|nd|rd|th)\b",r"\1",m.group(1),flags=re.I).replace(",","")
            for fmt in ("%B %d %Y","%b %d %Y","%d %B %Y","%d %b %Y","%Y-%m-%d"):
                try:return dt.datetime.strptime(raw,fmt).date().isoformat()
                except ValueError:pass
    return None

def category(title,body):
    t=(title+" "+body[:1200]).lower()
    if re.search(r"\bscholarship|fellowship|grant\b",title,re.I):return "Scholarships"
    if re.search(r"\bapprenticeship|apprentice|internship|intern|rotational program|cohort\b",title,re.I):return "Apprenticeships & internships" 
    if re.search(r"\bvolunteer|working group|contribut|externship\b",title,re.I):return "Volunteer & experience"
    if re.search(r"\bbeta\b|\bpilot\b",(title+" "+body[:600]) if "Certification Pilot" in body[:600] or "pilot exam" in body[:600] else title,re.I):return "Beta & pilot exams"
    if re.search(r"voucher|discount|coupon|\d{1,2}\s?% off|sale|special offer",title,re.I):return "Discounts & vouchers"
    if re.search(r"free exam|free certif",title,re.I):return "Free exams & credentials"
    if re.search(r"training|course|workshop|webinar",title,re.I):return "Training"
    return "Other opportunities"

def evidence(title,description,body):
    # Limited extract for a review lead, not a copied article.
    sentences=re.split(r"(?<=[.!?])\s+|\s{2,}",description+" "+body[:10000])
    ranked=sorted(sentences,key=lambda x:((4 if PROMOTION.search(x) else 0)+(2 if SUBJECT.search(x) else 0),-len(x)),reverse=True)
    for text in ranked:
        text=clean(text,240)
        if 25<=len(text)<=240 and PROMOTION.search(text):
            return " ".join(text.split()[:20])
    return " ".join(clean(description or title,200).split()[:20])

def price_hint(title,desc):
    context=title+" "+desc[:360]
    match=re.search(r"\b(\d{1,2}\s?%\s?off|\$\s?\d+(?:\.\d{2})?\s?(?:off|discount))\b",context,re.I)
    if match:return match.group(1).strip()
    if re.search(r"\bfree\b.{0,32}\b(?:exam|voucher|certification)\b|\b(?:exam|voucher|certification)\b.{0,32}\bfree\b",context,re.I):
        return "Free exam/voucher claimed; confirm terms"
    if re.search(r"\bfree (?:course|training|webinar)\b",context,re.I):
        return "Free training claimed; exam not confirmed"
    return "Not confirmed"

def score(title,description,body,pub,deadline):
    t=title.lower();d=(description+" "+body[:1800]).lower()
    val=20;why=[]
    if re.search(r"free.{0,30}(?:exam|certif|voucher)|(?:exam|voucher).{0,30}free",t):val+=35;why.append("Possible free exam")
    elif re.search(r"\bbeta\b|\bpilot\b",t):val+=31;why.append("Beta program")
    elif re.search(r"\bdiscount|voucher|\d{1,2}\s?% off|coupon|sale\b",t):val+=29;why.append("Discount signal")
    elif re.search(r"\bvolunteer|externship|scholarship|fellowship|apprenticeship|internship|rotational program|cohort\b",t):val+=23;why.append("Experience or funding")
    else:val+=8
    if re.search(r"free.{0,25}(?:exam|voucher)|(?:exam|voucher).{0,25}free",d):val+=11
    elif re.search(r"\bdiscount|voucher|\d{1,2}\s?% off|apply by\b",d):val+=6
    topics=[k for k,pattern in TOPICS.items() if re.search(pattern,title+" "+description[:500],re.I)]
    if topics:val+=min(16,5*len(topics));why.append("GRC focus: "+", ".join(topics[:2]))
    if pub:
        try:
            age=(TODAY-dt.date.fromisoformat(pub)).days
            if 0<=age<=21:val+=12;why.append("Recent announcement")
            elif age>365:val-=15
        except ValueError:pass
    if deadline:
        days=(dt.date.fromisoformat(deadline)-TODAY).days
        if days<0:val-=60;why.append("Deadline passed")
        elif days<=14:val+=15;why.append("Closing soon")
    if GENERIC.fullmatch(title):val-=55
    if re.search(r"\b(?:recipients|awarded|report|research|past event)\b",t):val-=28
    return max(0,min(100,val)),why,topics


APPRENTICESHIP_PAGE_EXCLUDE=re.compile(
    r"(?:/employers?(?:/|$)|/grants?(?:/|$)|/funding(?:/|$)|/news(?:/|$)|"
    r"/blog(?:/|$)|/resources?(?:/|$)|/events?(?:/|$)|/databases/das/|"
    r"/das(?:/|$)|/career-opportunities/?$)", re.I
)
APPRENTICESHIP_TITLE_EXCLUDE=re.compile(
    r"^(?:what (?:is|are)|how to|start (?:a|an)|understanding|apprenticeship vs|"
    r"internship vs|division of|apprenticeship data|apprenticeship management|"
    r"find an apprenticeship|apprenticeship programs information|"
    r"careers?\s*[-–]\s*the next|change the way|job seekers?|current opportunities|"
    r"apprenticeship e-news)|\b(?:employer resources?|funding guide|"
    r"apprenticeship innovation funding|grant recipients?)\b", re.I
)

def apprenticeship_application(title, url, evidence_text="", source=""):
    """Candidate-facing application pages, not educational/background links.

    Do not mark a directory or an employer-facing explanation as an opening.
    A generic pool/registration page also needs explicit active-application text.
    """
    parsed=urllib.parse.urlparse(url)
    host=(parsed.hostname or "").lower()
    path=re.sub(r"/+","/",parsed.path).lower().rstrip("/")
    if not host or APPRENTICESHIP_PAGE_EXCLUDE.search(path):return False
    if APPRENTICESHIP_TITLE_EXCLUDE.search(title):return False
    target=(title+" "+source).lower()
    career_relevant=re.search(r"\b(grc|cybersecurity|cyber|security|audit|compliance|risk|cloud|"
                              r"apprentice|apprenticeship|intern|internship|trainee)\b",target,re.I)
    specific_job=re.search(r"/(?:jobs?|positions?|openings?|vacancies)/[^/]+",path,re.I)
    if specific_job and career_relevant:return True
    topic=re.search(r"\b(apprentice|apprenticeship|intern|internship|cohort|"
                    r"rotational|trainee)\b",title,re.I)
    active=re.search(r"\b(accepting applications|applications? (?:are )?open|"
                     r"apply now|now accepting|submit an application|"
                     r"registration (?:is )?open)\b",evidence_text,re.I)
    application_route=re.search(r"/(?:apply|application|applications|register|join-a-cohort)(?:/|$)",path,re.I)
    program_page=re.search(r"/(?:apprenticeships|internships|programs|cohorts)/[^/]+",path,re.I)
    return bool(topic and (application_route or (program_page and active)))

def is_apprenticeship_source(lead):
    return (lead.get("category")=="Apprenticeships & internships" or
            re.search(r"apprenti|nextciso|per scholas registered",
                      lead.get("source",""),re.I))

def process_page(source,url,title_hint,page,old=None):
    parsed=Page();parsed.feed(page)
    title=clean(" ".join(parsed.heading) or parsed.meta.get("og:title") or title_hint or " ".join(parsed.title),180)
    desc=clean(parsed.meta.get("description") or parsed.meta.get("og:description") or "",320)
    body=clean(" ".join(parsed.body),MAX_BODY)
    if (source.get("group")=="Apprenticeships and experience" or
        re.search(r"apprenti|nextciso",source.get("name",""),re.I)):
        if not apprenticeship_application(title,url,desc+" "+body[:8000],source.get("name","")):return None
    if not title or GENERIC.fullmatch(title) or BLOCK.search(title):return None
    if re.search(r"\b(no one knows exam prep|your cybersecurity journey begins here|build team skills|become a part of our|train the new generation|all about training)\b",title,re.I):return None
    if re.search(r"\b(application period is now closed|applications? closed|no longer accepting|registration closed|has ended)\b",title,re.I):return None
    if re.search(r"^isaca foundation scholarships$",title,re.I):return None
    if not PROMOTION.search(title+" "+desc[:180]) and not (source.get("mode")=="watch" and PROMOTION.search(body[:2500])):return None
    if not SUBJECT.search(title+" "+desc+" "+source.get("group","")):return None
    deadline=deadline_from_text(desc+" "+body[:9000])
    pub=published(parsed.meta)
    value,why,topics=score(title,desc,body,pub,deadline)
    if source.get("mode")=="watch" and re.search(r"\b(beta|pilot|volunteer|apprenticeship|internship|cohort|free exam|discount)\b",body[:3200],re.I):
        value=min(100,value+21)
        why.append("Targeted source watch")
    if source.get("group")=="Apprenticeships and experience" and re.search(r"\b(apprenticeship|apprentice|internship|intern|cohort|rotational program)\b",title+" "+desc[:300],re.I):
        value=max(value,65)
    if source.get("group")=="Scholarships" and re.search(r"\bscholarship|grant|fellowship\b",title,re.I):
        value=min(100,value+22)
        why.append("Scholarship application page")
    if value<(50 if source.get("mode")=="watch" else 65):return None
    if deadline and deadline<TODAY.isoformat():return None
    category_name=category(title,desc+" "+body[:500] if source.get("mode")=="watch" else desc)
    if category_name=="Apprenticeships & internships" and not apprenticeship_application(
        title,url,desc+" "+body[:8000],source.get("name","")
    ):return None
    snippet=evidence(title,desc,body)
    identity=hashlib.sha256(url.encode()).hexdigest()[:18]
    fingerprint=hashlib.sha256((title+"|"+desc+"|"+snippet).encode()).hexdigest()[:18]
    change=bool(old and old.get("fingerprint") and old["fingerprint"]!=fingerprint)
    expired=bool(deadline and deadline<TODAY.isoformat())
    return {
        "id":identity,"title":title,"source":source["name"],"url":url,
        "category":category_name,"topics":topics,"group":source.get("group","General"),
        "status":"expired" if expired else ("needs_recheck" if change else "needs_review"),
        "score":value,"why":why,"evidence":snippet,"priceHint":price_hint(title,desc),
        "deadlineHint":deadline,"publishedAt":pub,"firstSeen":old.get("firstSeen",TODAY.isoformat()) if old else TODAY.isoformat(),
        "lastSeen":TODAY.isoformat(),"lastChecked":UTC(),"fingerprint":fingerprint,
        "verified":False,"reviewRequired":True,
    }

def collect_candidates(source,hosts):
    url=source["url"]
    raw=fetch(url,hosts)
    if source["mode"]=="rss":links=parse_rss(raw)
    else:
        page=Page();page.feed(raw)
        links=page.links
    items=[]
    if source["mode"]=="watch":items.append((url,source["name"]))
    for href,label in links:
        normalized=normalize(href,url,hosts)
        title=clean(label,160)
        if not normalized or normalized==url.rstrip("/") or not title or BLOCK.search(title):continue
        if GENERIC.fullmatch(title):continue
        if PROMOTION.search(title) or (SUBJECT.search(title) and re.search(r"(?:beta|pilot|training|scholarship|volunteer|free|discount|exam|internship|apprentice|freelance|contract|bounty|student)",title,re.I)):
            items.append((normalized,title))
    unique={}
    for u,t in items:unique.setdefault(u,t)
    return list(unique.items())[:source.get("maxLinks",12)]

def main():
    config=json.loads(CONFIG.read_text(encoding="utf-8"))
    sources=config["sources"]
    hosts={urllib.parse.urlparse(x["url"]).hostname.lower() for x in sources}
    prior={}
    if OUTPUT.exists():
        try:
            past=json.loads(OUTPUT.read_text(encoding="utf-8"))
            prior={x["id"]:x for x in past.get("leads",[])
                   if x.get("id") and (
                       (x.get("fingerprint") and
                        (not is_apprenticeship_source(x) or
                         apprenticeship_application(x.get("title",""),x.get("url",""),
                                                    x.get("evidence",""),x.get("source",""))))
                       or x.get("group") in ("Research intake","Employer and program research")
                   )}
        except (ValueError,TypeError):pass
    original_ids=set(prior)
    discovered=[];health=[];todo=[]
    with futures.ThreadPoolExecutor(max_workers=6) as pool:
        pending={pool.submit(collect_candidates,s,hosts):s for s in sources}
        for task in futures.as_completed(pending):
            source=pending[task]
            try:
                links=task.result()
                health.append({"name":source["name"],"ok":True,"candidates":len(links)})
                for url,title in links:todo.append((source,url,title))
            except Exception as ex:
                health.append({"name":source["name"],"ok":False,"candidates":0,"error":str(ex)[:110]})
    unique={}
    for source,url,title in todo:
        unique.setdefault(url,(source,url,title))
    cap=int(config.get("curation",{}).get("detailFetchLimit",45))
    tasks=sorted(unique.values(),key=lambda item:(
        item[0].get("mode")=="watch",
        bool(re.search(r"free.{0,25}exam|beta|pilot|voucher|scholarship",item[2],re.I)),
        bool(re.search(r"iso|cmmc|fedramp|audit|grc|risk|governance",item[0].get("group",""),re.I)),
        bool(re.search(r"discount|free|volunteer|special offer",item[2],re.I)),
    ),reverse=True)[:cap]
    with futures.ThreadPoolExecutor(max_workers=6) as pool:
        active={pool.submit(fetch,url,hosts):(source,url,title) for source,url,title in tasks}
        for done in futures.as_completed(active):
            source,url,title=active[done]
            try:
                raw=done.result()
                old=prior.get(hashlib.sha256(url.encode()).hexdigest()[:18])
                candidate=process_page(source,url,title,raw,old)
                if candidate:discovered.append(candidate)
            except Exception:pass
    current_ids={x["id"] for x in discovered}
    for candidate in discovered:prior[candidate["id"]]=candidate
    stale=int(config.get("curation",{}).get("staleDays",45))
    items=[]
    for lead in prior.values():
        if lead.get("lastSeen","")< (TODAY-dt.timedelta(days=stale)).isoformat():continue
        if (lead.get("id") not in current_ids
                and lead.get("group") not in ("Research intake","Employer and program research")
                and lead.get("status") not in ("expired","needs_recheck")):
            lead["status"]="not_seen_today"
        items.append(lead)
    items.sort(key=lambda x:(x.get("status")!="expired",x.get("score",0),x.get("lastSeen","")),reverse=True)
    items=items[:int(config.get("curation",{}).get("maxStoredLeads",200))]
    if not any(s["ok"] for s in health):
        status="sources_unavailable"
    else:
        status="partial" if not all(s["ok"] for s in health) else "ok"
    document={
      "version":2,"lastChecked":UTC(),"status":status,
      "note":"Unverified leads. Prices and eligibility must be confirmed on the official provider page.",
      "sources":sorted(health,key=lambda x:x["name"]),
      "newLeads":sum(x["id"] not in original_ids for x in discovered), 
      "leads":items,
    }
    OUTPUT.write_text(json.dumps(document,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("Discovery: {} pages evaluated, {} current candidates, {} stored, {} sources reached".format(len(tasks),len(discovered),len(items),sum(x["ok"] for x in health)))
    if status=="sources_unavailable":raise SystemExit("All sources unavailable; previous leads preserved")

if __name__=="__main__":
    main()
