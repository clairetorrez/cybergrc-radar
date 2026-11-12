#!/usr/bin/env python3
"""Refresh the public GRC news sidebar from source-owned RSS/Atom feeds."""
import datetime as dt
import email.utils
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT=pathlib.Path(__file__).resolve().parents[1]
DEST=ROOT/"data/grc_news.json"
TODAY=dt.datetime.now(dt.timezone.utc).date()
SOURCES=[
 ("NIST CSRC","https://csrc.nist.gov/rss/csrc-news.xml","csrc.nist.gov",5),
 ("FedRAMP","https://www.fedramp.gov/feed/","fedramp.gov",5),
 ("CISA","https://www.cisa.gov/news.xml","cisa.gov",3),
 ("ISACA","https://www.isaca.org/resources/news-and-trends/newsletters/atisaca/rss","isaca.org",3),
 ("Cloud Security Alliance","https://cloudsecurityalliance.org/blog/feed","cloudsecurityalliance.org",3),
 ("Corporate Compliance Insights","https://www.corporatecomplianceinsights.com/feed/","corporatecomplianceinsights.com",2),
 ("Open Policy Agent","https://www.openpolicyagent.org/blog/index.xml","openpolicyagent.org",4),
]
KEYWORDS=[
 (r"\boscal\b|fedramp|compliance.as.code|policy.as.code|continuous (?:compliance|monitoring|authorization)|automated evidence|control automation|grc engineering",8),
 (r"\bcmmc\b|\bsox\b|\bitgc\b|\bsoc 2\b|\biso 27001\b|\biso 42001\b|\bnist\b|ai governance|third.party risk|vendor risk",6),
 (r"\baudit\b|compliance|governance|security controls|risk management|assurance|certification|certified|security policy",3),
 (r"free (?:exam|course|training)|beta exam|voucher|discount|open.source|github|workshop",3),
]
SKIP=re.compile(r"webinar replay|sponsored|advertorial|podcast transcript",re.I)

def txt(x):
 return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",x or ""))).strip()

def get_text(node,names):
 for name in names:
  child=node.find(name)
  if child is not None and child.text:return txt(child.text)
 return ""

def parse_date(value):
 if not value:return None
 try:
  d=email.utils.parsedate_to_datetime(value)
  if d:return d.date()
 except (ValueError,TypeError,IndexError):pass
 try:return dt.date.fromisoformat(value[:10])
 except ValueError:return None

def host_ok(url,host):
 p=urllib.parse.urlparse(url)
 h=(p.hostname or "").lower()
 return p.scheme=="https" and (h==host or h.endswith("."+host))

def read_feed(source):
 name,feed,host,authority=source
 req=urllib.request.Request(feed,headers={"User-Agent":"CyberGRCRadar-News/1.0","Accept":"application/rss+xml, application/atom+xml, application/xml;q=0.9"})
 with urllib.request.urlopen(req,timeout=12) as response:
  raw=response.read(1200000)
 root=ET.fromstring(raw)
 nodes=root.findall(".//item")+root.findall(".//{http://www.w3.org/2005/Atom}entry")
 out=[]
 for node in nodes[:60]:
  title=get_text(node,["title","{http://www.w3.org/2005/Atom}title"])
  url=get_text(node,["link"])
  if not url:
   for link in node.findall("{http://www.w3.org/2005/Atom}link"):
    if link.get("rel","alternate")=="alternate":url=link.get("href","");break
  if not host_ok(url,host) or not title or len(title)<15 or SKIP.search(title):continue
  date=parse_date(get_text(node,["pubDate","{http://www.w3.org/2005/Atom}published","{http://www.w3.org/2005/Atom}updated","{http://purl.org/dc/elements/1.1/}date"]))
  if not date or date>TODAY or (TODAY-date).days>21:continue
  desc=get_text(node,["description","{http://www.w3.org/2005/Atom}summary"])
  text=(title+" "+desc[:400]).lower()
  relevance=sum(points for pattern,points in KEYWORDS if re.search(pattern,text,re.I))
  if relevance<6:continue
  score=relevance+authority+max(0,14-(TODAY-date).days)*0.35
  category="Engineering" if re.search(r"oscal|automation|policy.as.code|continuous",text) else "AI governance" if re.search(r"ai governance|ai risk",text) else "Federal" if re.search(r"fedramp|cmmc|nist",text) else "Certification" if re.search(r"certification|exam|voucher",text) else "Industry"
  out.append({"title":title[:125],"source":name,"date":date.isoformat(),"category":category,"url":url,"score":round(score,2)})
 return out

def main():
 existing=json.loads(DEST.read_text())
 found=[]
 errors=[]
 for source in SOURCES:
  try:found.extend(read_feed(source))
  except Exception as exc:errors.append(source[0]+": "+type(exc).__name__)
 seen=set()
 ranked=[]
 for item in sorted(found,key=lambda x:(-x["score"],x["title"])):
  key=urllib.parse.urlsplit(item["url"]).path.rstrip("/").lower()
  if key in seen:continue
  seen.add(key);ranked.append(item)
 # Keep previously curated articles as a fallback, but do not rewrite their dates.
 for old in existing.get("items",[]):
  if len(ranked)>=5:break
  if old.get("url") not in {x["url"] for x in ranked}:ranked.append(old)
 if not found:
  print("No new qualifying source articles; retaining existing feed. Errors: "+", ".join(errors))
  return
 published=[]
 for x in ranked[:8]:
  x=dict(x);x.pop("score",None);published.append(x)
 new={"updated":TODAY.isoformat(),"items":published}
 if new!=existing:DEST.write_text(json.dumps(new,indent=2,ensure_ascii=False)+"\n")
 print("Published",len(published),"news items from",len(found),"qualifying feed entries. Source errors:",", ".join(errors) or "none")

if __name__=="__main__":main()
