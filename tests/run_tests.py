"""
Phase 1 regression tests for OBMS Financial Explorer.

Run from the repo root (venv active):   python tests/run_tests.py

AppTest drives the app headlessly: .set_value() is a click, .run() is the
rerun that follows. Each check() prints PASS/FAIL; any FAIL stops the run.
"""
from pathlib import Path
from streamlit.testing.v1 import AppTest

HARNESS = str(Path(__file__).resolve().parent / "harness.py")

def fresh():
    at = AppTest.from_file(HARNESS, default_timeout=60); at.run(); return at

def sb(at, key): return at.sidebar.selectbox(key=key)
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg); assert cond, msg

at = fresh()
check(not at.exception, f"app loads without exceptions {[e.value for e in at.exception]}")
fy = at.sidebar.selectbox[0]
fy.set_value(2026).run()
check(sb(at, "sb_period").value == "Q04", "period defaults to latest (Q04)")

# 1. entity sticks across FY change
sb(at, "sb_entity").set_value("Tularosa Municipal Schools").run()
sb(at, "sb_period").set_value("Q03").run()
at.sidebar.selectbox[0].set_value(2025).run()
check(sb(at, "sb_entity").value == "Tularosa Municipal Schools", "entity kept FY26 → FY25")
check(sb(at, "sb_period").value == "Q03", "chosen period kept FY26 → FY25")

# 2. entity missing in a year → fallback + toast, and comes back
at.sidebar.selectbox[0].set_value(2026).run()
sb(at, "sb_entity").set_value("New Charter Academy").run()
at.sidebar.selectbox[0].set_value(2025).run()
check(sb(at, "sb_entity").value == "— All Entities —", "missing entity falls back to All in FY25")
check(any("isn't in this fiscal year" in t.value for t in at.toast), "toast explains the fallback")
at.sidebar.selectbox[0].set_value(2026).run()
check(sb(at, "sb_entity").value == "New Charter Academy", "preference restored on return to FY26")
check(not at.exception, "no exceptions through FY switching")

# 3. status sticks
at.sidebar.radio(key="sb_status").set_value("Approved").run()
at.sidebar.selectbox[0].set_value(2025).run()
check(at.sidebar.radio(key="sb_status").value == "Approved", "status kept across FY")

# 4. Exceptions respects entity
at = fresh(); at.sidebar.selectbox[0].set_value(2026).run()
at.radio(key="active_tab").set_value("Exceptions").run()
state_missing = at.metric[3].value
sb(at, "sb_entity").set_value("Tularosa Municipal Schools").run()
check(not at.exception, "Exceptions renders scoped")
check(at.metric[3].value == "0", f"Tularosa scope: missing actuals 0 (statewide was {state_missing})")
sb(at, "sb_entity").set_value("Socorro Consolidated Schools").run()
check(at.metric[3].value == "1", "Socorro scope: flagged missing Q04 actuals")
check(any("Hide reimbursable" in c.label for c in at.checkbox), "reimbursable toggle present")

# 5. Report Builder warns on empty actuals
at.radio(key="active_tab").set_value("Report Builder").run()
check(any("No actuals rows" in w.value for w in at.warning), "empty-actuals warning shown for Socorro Q04")
w = [w.value for w in at.warning if "No actuals rows" in w.value][0]
print("   ", w.split("Row counts: ")[1].split("\n")[0])
sb(at, "sb_entity").set_value("Tularosa Municipal Schools").run()
check(not any("No actuals rows" in w.value for w in at.warning), "no warning when actuals exist")
check(not at.exception, "Report Builder clean")

# 6. every tab renders
for tab in ["Overview","Budget Authority","Actuals","Salary & Benefits"]:
    at.radio(key="active_tab").set_value(tab).run()
    check(not at.exception, f"{tab} renders ({[str(e.value)[:80] for e in at.exception]})")
