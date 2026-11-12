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

# 5. PODhoc warns on empty actuals
at.radio(key="active_tab").set_value("PODhoc").run()
check(any("No actuals rows" in w.value for w in at.warning), "empty-actuals warning shown for Socorro Q04")
w = [w.value for w in at.warning if "No actuals rows" in w.value][0]
print("   ", w.split("Row counts: ")[1].split("\n")[0])
sb(at, "sb_entity").set_value("Tularosa Municipal Schools").run()
check(not any("No actuals rows" in w.value for w in at.warning), "no warning when actuals exist")
check(not at.exception, "PODhoc clean")

# 6. every tab renders
for tab in ["Overview","Budget Authority","Actuals","Salary & Benefits"]:
    at.radio(key="active_tab").set_value(tab).run()
    check(not at.exception, f"{tab} renders ({[str(e.value)[:80] for e in at.exception]})")


# ══ Phase 2: bookmarkable views, row order, tab persistence ══════════════════
print("\n── Phase 2 ──")

# 7. Opening a full report link lands on exactly that report
at = fresh(fy="2025", e="Tularosa Municipal Schools", p="Q03", s="Approved",
           tab="PODhoc", d="Object,Fund", m="YTD Actuals,Encumbrance",
           at="R", tot="1", f_Fund="11000 - Operational")
check(not at.exception, f"report link loads {[str(e.value)[:120] for e in at.exception]}")
check(at.sidebar.selectbox(key="sb_fy").value == 2025, "link: fiscal year")
check(sb(at, "sb_entity").value == "Tularosa Municipal Schools", "link: entity")
check(sb(at, "sb_period").value == "Q03", "link: period")
check(at.sidebar.radio(key="sb_status").value == "Approved", "link: status")
check(at.radio(key="active_tab").value == "PODhoc", "link: tab")
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
at.radio(key="active_tab").set_value("PODhoc").run()
check(at.multiselect(key="rb_dims").value == ["Fund"], "unknown dims dropped, valid kept")
check(at.multiselect(key="builder_Fund").value == [], "stale filter value dropped")
check(not at.exception, "PODhoc clean after bad link")

# 9. ◀ ▶ reorder
at = fresh(tab="PODhoc")
at.button(key="rb_right_0").click().run()
check(at.multiselect(key="rb_dims").value == ["Function", "Fund", "Object"], "▶ moves Fund later")
at.button(key="rb_left_2").click().run()
check(at.multiselect(key="rb_dims").value == ["Function", "Object", "Fund"], "◀ moves Object earlier")
check(qp(at, "d") == ["Function,Object,Fund"], "new order written to URL")
check(at.button(key="rb_left_0").disabled and at.button(key="rb_right_2").disabled,
      "end buttons disabled")

# 10. PODhoc settings survive a trip to another tab
at.multiselect(key="rb_measures").set_value(["YTD Actuals"]).run()
at.multiselect(key="builder_Fund").set_value(["11000 - Operational"]).run()
at.radio(key="active_tab").set_value("Overview").run()
check("d" not in at.query_params, "Overview URL omits report params")
at.radio(key="active_tab").set_value("PODhoc").run()
check(at.multiselect(key="rb_measures").value == ["YTD Actuals"], "measures kept across tabs")
check(at.multiselect(key="builder_Fund").value == ["11000 - Operational"], "filter kept across tabs")
check(at.multiselect(key="rb_dims").value == ["Function", "Object", "Fund"], "order kept across tabs")

# 11. Untouched period stays dynamic in the URL
at = fresh()
sb(at, "sb_entity").set_value("Tularosa Municipal Schools").run()
check(qp(at, "e") == ["Tularosa Municipal Schools"], "chosen entity written to URL")
check("p" not in at.query_params, "untouched period not frozen into URL")
check(not at.exception, "clean")


# ══ Phase 3: PODhoc rename, numeric sorting, drill-down ══════════════════════
print("\n── Phase 3 ──")
import pandas as pd

def tick(at, key, row=0):
    """Simulate ticking a row in a selectable st.dataframe. AppTest has no
    click-a-row method, so we write the same selection state the browser
    would send, then rerun."""
    at.session_state[key] = {"selection": {"rows": [row], "columns": [], "cells": []}}
    at.run(); return at

def table_with(at, col):
    """First on-screen table that has a column named `col`."""
    return next(d.value for d in at.dataframe if col in d.value.columns)

# 12. Tab is renamed, sits second, and old bookmarks still open it
at = fresh()
check(list(at.radio(key="active_tab").options)[:2] == ["Overview", "PODhoc"], "PODhoc is the second tab")
at = fresh(tab="Report Builder")
check(at.radio(key="active_tab").value == "PODhoc", "old ?tab=Report Builder bookmark opens PODhoc")

