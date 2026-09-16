from pathlib import Path
import json
import re

ROOT=Path(__file__).resolve().parents[2]
FORBIDDEN=[
    r"\bcreate_order\b", r"\bcancel_order\b", r"\bwithdraw\b", r"\bset_leverage\b",
    r"\bposition_margin\b", r"/fapi/v1/order", r"/api/v3/order", r"private account balance",
]
ALLOW={Path(__file__).name}

def scan():
    hits=[]
    for p in (ROOT/"src").rglob("*.py"):
        if p.name in ALLOW: continue
        text=p.read_text(errors="ignore")
        for pat in FORBIDDEN:
            if re.search(pat,text,re.I): hits.append({"file":str(p.relative_to(ROOT)),"pattern":pat})
    report={"trading_capability":"ZERO" if not hits else "FAIL","hits":hits}
    out=ROOT/"reports"; out.mkdir(exist_ok=True); (out/"SECURITY_SCAN.md").write_text("# Security Scan\n\nTRADING CAPABILITY = "+report["trading_capability"]+"\n\n"+json.dumps(hits,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    if hits: raise SystemExit(3)

if __name__=="__main__": scan()
