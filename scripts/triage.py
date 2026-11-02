#!/usr/bin/env python3
"""Persist maintainer triage choices from the GitHub Actions form."""
import datetime as dt
import json
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DISCOVERY=ROOT/"data/discovery.json"
OUT=ROOT/"data/triage.json"
lead_id=os.environ.get("LEAD_ID","").strip()
status=os.environ.get("LEAD_STATUS","").strip()
note=os.environ.get("REVIEW_NOTE","").strip()[:600]
if status not in ("needs_research","ready_for_review","rejected"):
    raise SystemExit("Unsupported review status")
leads=json.loads(DISCOVERY.read_text(encoding="utf-8")).get("leads",[])
if not any(x.get("id")==lead_id for x in leads):
    raise SystemExit("No such lead ID. Check the Discovery feed.")
data=json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"version":1,"decisions":[]}
existing=[x for x in data.get("decisions",[]) if x.get("id")!=lead_id]
existing.append({"id":lead_id,"status":status,"note":note,
                 "by":os.getenv("GITHUB_ACTOR","maintainer"),
                 "at":dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()})
data["decisions"]=sorted(existing,key=lambda x:x["at"],reverse=True)
OUT.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print("Saved triage state for lead",lead_id)