# 13. PODhoc's table holds numbers, not formatted text (so sorting is by value)
rpt = table_with(at, "YTD Actuals")
check(pd.api.types.is_numeric_dtype(rpt["YTD Actuals"]), "PODhoc YTD Actuals column is numeric")
check(pd.api.types.is_numeric_dtype(rpt["Burn % (Act + Enc)"]), "PODhoc Burn % column is numeric")
check(not at.exception, "PODhoc clean")

# 14. Entity export previews are numeric too
sb(at, "sb_entity").set_value("Tularosa Municipal Schools").run()
at.sidebar.selectbox(key="sb_fy").set_value(2026).run()
at.radio(key="active_tab").set_value("Actuals").run()
check(pd.api.types.is_numeric_dtype(table_with(at, "Actuals YTD")["Actuals YTD"]), "Actuals export preview is numeric")
at.radio(key="active_tab").set_value("Budget Authority").run()
check(pd.api.types.is_numeric_dtype(table_with(at, "Beginning Budget")["Beginning Budget"]), "Budget export preview is numeric")
check(not at.exception, "previews clean")

# 15. Overview: statewide By Budget Entity table → drill → hand-off to PODhoc
at = fresh(); at.sidebar.selectbox(key="sb_fy").set_value(2026).run()
ent = table_with(at, "% Spent")
check("Budget Entity" in ent.columns and len(ent) == 3, "Overview lists every entity statewide")
picked = ent.iloc[0]["Budget Entity"]
tick(at, "ov_entity_tbl")
check(any("Drill-down" in m.value and picked in m.value for m in at.markdown), "ticking a row opens the drill-down")
check(list(at.radio(key="ov_entity_drill_Budget Entity_by").options) == ["Fund", "Function", "Object"],
      "entity drill offers Fund / Function / Object")
at.button(key="ov_entity_drill_Budget Entity_open").click().run()
check(not at.exception, f"hand-off clean {[str(e.value)[:120] for e in at.exception]}")
check(at.radio(key="active_tab").value == "PODhoc", "hand-off lands on PODhoc")
check(sb(at, "sb_entity").value == picked, "hand-off scopes the sidebar to the entity")
check(at.multiselect(key="rb_dims").value == ["Fund", "Function", "Object"], "hand-off sets line-level rows")

# 16. Actuals: group by Budget Entity statewide; function drill carries its filter
at = fresh(); at.sidebar.selectbox(key="sb_fy").set_value(2026).run()
at.radio(key="active_tab").set_value("Actuals").run()
check("Budget Entity" in at.radio(key="act_spend_group").options, "Spend Distribution offers Budget Entity statewide")
at.radio(key="act_spend_group").set_value("Budget Entity").run()
check(not at.exception, "Spend Distribution by entity renders")
tick(at, "act_func_tbl")
check(list(at.radio(key="act_func_drill_Function_by").options)[0] == "Budget Entity", "function drill breaks down by entity first")
at.button(key="act_func_drill_Function_open").click().run()
check(at.radio(key="active_tab").value == "PODhoc", "function hand-off lands on PODhoc")
check(at.multiselect(key="builder_Function").value == ["1000 - Instruction"], "function filter carried into PODhoc")
check(at.multiselect(key="rb_dims").value[0] == "Budget Entity", "statewide hand-off adds Budget Entity as a row")
check(not at.exception, "clean after hand-off")

# 17. Picking an entity while grouped by Budget Entity falls back, no crash
at.radio(key="active_tab").set_value("Actuals").run()
at.radio(key="act_spend_group").set_value("Budget Entity").run()
sb(at, "sb_entity").set_value("Tularosa Municipal Schools").run()
check(not at.exception, f"entity pick with entity grouping doesn't crash {[str(e.value)[:120] for e in at.exception]}")
check(at.radio(key="act_spend_group").value == "Fund", "grouping falls back to Fund")

# 18. Negatives read -$1,234 (sign first), never $-1,234
ns = {}
src = (Path(__file__).resolve().parent.parent / "obms_explorer.py").read_text()
start = src.index("def fmt_currency"); end = src.index("def fmt_acct_currency")
exec("import pandas as pd\n" + src[start:end], ns)   # run just that one function
check(ns["fmt_currency"](-44_600_000_000, compact=True) == "-$44.6B", "compact negative is -$44.6B")
check(ns["fmt_currency"](-1234.4) == "-$1,234", "plain negative is -$1,234")
check(ns["fmt_currency"](1234.4) == "$1,234", "positive unchanged")

print("\nAll checks passed.")
