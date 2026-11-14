#!/usr/bin/env python3
"""Refresh event listings from official pages with conservative JSON-LD Event parsing.

Existing curated events remain until their end date. New entries require a
provider Event schema, explicit start/end dates, and a matching official URL.
Ambiguous pricing stays 'See provider', never 'Free'.
"""
import datetime as dt
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent.parent
OUTPUT=ROOT/"data/events.json"
SOURCES=ROOT/"data/sources.json"
TODAY=dt.datetime.now(dt.timezone.utc).date()
class Schema(HTMLParser):
    def __init__(self):
        super().__init__();self.in_schema=False;self.chunks=[];self.buffer=[]
    def handle_starttag(self,tag,attrs):
        if tag=="script" and dict(attrs).get("type","").lower()=="application/ld+json":
            self.in_schema=True;self.buffer=[]
    def handle_data(self,data):
        if self.in_schema:self.buffer.append(data)
    def handle_endtag(self,tag):
        if tag=="script" and self.in_schema:
            self.chunks.append("".join(self.buffer));self.in_schema=False
def flatten(node):
    if isinstance(node,list):
        for n in node:yield from flatten(n)
    elif isinstance(node,dict):
        if node.get("@type")=="Event" or "Event" in (node.get("@type") if isinstance(node.get("@type"),list) else []):yield node
        for k in ("@graph","itemListElement","mainEntity"):
            if k in node:yield from flatten(node[k])
def date(value):
    if not isinstance(value,str):return None
    try:return dt.date.fromisoformat(value[:10]).isoformat()
    except ValueError:return None
def main():
    data=json.loads(OUTPUT.read_text());old=data.get("events",[])
    byurl={x["source"].rstrip("/").lower():x for x in old if x.get("source")}
    sources=json.loads(SOURCES.read_text())
    if isinstance(sources,dict):sources=sources.get("sources",[])
    audit=[]
    for source in sources:
        if not isinstance(source,dict) or not re.search(r"event|fest|webinar|summit|conference",source.get("name",""),re.I):continue
        url=source.get("url","")
        if not url.startswith("https://"):continue
        try:
            with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; CyberGRCRadar/1.0)"}),timeout=12) as response:
                html=response.read(900000).decode("utf-8","replace")
            parser=Schema();parser.feed(html)
            count=0
            for chunk in parser.chunks:
                try:records=list(flatten(json.loads(chunk)))
                except (ValueError,TypeError):continue
                for record in records:
                    start=date(record.get("startDate"));end=date(record.get("endDate")) or start
                    title=record.get("name","")
                    link=record.get("url") or url
                    if not isinstance(link,str) or not link.startswith("https://"):continue
                    if not isinstance(title,str) or not start or not end or end<TODAY.isoformat():continue
                    if urlparse(link).hostname!=urlparse(url).hostname:continue
                    key=link.rstrip("/").lower()
                    if key in byurl:continue
                    offers=record.get("offers",{})
                    if isinstance(offers,list):offers=offers[0] if offers else {}
                    if not isinstance(offers,dict):offers={}
                    price=offers.get("price")
                    free=str(price).strip() in ("0","0.0","0.00") and bool(offers.get("priceCurrency"))
                    ident="event-"+re.sub(r"[^a-z0-9]+","-",title.lower()).strip("-")[:65]+"-"+start
                    byurl[key]={"id":ident,"title":title[:170],"provider":source["name"],"category":source.get("group","Security training"),"kind":"Event","price":"Free registration" if free else "See provider","discount":"","description":"Upcoming provider-listed cybersecurity event. Check the official page for sessions, registration and CPE terms.","eligibility":"Registration and pricing subject to provider terms.","startDate":start,"deadline":end,"dateLabel":start+" to "+end,"frameworks":["GRC"],"tags":["Official event"]+(["Free registration"] if free else []),"source":link,"verifiedOn":TODAY.isoformat(),"featured":False,"score":75}
                    count+=1
            audit.append({"source":source["name"],"status":"ok","new":count})
        except Exception as exc:audit.append({"source":source.get("name"),"status":"fetch_failed","reason":type(exc).__name__})
    data["events"]=sorted((x for x in byurl.values() if (x.get("deadline") or "9999")>=TODAY.isoformat()),key=lambda x:(x.get("startDate") or "9999",x["title"]))
    data["lastChecked"]=TODAY.isoformat();data["sourceHealth"]=audit
    OUTPUT.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n")
    print("Events:",len(data["events"]),"sources checked:",len(audit))
if __name__=="__main__":main()
