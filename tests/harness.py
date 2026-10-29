"""
Test harness: runs obms_explorer.py with small synthetic parquet files served
in place of Google Drive, so tests are fast, offline, and deterministic.

How: the app downloads with urllib.request.urlopen(). We replace that one
function with fake_urlopen() BEFORE executing the app — a technique called
monkeypatching. The app never knows the difference.
"""
import io, json, urllib.request
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent     # repo root (tests/ is one level down)
MAN = json.load(open(ROOT / "gdrive_manifest.json"))
ID2KEY = {v: k for k, v in MAN.items()}
DIMS = dict(Fund="11000 - Operational", Function="1000 - Instruction",
            Object="51100 - Salaries", Program="0000 - No Program",
            Location="000 - District", **{"Job Class": "0000 - No Job Class"})

def entities(fy):
    ents = ["Tularosa Municipal Schools", "Socorro Consolidated Schools"]
    if fy == "2526":
        ents.append("New Charter Academy")   # exists only in FY26
    return ents

def frame(key):
    kind, fy = key.split("_")
    rows = []
    for e in entities(fy):
        for acct in ("E", "R"):
            base = {"Budget Entity": e, **DIMS, "Account Type": acct}
            if kind == "budget":
                rows.append({**base, "Final Amt": 1000.0, "Final FTE": 1.0,
                             "Adjustment Amt": 0.0, "Adjustment FTE": 0.0,
                             "Adjusted Amt": 1000.0, "Adjusted FTE": 1.0})
            else:
                periods = ["Q03", "Q04"]
                if e == "Socorro Consolidated Schools":
                    periods = ["Q03"]           # never submitted Q04
                for p in periods:
                    rows.append({**base, "Location Type": "District",
                                 "Reporting Period": p,
                                 "Status": "Approved" if p == "Q03" else "Submitted",
                                 "Actuals Period Amount": 100.0,
                                 "Actuals YTDAmount": 1500.0 if acct == "E" else 500.0,
                                 "Actuals Encumbrance": 0.0, "Actuals FTE": 1.0})
    buf = io.BytesIO(); pd.DataFrame(rows).to_parquet(buf); return buf.getvalue()

class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass

def fake_urlopen(req, timeout=None):
    fid = req.full_url.split("id=")[-1]
    return _Resp(frame(ID2KEY[fid]))

urllib.request.urlopen = fake_urlopen
APP = ROOT / "obms_explorer.py"
exec(compile(APP.read_text(), str(APP), "exec"),
     {"__name__": "__main__", "__file__": str(APP)})
