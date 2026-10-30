"""
Regression tests for OBMS Financial Explorer (Phase 1 + Phase 2).

Run from the repo root (venv active):   python tests/run_tests.py

AppTest drives the app headlessly: .set_value() is a click, .run() is the
rerun that follows. Each check() prints PASS/FAIL; any FAIL stops the run.
"""
from pathlib import Path
from streamlit.testing.v1 import AppTest

HARNESS = str(Path(__file__).resolve().parent / "harness.py")

def fresh(**url):
    """New browser session. Keyword args become the page's ?query=string,
    as if you'd opened a bookmark."""
    at = AppTest.from_file(HARNESS, default_timeout=60)
    for k, v in url.items():
        at.query_params[k] = v
    at.run(); return at

def sb(at, key): return at.sidebar.selectbox(key=key)

def qp(at, key):
    """URL param as a list. AppTest reports single values as ['x'] on
    Streamlit 1.63 and as 'x' on 1.66 — normalize so tests check meaning,
    not container type."""
    v = at.query_params.get(key)
    return None if v is None else (list(v) if isinstance(v, (list, tuple)) else [v])
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


# ══ Phase 2: bookmarkable views, row order, tab persistence ══════════════════
print("\n── Phase 2 ──")

# 7. Opening a full report link lands on exactly that report
at = fresh(fy="2025", e="Tularosa Municipal Schools", p="Q03", s="Approved",
           tab="Report Builder", d="Object,Fund", m="YTD Actuals,Encumbrance",
           at="R", tot="1", f_Fund="11000 - Operational")
check(not at.exception, f"report link loads {[str(e.value)[:120] for e in at.exception]}")
check(at.sidebar.selectbox(key="sb_fy").value == 2025, "link: fiscal year")
check(sb(at, "sb_entity").value == "Tularosa Municipal Schools", "link: entity")
check(sb(at, "sb_period").value == "Q03", "link: period")
check(at.sidebar.radio(key="sb_status").value == "Approved", "link: status")
check(at.radio(key="active_tab").value == "Report Builder", "link: tab")
check(at.multiselect(key="rb_dims").value == ["Object", "Fund"], "link: row dims + order")
check(at.multiselect(key="rb_measures").value == ["YTD Actuals", "Encumbrance"], "link: measures")
check(at.radio(key="builder_acct_type").value == "R", "link: account type")
check(at.checkbox(key="rb_totals").value is True, "link: totals row")
check(at.multiselect(key="builder_Fund").value == ["11000 - Operational"], "link: fund filter")
check(qp(at, "d") == ["Object,Fund"], "URL round-trips what it loaded")
link = at.code[0].value
check("e=Tularosa" in link and "f_Fund=11000" in link, "share link carries entity + filter")

# 8. A broken or stale link degrades to defaults instead of crashing
at = fresh(fy="1999", e="No Such School", d="Bogus,Fund", m="Nope",
           tab="Nope", f_Fund="99999 - Not A Fund", at="X")
check(not at.exception, f"bad link doesn't crash {[str(e.value)[:120] for e in at.exception]}")
check(sb(at, "sb_entity").value == "— All Entities —", "bad entity → All Entities")
check(at.radio(key="active_tab").value == "Overview", "bad tab → Overview")
at.radio(key="active_tab").set_value("Report Builder").run()
check(at.multiselect(key="rb_dims").value == ["Fund"], "unknown dims dropped, valid kept")
check(at.multiselect(key="builder_Fund").value == [], "stale filter value dropped")
check(not at.exception, "Report Builder clean after bad link")

# 9. ◀ ▶ reorder
at = fresh(tab="Report Builder")
at.button(key="rb_right_0").click().run()
check(at.multiselect(key="rb_dims").value == ["Function", "Fund", "Object"], "▶ moves Fund later")
at.button(key="rb_left_2").click().run()
check(at.multiselect(key="rb_dims").value == ["Function", "Object", "Fund"], "◀ moves Object earlier")
check(qp(at, "d") == ["Function,Object,Fund"], "new order written to URL")
check(at.button(key="rb_left_0").disabled and at.button(key="rb_right_2").disabled,
      "end buttons disabled")

# 10. Report Builder settings survive a trip to another tab
at.multiselect(key="rb_measures").set_value(["YTD Actuals"]).run()
at.multiselect(key="builder_Fund").set_value(["11000 - Operational"]).run()
at.radio(key="active_tab").set_value("Overview").run()
check("d" not in at.query_params, "Overview URL omits report params")
at.radio(key="active_tab").set_value("Report Builder").run()
check(at.multiselect(key="rb_measures").value == ["YTD Actuals"], "measures kept across tabs")
check(at.multiselect(key="builder_Fund").value == ["11000 - Operational"], "filter kept across tabs")
check(at.multiselect(key="rb_dims").value == ["Function", "Object", "Fund"], "order kept across tabs")

# 11. Untouched period stays dynamic in the URL
at = fresh()
sb(at, "sb_entity").set_value("Tularosa Municipal Schools").run()
check(qp(at, "e") == ["Tularosa Municipal Schools"], "chosen entity written to URL")
check("p" not in at.query_params, "untouched period not frozen into URL")
check(not at.exception, "clean")
