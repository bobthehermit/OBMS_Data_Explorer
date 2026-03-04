"""
OBMS Financial Explorer
A Streamlit-based Power BI alternative for NM PED School Budget Bureau
Reads parquet files from Google Drive (extracted from OBMS SSAS cubes via XMLA)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from io import BytesIO
from datetime import datetime
import json

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OBMS Financial Explorer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom Theme ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg-primary: #0f1117;
    --bg-card: #1a1d2e;
    --bg-card-hover: #222640;
    --accent-blue: #4f8df5;
    --accent-teal: #2dd4bf;
    --accent-amber: #f59e0b;
    --accent-rose: #f43f5e;
    --accent-violet: #8b5cf6;
    --text-primary: #e8eaed;
    --text-secondary: #9ca3af;
    --border-subtle: #2a2d3e;
}

/* Global font */
html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif !important;
}

/* Metric cards */
div[data-testid="stMetric"] {
    background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-card-hover) 100%);
    border: 1px solid var(--border-subtle);
    border-radius: 12px;
    padding: 16px 20px;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
div[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(79, 141, 245, 0.15);
}
div[data-testid="stMetric"] label {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500;
    font-size: 0.8rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--text-secondary) !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 500;
    font-size: 1.6rem;
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background: #0d0f18;
    border-right: 1px solid var(--border-subtle);
}
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stMultiSelect label,
section[data-testid="stSidebar"] .stRadio label {
    font-weight: 500;
    font-size: 0.82rem;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: var(--text-secondary) !important;
}

/* Tab styling */
button[data-baseweb="tab"] {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600;
    font-size: 0.9rem;
    letter-spacing: 0.02em;
}

/* Dataframe styling */
div[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
}

/* Download buttons */
.stDownloadButton > button {
    background: linear-gradient(135deg, var(--accent-blue), var(--accent-violet)) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    padding: 8px 20px !important;
    transition: opacity 0.2s ease !important;
}
.stDownloadButton > button:hover {
    opacity: 0.85 !important;
}

/* Section headers */
.section-header {
    font-family: 'DM Sans', sans-serif;
    font-weight: 700;
    font-size: 1.1rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 1.5rem 0 0.8rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 2px solid var(--accent-blue);
    display: inline-block;
}

/* Logo / Title area */
.app-title {
    font-family: 'DM Sans', sans-serif;
    font-weight: 700;
    font-size: 1.6rem;
    background: linear-gradient(135deg, #4f8df5, #2dd4bf);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0;
    line-height: 1.2;
}
.app-subtitle {
    font-family: 'DM Sans', sans-serif;
    font-size: 0.78rem;
    color: var(--text-secondary);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-top: 2px;
}

/* Expander */
details {
    border: 1px solid var(--border-subtle) !important;
    border-radius: 10px !important;
    background: var(--bg-card) !important;
}
</style>
""", unsafe_allow_html=True)


# ── Plotly Theme ─────────────────────────────────────────────────────────────
PLOTLY_TEMPLATE = dict(
    layout=go.Layout(
        font=dict(family="DM Sans, sans-serif", color="#e8eaed"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=["#4f8df5", "#2dd4bf", "#f59e0b", "#f43f5e", "#8b5cf6",
                   "#06b6d4", "#84cc16", "#ec4899", "#f97316", "#6366f1"],
        xaxis=dict(gridcolor="#1e2130", zerolinecolor="#2a2d3e"),
        yaxis=dict(gridcolor="#1e2130", zerolinecolor="#2a2d3e"),
        margin=dict(l=40, r=20, t=50, b=40),
        hoverlabel=dict(
            bgcolor="#1a1d2e",
            bordercolor="#4f8df5",
            font=dict(family="DM Sans", color="#e8eaed", size=13)
        ),
    )
)


# ── Fund Classification ─────────────────────────────────────────────────────
# Used for Section 5: classifying funds as reimbursable vs non-reimbursable
# when expenditures exceed revenue.
#
# Non-Reimbursable: local/operational funds where spending > revenue is a real
# cash concern. Reimbursable: federal/state flow-through grants where spending
# typically precedes reimbursement.
#
# Classification is by leading digits of the fund code. Order matters —
# first match wins.

FUND_CLASSIFICATION = {
    # Non-Reimbursable (real cash concerns)
    "11": "Non-Reimbursable",   # Operational
    "13": "Non-Reimbursable",   # Transportation
    "14": "Non-Reimbursable",   # Instructional Materials
    "21": "Non-Reimbursable",   # Food Services (local revenue-backed)
    "23": "Non-Reimbursable",   # Non-Instructional Support
    "31": "Non-Reimbursable",   # Debt Service (Bond)
    "32": "Non-Reimbursable",   # Debt Service (other)
    "41": "Non-Reimbursable",   # Capital Improvements HB-33
    "42": "Non-Reimbursable",   # Capital Improvements SB-9
    "43": "Non-Reimbursable",   # Capital (other local)

    # Reimbursable (expected: spend first, reimbursed later)
    "24": "Reimbursable",       # Federal Flow-Through (IDEA-B, Title I, etc.)
    "25": "Reimbursable",       # State Flow-Through
    "26": "Reimbursable",       # Federal Direct Grants
    "27": "Reimbursable",       # State Direct Appropriations
    "28": "Reimbursable",       # Federal Stimulus (ESSER, etc.)
    "29": "Reimbursable",       # State/Other Grants
}


def classify_fund(fund_str):
    """Classify a fund string like '11000 - Operational' as Reimbursable or Non-Reimbursable."""
    code = extract_code(str(fund_str))
    for prefix, classification in FUND_CLASSIFICATION.items():
        if code.startswith(prefix):
            return classification
    return "Other"


# ── Google Drive File Registry ───────────────────────────────────────────────
GDRIVE_FILES = {
    # Actuals
    "actuals_0607": "1gNXoqsb7KlULD0o35olSqKYxkzBpIvmY",
    "actuals_0708": "1SxAfJz9AXYSM6sTf8ZjeakpQaec7XFX8",
    "actuals_0809": "1S8tMk-r_nIpHqZ41E_pUZmTj1xyQE55M",
    "actuals_0910": "1DFU-CyIzwfJqFCagCt_G9oCq-5y7_js7",
    "actuals_1011": "1rDVMe6mHxZxeQENuAU0THVNFNN0vHbvs",
    "actuals_1112": "1XjdSjYBCM1Cd4oNM06MWnvZFNag0PUTJ",
    "actuals_1213": "1oxA9smmcVwxcGOnCVQhGqafGICKmmvG7",
    "actuals_1314": "1LLbzXHT6vEhTy6SYey4-NjZv1rvdr4qX",
    "actuals_1415": "1-QsCBf3IuD_hARAJ-Eq7HoOtlYFW9DbP",
    "actuals_1516": "1hFxsHvrF869J4XANT9uv1PRvUaMmyHvg",
    "actuals_1617": "1eYedwlnb1Y1-M1FIluAmf00wXkAZwghi",
    "actuals_1718": "1mLpCNiadwhFV8V1P_pBfl8TapO6oFpyA",
    "actuals_1819": "18pgtuw2TktHnvkpBHtDGWidiwJ3xlzyU",
    "actuals_1920": "1k0kH1Dw822-RgcqizyLdt2IM9aVm6tP0",
    "actuals_2021": "1civ3AJzXHOTEENKeHZ1c5fPtFUw8Bns4",
    "actuals_2122": "1ECBJmrWsftyJtgV3l_mA7Ktc71orEBRT",
    "actuals_2223": "19tdwjO4hEBo2MLuKCdiTxNMqKd2HOeW5",
    "actuals_2324": "1E0Q_zUaAO2o5F9sv-yNT1yd1d8XHHE7I",
    "actuals_2425": "1fd3Y7uhKBLcu9tMUYt5OjYK_uowKSoCr",
    "actuals_2526": "1A2bNEe8Qa0ZDplVJ0czpjfjjTDK9Dso6",
    # Budget
    "budget_0607": "1nY-wIi0O7qTo2Ulv2UUmC2A8S_Wki-_i",
    "budget_0708": "1lVim1I0KWgNVKmDL3qCvxKloqGX95uwF",
    "budget_0809": "1iJwpXzgTQApcPyH3-25frQsigs5CI1DZ",
    "budget_0910": "13xxR2b9wNT2LMUvApFv3meTYFNbplI7b",
    "budget_1011": "1Uneov8tf-TjCTWDK3SZYZ_KOCuSA26TI",
    "budget_1112": "1NhLH8AHKalV-d7nhMM4E5nPs9AxmYXVc",
    "budget_1213": "1z5UtAW8DANylJDVjpiqRHtcYQXT2yYbQ",
    "budget_1314": "1CVYXkieBfxM6HXTXqvbl4YgC-0MgqXNO",
    "budget_1415": "1EnzIrebjSWd5vlguwK2Pu4Pbr_t8dcE2",
    "budget_1516": "1TKlP3NOpYNiOlXSAMWYTekU5x3yfqaas",
    "budget_1617": "1N3LEQ1qmmkIBxaJhVdnm6uq6aiiYuNEJ",
    "budget_1718": "1O0otS5iH2Y95o8u8c6jyKAlDyvfVK9dS",
    "budget_1819": "1jpcVcn7ZyTipVzCdjjn1pTFK14cmSHN3",
    "budget_1920": "1tpangmkR7gStakQTvP0eb9AfMsBikLaY",
    "budget_2021": "1smwBtwXT9DBlYYMfJJI_OQhMVGaQ46ez",
    "budget_2122": "1uUzPwwXfRpkPvMW3Hay4HJfY-E0S77JW",
    "budget_2223": "1qtkggg24QNGGu8v2BDWiPD72lavyKL5l",
    "budget_2324": "1Kege6aBjkvOtc6UuIxLcWExB7Lg-pUEZ",
    "budget_2425": "14WGpeN5yxosM3uK-23nS9VPvRfkvKvbC",
    "budget_2526": "1VbV8Ynyr41kSz3wJvuN4FZR2u5DW9SNB",
}


def gdrive_download_url(file_id: str) -> str:
    """Convert a Google Drive file ID to a direct download URL."""
    return f"https://drive.google.com/uc?export=download&id={file_id}"


# ── Fiscal Year Helpers ──────────────────────────────────────────────────────
ALL_FY_CODES = sorted(set(
    k.split("_")[1] for k in GDRIVE_FILES.keys()
))

def fy_key_to_code(fy_key: int) -> str:
    """Convert FiscalYearKey like 2025 to FY code like '2425'."""
    return f"{(fy_key-1) % 100:02d}{fy_key % 100:02d}"

def fy_code_to_key(fy_code: str) -> int:
    """Convert FY code like '2425' to FiscalYearKey like 2025."""
    return 2000 + int(fy_code[2:4])

ALL_FY_KEYS = sorted([fy_code_to_key(c) for c in ALL_FY_CODES])
DIM_FISCAL = pd.DataFrame([{
    "FiscalYearKey": k,
    "FiscalYear": fy_key_to_code(k),
    "FiscalYearLabel": f"{k-1}–{k}"
} for k in ALL_FY_KEYS])


@st.cache_data(ttl=3600)
def load_single_parquet(file_key: str) -> pd.DataFrame:
    """Load a single parquet file from Google Drive. Cached per file."""
    file_id = GDRIVE_FILES.get(file_key)
    if not file_id:
        return pd.DataFrame()
    try:
        return pd.read_parquet(gdrive_download_url(file_id))
    except Exception as e:
        st.warning(f"Failed to load {file_key}: {e}")
        return pd.DataFrame()


def load_data_for_years(fy_keys: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load actuals and budget data only for the selected fiscal years."""
    actuals_dfs = []
    budget_dfs = []

    fy_codes = [fy_key_to_code(k) for k in fy_keys]
    files_to_load = [f"{t}_{c}" for c in fy_codes for t in ["actuals", "budget"]
                     if f"{t}_{c}" in GDRIVE_FILES]

    if not files_to_load:
        return pd.DataFrame(), pd.DataFrame()

    progress = st.progress(0, text="Loading data...")
    for i, key in enumerate(files_to_load):
        progress.progress((i + 1) / len(files_to_load), text=f"Loading {key}.parquet...")
        df = load_single_parquet(key)
        if len(df) > 0:
            if key.startswith("actuals_"):
                actuals_dfs.append(df)
            else:
                budget_dfs.append(df)
    progress.empty()

    act = pd.concat(actuals_dfs, ignore_index=True) if actuals_dfs else pd.DataFrame()
    bud = pd.concat(budget_dfs, ignore_index=True) if budget_dfs else pd.DataFrame()
    return act, bud


# ── Helper Functions ─────────────────────────────────────────────────────────
def fmt_currency(val, compact=False):
    """Format a number as currency."""
    if pd.isna(val):
        return "$0"
    if compact:
        if abs(val) >= 1_000_000_000:
            return f"${val/1_000_000_000:,.1f}B"
        if abs(val) >= 1_000_000:
            return f"${val/1_000_000:,.1f}M"
        if abs(val) >= 1_000:
            return f"${val/1_000:,.0f}K"
    return f"${val:,.0f}"


def fmt_pct(val):
    if pd.isna(val) or val == float('inf') or val == float('-inf'):
        return "N/A"
    return f"{val:.1f}%"


def extract_code(text):
    """Extract leading numeric code from strings like '11000 - Operational'."""
    if pd.isna(text):
        return ""
    parts = str(text).split(" - ", 1)
    return parts[0].strip()


def extract_name(text):
    """Extract name portion from strings like '11000 - Operational'."""
    if pd.isna(text):
        return ""
    parts = str(text).split(" - ", 1)
    return parts[1].strip() if len(parts) > 1 else parts[0].strip()


def to_excel_download(df, sheet_name="Data"):
    """Convert DataFrame to downloadable Excel bytes."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()


def apply_filters(act, bud, account_type, period, entities, funds, functions, objects, programs):
    """Apply user-selected filters to both fact tables."""
    a = act
    if account_type:
        a = a[a["Account Type"] == account_type]
    if period:
        a = a[a["Reporting Period"] == period]
    if entities:
        a = a[a["Budget Entity"].isin(entities)]
    if funds:
        a = a[a["Fund"].isin(funds)]
    if functions:
        a = a[a["Function"].isin(functions)]
    if objects:
        a = a[a["Object"].isin(objects)]
    if programs:
        a = a[a["Program"].isin(programs)]

    b = bud
    if account_type:
        b = b[b["Account Type"] == account_type]
    if entities:
        b = b[b["Budget Entity"].isin(entities)]
    if funds:
        b = b[b["Fund"].isin(funds)]
    if functions:
        b = b[b["Function"].isin(functions)]
    if objects:
        b = b[b["Object"].isin(objects)]
    if programs:
        b = b[b["Program"].isin(programs)]

    return a, b


def compute_budget_vs_actuals(act_filtered, bud_filtered, group_col):
    """Compute budget vs actuals comparison grouped by a dimension."""
    b_agg = bud_filtered.groupby(group_col).agg(
        Adjusted_Budget=("Adjusted Amt", "sum"),
        Final_Budget=("Final Amt", "sum"),
        Budget_FTE=("Final FTE", "sum")
    ).reset_index()

    a_agg = act_filtered.groupby(group_col).agg(
        YTD_Actuals=("Actuals YTDAmount", "sum"),
        Period_Actuals=("Actuals Period Amount", "sum"),
        Encumbrance=("Actuals Encumbrance", "sum"),
        Actuals_FTE=("Actuals FTE", "sum")
    ).reset_index()

    merged = b_agg.merge(a_agg, on=group_col, how="outer").fillna(0)
    merged["Budget_Balance"] = merged["Adjusted_Budget"] - merged["YTD_Actuals"] - merged["Encumbrance"]
    merged["Pct_Spent"] = (merged["YTD_Actuals"] / merged["Adjusted_Budget"].replace(0, float("nan")) * 100)
    merged["Pct_Committed"] = ((merged["YTD_Actuals"] + merged["Encumbrance"]) /
                                merged["Adjusted_Budget"].replace(0, float("nan")) * 100)

    return merged.sort_values("Adjusted_Budget", ascending=False)


# ── District Report Helpers ──────────────────────────────────────────────────
REPORT_DIMS = ["Budget Entity", "Fund", "Function", "Object", "Program", "Job Class"]

REPORT_CSV_COLS = [
    "Entity", "Fund", "Function", "Object", "Program", "JobClass",
    "Actuals Period Amount", "Actuals YTD", "Encumbrance", "Actuals FTE",
    "Adjusted Budget", "Adjusted FTE", "Available Balance", "Burn % (Actuals + Enc)"
]


def _fmt_acct_currency(val):
    if pd.isna(val):
        return ""
    if val < 0:
        return f"(${abs(val):,.2f})"
    return f"${val:,.2f}"


def _fmt_acct_pct(val):
    if pd.isna(val):
        return ""
    return f"{val:.2f}%"


def build_district_report(act_df, bud_df, entity_name, account_type):
    """Build a line-item report for a single entity matching quarterly review CSV format."""
    act = act_df[
        (act_df["Budget Entity"] == entity_name) &
        (act_df["Account Type"] == account_type)
    ].copy()

    bud = bud_df[
        (bud_df["Budget Entity"] == entity_name) &
        (bud_df["Account Type"] == account_type)
    ].copy()

    if len(act) == 0 and len(bud) == 0:
        return pd.DataFrame(columns=REPORT_CSV_COLS)

    if len(act) > 0:
        a_agg = act.groupby(REPORT_DIMS, dropna=False).agg(
            period_amt=("Actuals Period Amount", "sum"),
            ytd_amt=("Actuals YTDAmount", "sum"),
            enc_amt=("Actuals Encumbrance", "sum"),
            act_fte=("Actuals FTE", "sum"),
        ).reset_index()
    else:
        a_agg = pd.DataFrame(columns=REPORT_DIMS + ["period_amt", "ytd_amt", "enc_amt", "act_fte"])

    if len(bud) > 0:
        b_agg = bud.groupby(REPORT_DIMS, dropna=False).agg(
            adj_budget=("Adjusted Amt", "sum"),
            adj_fte=("Final FTE", "sum"),
        ).reset_index()
    else:
        b_agg = pd.DataFrame(columns=REPORT_DIMS + ["adj_budget", "adj_fte"])

    merged = b_agg.merge(a_agg, on=REPORT_DIMS, how="outer")

    merged["avail_balance"] = (
        merged["adj_budget"].fillna(0)
        - merged["ytd_amt"].fillna(0)
        - merged["enc_amt"].fillna(0)
    )

    has_actuals = merged["ytd_amt"].notna() | merged["enc_amt"].notna()
    has_budget = merged["adj_budget"].notna() & (merged["adj_budget"] != 0)
    merged["burn_pct"] = pd.NA
    mask = has_actuals & has_budget
    merged.loc[mask, "burn_pct"] = (
        (merged.loc[mask, "ytd_amt"].fillna(0) + merged.loc[mask, "enc_amt"].fillna(0))
        / merged.loc[mask, "adj_budget"]
        * 100
    )

    merged = merged.sort_values(REPORT_DIMS).reset_index(drop=True)

    actuals_present = merged["ytd_amt"].notna() | merged["enc_amt"].notna()
    budget_present = merged["adj_budget"].notna()

    report = pd.DataFrame()
    report["Entity"] = merged["Budget Entity"]
    report["Fund"] = merged["Fund"]
    report["Function"] = merged["Function"]
    report["Object"] = merged["Object"]
    report["Program"] = merged["Program"]
    report["JobClass"] = merged["Job Class"]

    report["Actuals Period Amount"] = merged["period_amt"].apply(
        lambda v: _fmt_acct_currency(v) if pd.notna(v) and v != 0 else ("" if pd.isna(v) else _fmt_acct_currency(v))
    )
    report["Actuals YTD"] = merged["ytd_amt"].apply(
        lambda v: _fmt_acct_currency(v) if pd.notna(v) and v != 0 else ("" if pd.isna(v) else _fmt_acct_currency(v))
    )
    report["Encumbrance"] = merged["enc_amt"].apply(
        lambda v: _fmt_acct_currency(v) if pd.notna(v) and v != 0 else ("" if pd.isna(v) else _fmt_acct_currency(v))
    )
    report["Actuals FTE"] = merged["act_fte"].apply(
        lambda v: "" if pd.isna(v) else f"{v:.2f}" if v != 0 else "0.00"
    )

    report["Adjusted Budget"] = merged["adj_budget"].apply(
        lambda v: _fmt_acct_currency(v) if pd.notna(v) else ""
    )
    report["Adjusted FTE"] = merged["adj_fte"].apply(
        lambda v: "" if pd.isna(v) else f"{v:.2f}" if v != 0 else "0.00"
    )

    report["Available Balance"] = merged["avail_balance"].apply(_fmt_acct_currency)
    report["Burn % (Actuals + Enc)"] = merged["burn_pct"].apply(_fmt_acct_pct)

    budget_only_mask = ~actuals_present
    for col in ["Actuals Period Amount", "Actuals YTD", "Encumbrance", "Actuals FTE"]:
        report.loc[budget_only_mask, col] = ""

    actuals_only_mask = ~budget_present
    for col in ["Adjusted Budget", "Adjusted FTE"]:
        report.loc[actuals_only_mask, col] = ""

    return report


# ══════════════════════════════════════════════════════════════════════════════
# Entity Analysis Functions (Sections 4–7)
# ══════════════════════════════════════════════════════════════════════════════

def compute_entity_rev_vs_exp(act_df, bud_df, entity_name):
    """
    Section 4: Revenue vs Expenditure by Fund.
    Returns a DataFrame with fund-level revenue and expenditure YTD totals.
    """
    # Revenue actuals for entity
    rev_act = act_df[
        (act_df["Budget Entity"] == entity_name) &
        (act_df["Account Type"] == "R")
    ].groupby("Fund").agg(Revenue_YTD=("Actuals YTDAmount", "sum")).reset_index()

    # Expenditure actuals for entity
    exp_act = act_df[
        (act_df["Budget Entity"] == entity_name) &
        (act_df["Account Type"] == "E")
    ].groupby("Fund").agg(Expenditure_YTD=("Actuals YTDAmount", "sum")).reset_index()

    merged = rev_act.merge(exp_act, on="Fund", how="outer").fillna(0)
    merged["Net"] = merged["Revenue_YTD"] - merged["Expenditure_YTD"]
    merged["Total_Activity"] = merged["Revenue_YTD"].abs() + merged["Expenditure_YTD"].abs()
    merged["Fund_Name"] = merged["Fund"].apply(extract_name)
    merged["Fund_Code"] = merged["Fund"].apply(extract_code)
    merged["Fund_Class"] = merged["Fund"].apply(classify_fund)

    return merged.sort_values("Total_Activity", ascending=False)


def compute_funds_exp_exceed_rev(rev_exp_df):
    """
    Section 5: Funds where expenditures exceed revenue.
    Split into Non-Reimbursable (real concern) and Reimbursable (expected).
    """
    deficit = rev_exp_df[rev_exp_df["Net"] < 0].copy()
    deficit["Deficit"] = deficit["Net"].abs()

    non_reimb = deficit[deficit["Fund_Class"] == "Non-Reimbursable"].sort_values("Deficit", ascending=False)
    reimb = deficit[deficit["Fund_Class"] == "Reimbursable"].sort_values("Deficit", ascending=False)
    other = deficit[deficit["Fund_Class"] == "Other"].sort_values("Deficit", ascending=False)

    return non_reimb, reimb, other


def compute_exp_by_fund_type(act_df, entity_name):
    """
    Section 6: Expenditure distribution by fund.
    Returns fund-level YTD expenditure totals for donut chart + table.
    """
    exp = act_df[
        (act_df["Budget Entity"] == entity_name) &
        (act_df["Account Type"] == "E")
    ].groupby("Fund").agg(
        YTD_Actuals=("Actuals YTDAmount", "sum")
    ).reset_index()

    exp["Fund_Name"] = exp["Fund"].apply(extract_name)
    exp["Fund_Code"] = exp["Fund"].apply(extract_code)
    exp["Fund_Class"] = exp["Fund"].apply(classify_fund)
    total = exp["YTD_Actuals"].sum()
    exp["Pct_of_Total"] = (exp["YTD_Actuals"] / total * 100) if total > 0 else 0

    return exp.sort_values("YTD_Actuals", ascending=False)


def compute_exp_by_function(act_df, bud_df, entity_name):
    """
    Section 7: Expenditure by function with budget/actuals/encumbrance.
    Returns function-level comparison for horizontal bar + table.
    """
    exp_act = act_df[
        (act_df["Budget Entity"] == entity_name) &
        (act_df["Account Type"] == "E")
    ].groupby("Function").agg(
        YTD_Actuals=("Actuals YTDAmount", "sum"),
        Encumbrance=("Actuals Encumbrance", "sum"),
    ).reset_index()

    exp_bud = bud_df[
        (bud_df["Budget Entity"] == entity_name) &
        (bud_df["Account Type"] == "E")
    ].groupby("Function").agg(
        Adjusted_Budget=("Adjusted Amt", "sum"),
    ).reset_index()

    merged = exp_bud.merge(exp_act, on="Function", how="outer").fillna(0)
    merged["Available"] = merged["Adjusted_Budget"] - merged["YTD_Actuals"] - merged["Encumbrance"]
    merged["Pct_Used"] = (
        (merged["YTD_Actuals"] + merged["Encumbrance"])
        / merged["Adjusted_Budget"].replace(0, float("nan"))
        * 100
    )
    merged["Function_Name"] = merged["Function"].apply(extract_name)
    merged["Function_Code"] = merged["Function"].apply(extract_code)

    return merged.sort_values("Adjusted_Budget", ascending=False)


# ══════════════════════════════════════════════════════════════════════════════
# HTML Export Builder
# ══════════════════════════════════════════════════════════════════════════════

def build_html_report(entity_name, fy_label, period_label, rev_exp_df,
                      non_reimb_df, reimb_df, other_df,
                      fund_dist_df, func_df, summary_stats):
    """
    Generate a standalone HTML report in the cream/Playfair Display style
    matching the quarterly review format. Includes Chart.js charts.
    """
    # Prepare chart data
    # Section 4: Rev vs Exp bar chart — top 12 funds
    top_funds_chart = rev_exp_df.head(12)
    chart_labels = [extract_name(f) for f in top_funds_chart["Fund"]]
    chart_rev = top_funds_chart["Revenue_YTD"].tolist()
    chart_exp = top_funds_chart["Expenditure_YTD"].tolist()

    # Section 6: Donut chart — fund distribution
    fund_donut = fund_dist_df[fund_dist_df["YTD_Actuals"] > 0].head(10)
    donut_labels = fund_donut["Fund_Name"].tolist()
    donut_values = fund_donut["YTD_Actuals"].tolist()

    # Section 7: Function bar chart
    func_chart = func_df[func_df["Adjusted_Budget"] > 0].head(12)
    func_labels = func_chart["Function_Name"].tolist()
    func_actuals = func_chart["YTD_Actuals"].tolist()
    func_enc = func_chart["Encumbrance"].tolist()
    func_avail = func_chart["Available"].clip(lower=0).tolist()

    # Build deficit fund tables
    def _fund_deficit_rows(df):
        rows = ""
        for _, r in df.iterrows():
            status_color = "#b91c1c" if r["Deficit"] > 100_000 else "#d97706" if r["Deficit"] > 10_000 else "#65a30d"
            rows += f"""<tr>
                <td>{r['Fund']}</td>
                <td style="text-align:right">${r['Revenue_YTD']:,.0f}</td>
                <td style="text-align:right">${r['Expenditure_YTD']:,.0f}</td>
                <td style="text-align:right;color:{status_color};font-weight:600">({_fmt_acct_currency(r['Deficit'])})</td>
                <td><span style="background:{status_color};color:white;padding:2px 10px;border-radius:12px;font-size:0.8rem;">
                    {'High' if r['Deficit'] > 100_000 else 'Monitor' if r['Deficit'] > 10_000 else 'Low'}</span></td>
            </tr>"""
        return rows

    # Build function table
    func_table_rows = ""
    for _, r in func_df.iterrows():
        if r["Adjusted_Budget"] == 0 and r["YTD_Actuals"] == 0:
            continue
        pct_str = f"{r['Pct_Used']:.1f}%" if pd.notna(r["Pct_Used"]) else "N/A"
        pct_color = "#b91c1c" if pd.notna(r["Pct_Used"]) and r["Pct_Used"] > 90 else "#d97706" if pd.notna(r["Pct_Used"]) and r["Pct_Used"] > 70 else "#1e3a5f"
        func_table_rows += f"""<tr>
            <td>{r['Function']}</td>
            <td style="text-align:right">${r['Adjusted_Budget']:,.0f}</td>
            <td style="text-align:right">${r['YTD_Actuals']:,.0f}</td>
            <td style="text-align:right">${r['Encumbrance']:,.0f}</td>
            <td style="text-align:right">${r['Available']:,.0f}</td>
            <td style="text-align:right;color:{pct_color};font-weight:600">{pct_str}</td>
        </tr>"""

    # Fund distribution table
    fund_table_rows = ""
    for _, r in fund_dist_df.head(10).iterrows():
        fund_table_rows += f"""<tr>
            <td>{r['Fund']}</td>
            <td style="text-align:right">${r['YTD_Actuals']:,.0f}</td>
            <td style="text-align:right">{r['Pct_of_Total']:.1f}%</td>
        </tr>"""

    review_date = datetime.now().strftime("%B %d, %Y")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{entity_name} — {fy_label} Actuals Analysis</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=Source+Sans+3:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0"></script>
<style>
    :root {{
        --navy: #1e3a5f;
        --gold: #c9a96e;
        --red: #b91c1c;
        --amber: #d97706;
        --green: #65a30d;
        --cream: #faf9f7;
        --card-bg: #ffffff;
        --text: #2d3748;
        --text-light: #718096;
        --border: #e8e4df;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: 'Source Sans 3', sans-serif;
        background: var(--cream);
        color: var(--text);
        line-height: 1.6;
        padding: 40px;
    }}
    .header {{
        text-align: center;
        margin-bottom: 40px;
        padding-bottom: 24px;
        border-bottom: 3px solid var(--navy);
    }}
    .header h1 {{
        font-family: 'Playfair Display', serif;
        font-size: 2rem;
        color: var(--navy);
        margin-bottom: 4px;
    }}
    .header h2 {{
        font-family: 'Playfair Display', serif;
        font-size: 1.2rem;
        color: var(--gold);
        font-weight: 400;
        margin-bottom: 8px;
    }}
    .header .meta {{
        font-size: 0.9rem;
        color: var(--text-light);
    }}
    .section {{
        margin-bottom: 36px;
    }}
    .section h3 {{
        font-family: 'Playfair Display', serif;
        font-size: 1.3rem;
        color: var(--navy);
        margin-bottom: 16px;
        padding-bottom: 6px;
        border-bottom: 2px solid var(--gold);
        display: inline-block;
    }}
    .cards {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin-bottom: 24px;
    }}
    .card {{
        background: var(--card-bg);
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        border-left: 4px solid var(--navy);
    }}
    .card .label {{
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--text-light);
        margin-bottom: 4px;
    }}
    .card .value {{
        font-size: 1.6rem;
        font-weight: 700;
        color: var(--navy);
    }}
    .card.accent-gold {{ border-left-color: var(--gold); }}
    .card.accent-red {{ border-left-color: var(--red); }}
    .card.accent-green {{ border-left-color: var(--green); }}
    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.9rem;
        background: var(--card-bg);
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }}
    th {{
        background: var(--navy);
        color: white;
        padding: 10px 14px;
        text-align: left;
        font-weight: 600;
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}
    td {{
        padding: 8px 14px;
        border-bottom: 1px solid var(--border);
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover {{ background: #f7f5f2; }}
    .chart-container {{
        background: var(--card-bg);
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        margin-bottom: 20px;
    }}
    .two-col {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 24px;
    }}
    @media (max-width: 768px) {{
        .two-col {{ grid-template-columns: 1fr; }}
        body {{ padding: 16px; }}
    }}
    .footer {{
        margin-top: 40px;
        padding-top: 20px;
        border-top: 2px solid var(--border);
        font-size: 0.82rem;
        color: var(--text-light);
        text-align: center;
    }}
    .sub-header {{
        font-family: 'Playfair Display', serif;
        font-size: 1.05rem;
        color: var(--navy);
        margin: 16px 0 10px 0;
        font-weight: 600;
    }}
    .no-data {{
        color: var(--text-light);
        font-style: italic;
        padding: 12px;
    }}
</style>
</head>
<body>

<div class="header">
    <h1>{entity_name}</h1>
    <h2>{fy_label} Actuals Analysis Dashboard</h2>
    <div class="meta">Review Date: {review_date} · NM Public Education Department / School Budget Bureau</div>
</div>

<!-- Section 1: Executive Summary -->
<div class="section">
    <h3>Executive Summary</h3>
    <div class="cards">
        <div class="card">
            <div class="label">Revenue YTD</div>
            <div class="value">{fmt_currency(summary_stats['rev_ytd'], compact=True)}</div>
        </div>
        <div class="card accent-gold">
            <div class="label">Expenditure YTD</div>
            <div class="value">{fmt_currency(summary_stats['exp_ytd'], compact=True)}</div>
        </div>
        <div class="card {'accent-green' if summary_stats['net'] >= 0 else 'accent-red'}">
            <div class="label">Net (Rev − Exp)</div>
            <div class="value">{fmt_currency(summary_stats['net'], compact=True)}</div>
        </div>
        <div class="card">
            <div class="label">Exp. Adjusted Budget</div>
            <div class="value">{fmt_currency(summary_stats['exp_budget'], compact=True)}</div>
        </div>
    </div>
</div>

<!-- Section 4: Revenue vs Expenditure by Fund -->
<div class="section">
    <h3>Revenue vs. Expenditure Analysis</h3>
    <div class="chart-container">
        <canvas id="revExpChart" height="320"></canvas>
    </div>
</div>

<!-- Section 5: Funds Where Expenditures Exceed Revenue -->
<div class="section">
    <h3>Funds Where Expenditures Exceed Revenue</h3>

    <div class="sub-header">Non-Reimbursable Funds</div>
    {'<p class="no-data">No non-reimbursable funds with expenditures exceeding revenue.</p>' if len(non_reimb_df) == 0 else f"""
    <table>
        <thead><tr><th>Fund</th><th style="text-align:right">Revenue YTD</th><th style="text-align:right">Expenditure YTD</th><th style="text-align:right">Net</th><th>Status</th></tr></thead>
        <tbody>{_fund_deficit_rows(non_reimb_df)}</tbody>
    </table>"""}

    <div class="sub-header" style="margin-top:24px">Reimbursable Funds (Expected Behavior)</div>
    {'<p class="no-data">No reimbursable funds with expenditures exceeding revenue.</p>' if len(reimb_df) == 0 else f"""
    <table>
        <thead><tr><th>Fund</th><th style="text-align:right">Revenue YTD</th><th style="text-align:right">Expenditure YTD</th><th style="text-align:right">Net</th><th>Status</th></tr></thead>
        <tbody>{_fund_deficit_rows(reimb_df)}</tbody>
    </table>"""}

    {"" if len(other_df) == 0 else f'''
    <div class="sub-header" style="margin-top:24px">Other / Unclassified Funds</div>
    <table>
        <thead><tr><th>Fund</th><th style="text-align:right">Revenue YTD</th><th style="text-align:right">Expenditure YTD</th><th style="text-align:right">Net</th><th>Status</th></tr></thead>
        <tbody>{_fund_deficit_rows(other_df)}</tbody>
    </table>'''}
</div>

<!-- Section 6: Expenditure Distribution by Fund -->
<div class="section">
    <h3>Expenditure Distribution by Fund</h3>
    <div class="two-col">
        <div class="chart-container">
            <canvas id="fundDonut" height="300"></canvas>
        </div>
        <div>
            <table>
                <thead><tr><th>Fund</th><th style="text-align:right">YTD Spend</th><th style="text-align:right">% of Total</th></tr></thead>
                <tbody>{fund_table_rows}</tbody>
            </table>
        </div>
    </div>
</div>

<!-- Section 7: Expenditure by Function -->
<div class="section">
    <h3>Expenditure by Function</h3>
    <div class="chart-container">
        <canvas id="funcChart" height="350"></canvas>
    </div>
    <table style="margin-top:16px">
        <thead><tr>
            <th>Function</th><th style="text-align:right">Budget</th>
            <th style="text-align:right">YTD Actuals</th><th style="text-align:right">Encumbered</th>
            <th style="text-align:right">Available</th><th style="text-align:right">% Used (Act+Enc)</th>
        </tr></thead>
        <tbody>{func_table_rows}</tbody>
    </table>
</div>

<div class="footer">
    <p>NM Public Education Department · School Budget Bureau</p>
    <p style="margin-top:4px;font-size:0.78rem;">
        This review is conducted pursuant to NMAC 6.20.2 and does not constitute an audit.
    </p>
</div>

<script>
// Color palette
const navy = '#1e3a5f';
const gold = '#c9a96e';
const red  = '#b91c1c';
const teal = '#2dd4bf';
const amber = '#d97706';
const green = '#65a30d';
const violet = '#6366f1';

const palette = [navy, gold, '#4f8df5', teal, amber, red, green, violet, '#ec4899', '#06b6d4'];

// Section 4: Revenue vs Expenditure
new Chart(document.getElementById('revExpChart'), {{
    type: 'bar',
    data: {{
        labels: {json.dumps(chart_labels)},
        datasets: [
            {{
                label: 'Revenue YTD',
                data: {json.dumps(chart_rev)},
                backgroundColor: navy,
                borderRadius: 4,
            }},
            {{
                label: 'Expenditure YTD',
                data: {json.dumps(chart_exp)},
                backgroundColor: gold,
                borderRadius: 4,
            }}
        ]
    }},
    options: {{
        responsive: true,
        plugins: {{
            legend: {{ position: 'top' }},
            tooltip: {{
                callbacks: {{
                    label: ctx => ctx.dataset.label + ': $' + ctx.raw.toLocaleString()
                }}
            }}
        }},
        scales: {{
            x: {{ ticks: {{ maxRotation: 40, font: {{ size: 11 }} }} }},
            y: {{ ticks: {{ callback: v => '$' + (v/1000000).toFixed(1) + 'M' }} }}
        }}
    }}
}});

// Section 6: Fund Donut
new Chart(document.getElementById('fundDonut'), {{
    type: 'doughnut',
    data: {{
        labels: {json.dumps(donut_labels)},
        datasets: [{{
            data: {json.dumps(donut_values)},
            backgroundColor: palette.slice(0, {len(donut_labels)}),
            borderWidth: 2,
            borderColor: '#faf9f7'
        }}]
    }},
    options: {{
        responsive: true,
        plugins: {{
            legend: {{ position: 'right', labels: {{ font: {{ size: 11 }} }} }},
            tooltip: {{
                callbacks: {{
                    label: ctx => ctx.label + ': $' + ctx.raw.toLocaleString()
                }}
            }}
        }}
    }}
}});

// Section 7: Function Stacked Bar
new Chart(document.getElementById('funcChart'), {{
    type: 'bar',
    data: {{
        labels: {json.dumps(func_labels)},
        datasets: [
            {{
                label: 'YTD Actuals',
                data: {json.dumps(func_actuals)},
                backgroundColor: navy,
                borderRadius: 2,
            }},
            {{
                label: 'Encumbrance',
                data: {json.dumps(func_enc)},
                backgroundColor: amber,
                borderRadius: 2,
            }},
            {{
                label: 'Available',
                data: {json.dumps(func_avail)},
                backgroundColor: '#e8e4df',
                borderRadius: 2,
            }}
        ]
    }},
    options: {{
        indexAxis: 'y',
        responsive: true,
        plugins: {{
            legend: {{ position: 'top' }},
            tooltip: {{
                callbacks: {{
                    label: ctx => ctx.dataset.label + ': $' + ctx.raw.toLocaleString()
                }}
            }}
        }},
        scales: {{
            x: {{
                stacked: true,
                ticks: {{ callback: v => '$' + (v/1000000).toFixed(1) + 'M' }}
            }},
            y: {{
                stacked: true,
                ticks: {{ font: {{ size: 11 }} }}
            }}
        }}
    }}
}});
</script>
</body>
</html>"""

    return html


# ── Sidebar Filters ──────────────────────────────────────────────────────────
fy_labels = {row["FiscalYearKey"]: row["FiscalYearLabel"] for _, row in DIM_FISCAL.iterrows()}

with st.sidebar:
    st.markdown('<div class="app-title">OBMS Explorer</div>', unsafe_allow_html=True)
    st.markdown('<div class="app-subtitle">NM PED · School Budget Bureau</div>', unsafe_allow_html=True)
    st.markdown("---")

    acct_type = st.radio(
        "Account Type",
        options=["E", "R"],
        format_func=lambda x: "Expenditure" if x == "E" else "Revenue",
        index=0,
        horizontal=True
    )

    fy_options = sorted(ALL_FY_KEYS, reverse=True)
    selected_fy = st.multiselect(
        "Fiscal Year",
        options=fy_options,
        default=[fy_options[0]] if fy_options else [],
        format_func=lambda x: fy_labels.get(x, str(x))
    )

# ── Data Loading ─────────────────────────────────────────────────────────────
if not selected_fy:
    st.warning("Select at least one fiscal year.")
    st.stop()

act_raw, bud_raw = load_data_for_years(selected_fy)

if len(act_raw) == 0 and len(bud_raw) == 0:
    st.error("No data loaded. Check that Google Drive files are publicly shared.")
    st.stop()

# ── Remaining Sidebar Filters ────────────────────────────────────────────────
with st.sidebar:
    available_periods = sorted(
        act_raw["Reporting Period"].unique()
    ) if len(act_raw) > 0 else []

    if available_periods:
        selected_period = st.selectbox(
            "Reporting Period",
            options=available_periods,
            index=len(available_periods) - 1,
            help="Select the reporting quarter. YTD amounts are cumulative through this quarter."
        )
    else:
        selected_period = None

    st.markdown("---")
    st.markdown('<div class="section-header">Dimension Filters</div>', unsafe_allow_html=True)

    all_entities = sorted(
        set(act_raw["Budget Entity"].unique()) | set(bud_raw["Budget Entity"].unique())
    )
    selected_entities = st.multiselect("Budget Entity", options=all_entities, default=[])

    all_funds = sorted(
        set(act_raw["Fund"].unique()) | set(bud_raw["Fund"].unique())
    )
    selected_funds = st.multiselect("Fund", options=all_funds, default=[])

    all_functions = sorted(
        set(act_raw["Function"].unique()) | set(bud_raw["Function"].unique())
    )
    selected_functions = st.multiselect("Function", options=all_functions, default=[])

    all_objects = sorted(
        set(act_raw["Object"].unique()) | set(bud_raw["Object"].unique())
    )
    selected_objects = st.multiselect("Object", options=all_objects, default=[])

    all_programs = sorted(
        set(act_raw["Program"].unique()) | set(bud_raw["Program"].unique())
    )
    selected_programs = st.multiselect("Program", options=all_programs, default=[])

    st.markdown("---")
    act_count = len(act_raw)
    bud_count = len(bud_raw)
    st.caption(f"📁 {act_count:,} actuals rows · {bud_count:,} budget rows · {len(selected_fy)} fiscal year(s)")
    st.caption(f"☁️ Data source: Google Drive")


# ── Apply Filters ────────────────────────────────────────────────────────────
act_f, bud_f = apply_filters(
    act_raw, bud_raw,
    account_type=acct_type,
    period=selected_period,
    entities=selected_entities or None,
    funds=selected_funds or None,
    functions=selected_functions or None,
    objects=selected_objects or None,
    programs=selected_programs or None
)


# ── Header ───────────────────────────────────────────────────────────────────
acct_label = "Expenditure" if acct_type == "E" else "Revenue"
period_label = selected_period if selected_period else "All Periods"
fy_label = ", ".join(fy_labels.get(k, str(k)) for k in selected_fy) if selected_fy else "All Years"

st.markdown(f"""
<div style="margin-bottom: 0.5rem;">
    <span class="app-title" style="font-size: 1.3rem;">OBMS Financial Explorer</span>
    <span style="color: var(--text-secondary); font-size: 0.85rem; margin-left: 12px;">
        {acct_label} · {fy_label} · {period_label}
    </span>
</div>
""", unsafe_allow_html=True)


# ── KPI Row ──────────────────────────────────────────────────────────────────
total_budget = bud_f["Adjusted Amt"].sum()
total_ytd = act_f["Actuals YTDAmount"].sum()
total_encumbrance = act_f["Actuals Encumbrance"].sum()
total_balance = total_budget - total_ytd - total_encumbrance
total_pct_spent = (total_ytd / total_budget * 100) if total_budget != 0 else 0
total_pct_committed = ((total_ytd + total_encumbrance) / total_budget * 100) if total_budget != 0 else 0
total_fte_budget = bud_f["Final FTE"].sum()
total_fte_actual = act_f["Actuals FTE"].sum()
entity_count = max(bud_f["Budget Entity"].nunique(), act_f["Budget Entity"].nunique())

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Adjusted Budget", fmt_currency(total_budget, compact=True))
k2.metric("YTD Actuals", fmt_currency(total_ytd, compact=True))
k3.metric("Encumbrance", fmt_currency(total_encumbrance, compact=True))
k4.metric("Budget Balance", fmt_currency(total_balance, compact=True))
k5.metric("% Spent (YTD)", fmt_pct(total_pct_spent))
k6.metric("% Committed", fmt_pct(total_pct_committed))


# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_overview, tab_entity, tab_detail, tab_trends, tab_report, tab_data = st.tabs([
    "📊 Overview", "🏫 Entity Analysis", "🔍 Drill-Down", "📈 Trends",
    "📄 District Report", "📋 Data Export"
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1: Overview
# ════════════════════════════════════════════════════════════════════════════
with tab_overview:

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown('<div class="section-header">Budget vs Actuals by Fund</div>', unsafe_allow_html=True)

        bva_fund = compute_budget_vs_actuals(act_f, bud_f, "Fund")
        top_funds = bva_fund.head(10).copy()
        top_funds["Fund_Short"] = top_funds["Fund"].apply(extract_name)

        fig_fund = go.Figure()
        fig_fund.add_trace(go.Bar(
            name="Adjusted Budget",
            x=top_funds["Fund_Short"],
            y=top_funds["Adjusted_Budget"],
            marker_color="#4f8df5",
            hovertemplate="%{x}<br>Budget: $%{y:,.0f}<extra></extra>"
        ))
        fig_fund.add_trace(go.Bar(
            name="YTD Actuals",
            x=top_funds["Fund_Short"],
            y=top_funds["YTD_Actuals"],
            marker_color="#2dd4bf",
            hovertemplate="%{x}<br>YTD: $%{y:,.0f}<extra></extra>"
        ))
        fig_fund.add_trace(go.Bar(
            name="Encumbrance",
            x=top_funds["Fund_Short"],
            y=top_funds["Encumbrance"],
            marker_color="#f59e0b",
            opacity=0.7,
            hovertemplate="%{x}<br>Encumbrance: $%{y:,.0f}<extra></extra>"
        ))
        fig_fund.update_layout(
            **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
            barmode="group",
            height=420,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis_tickangle=-30,
            yaxis_title=""
        )
        st.plotly_chart(fig_fund, use_container_width=True)

    with col_right:
        st.markdown('<div class="section-header">Spend Distribution by Function</div>', unsafe_allow_html=True)

        bva_func = compute_budget_vs_actuals(act_f, bud_f, "Function")
        bva_func["Function_Name"] = bva_func["Function"].apply(extract_name)
        bva_func_top = bva_func[bva_func["YTD_Actuals"] > 0].head(8)

        fig_func = go.Figure(go.Treemap(
            labels=bva_func_top["Function_Name"],
            values=bva_func_top["YTD_Actuals"],
            parents=[""] * len(bva_func_top),
            textinfo="label+value+percent root",
            texttemplate="%{label}<br>$%{value:,.0f}<br>%{percentRoot:.1%}",
            marker=dict(
                colors=bva_func_top["Pct_Spent"],
                colorscale=[[0, "#2dd4bf"], [0.5, "#4f8df5"], [1, "#f43f5e"]],
                showscale=True,
                colorbar=dict(title="% Spent", ticksuffix="%")
            ),
            hovertemplate="%{label}<br>YTD: $%{value:,.0f}<br>% Spent: %{color:.1f}%<extra></extra>"
        ))
        tmpl = PLOTLY_TEMPLATE["layout"].to_plotly_json()
        tmpl["margin"] = dict(l=10, r=10, t=30, b=10)
        fig_func.update_layout(**tmpl, height=420)
        st.plotly_chart(fig_func, use_container_width=True)

    # ── Execution gauge ──
    st.markdown('<div class="section-header">Budget Execution Summary</div>', unsafe_allow_html=True)

    g1, g2, g3 = st.columns(3)

    if selected_period and selected_period.startswith("Q"):
        quarter_num = int(selected_period[1:])
        expected_pct = quarter_num * 25
    else:
        expected_pct = 50

    with g1:
        fig_gauge1 = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=total_pct_spent,
            number={"suffix": "%", "font": {"size": 36, "family": "JetBrains Mono"}},
            delta={"reference": expected_pct, "suffix": "%", "relative": False},
            title={"text": "% Spent vs Expected", "font": {"size": 14}},
            gauge={
                "axis": {"range": [0, 100], "ticksuffix": "%"},
                "bar": {"color": "#4f8df5"},
                "bgcolor": "#1a1d2e",
                "steps": [
                    {"range": [0, expected_pct], "color": "#1e2130"},
                    {"range": [expected_pct, 100], "color": "#1a1a2e"}
                ],
                "threshold": {
                    "line": {"color": "#f59e0b", "width": 3},
                    "thickness": 0.8,
                    "value": expected_pct
                }
            }
        ))
        tmpl1 = PLOTLY_TEMPLATE["layout"].to_plotly_json()
        tmpl1["margin"] = dict(l=30, r=30, t=60, b=20)
        fig_gauge1.update_layout(**tmpl1, height=250)
        st.plotly_chart(fig_gauge1, use_container_width=True)

    with g2:
        fig_gauge2 = go.Figure(go.Indicator(
            mode="gauge+number",
            value=total_pct_committed,
            number={"suffix": "%", "font": {"size": 36, "family": "JetBrains Mono"}},
            title={"text": "% Committed (YTD + Enc.)", "font": {"size": 14}},
            gauge={
                "axis": {"range": [0, 120], "ticksuffix": "%"},
                "bar": {"color": "#2dd4bf"},
                "bgcolor": "#1a1d2e",
                "steps": [
                    {"range": [0, 100], "color": "#1e2130"},
                    {"range": [100, 120], "color": "#3d1515"}
                ],
                "threshold": {
                    "line": {"color": "#f43f5e", "width": 3},
                    "thickness": 0.8,
                    "value": 100
                }
            }
        ))
        tmpl2 = PLOTLY_TEMPLATE["layout"].to_plotly_json()
        tmpl2["margin"] = dict(l=30, r=30, t=60, b=20)
        fig_gauge2.update_layout(**tmpl2, height=250)
        st.plotly_chart(fig_gauge2, use_container_width=True)

    with g3:
        fig_gauge3 = go.Figure(go.Indicator(
            mode="number+delta",
            value=total_balance,
            number={"prefix": "$", "font": {"size": 36, "family": "JetBrains Mono"},
                    "valueformat": ",.0f"},
            title={"text": "Remaining Balance", "font": {"size": 14}},
            delta={"reference": total_budget * 0.5, "prefix": "$", "valueformat": ",.0f",
                   "relative": False}
        ))
        tmpl3 = PLOTLY_TEMPLATE["layout"].to_plotly_json()
        tmpl3["margin"] = dict(l=30, r=30, t=60, b=20)
        fig_gauge3.update_layout(**tmpl3, height=250)
        st.plotly_chart(fig_gauge3, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 2: Entity Analysis
# ════════════════════════════════════════════════════════════════════════════
with tab_entity:

    bva_entity = compute_budget_vs_actuals(act_f, bud_f, "Budget Entity")

    st.markdown('<div class="section-header">Entity Budget Execution</div>', unsafe_allow_html=True)

    scatter_data = bva_entity[bva_entity["Adjusted_Budget"] > 0].copy()

    fig_scatter = px.scatter(
        scatter_data,
        x="Adjusted_Budget",
        y="Pct_Spent",
        size="YTD_Actuals",
        color="Pct_Committed",
        color_continuous_scale=[[0, "#2dd4bf"], [0.5, "#4f8df5"], [1, "#f43f5e"]],
        hover_name="Budget Entity",
        hover_data={
            "Adjusted_Budget": ":$,.0f",
            "YTD_Actuals": ":$,.0f",
            "Pct_Spent": ":.1f",
            "Pct_Committed": ":.1f"
        },
        labels={
            "Adjusted_Budget": "Adjusted Budget",
            "Pct_Spent": "% Spent (YTD)",
            "Pct_Committed": "% Committed"
        }
    )
    fig_scatter.update_layout(
        **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
        height=450,
        xaxis_title="Adjusted Budget",
        yaxis_title="% Spent (YTD)",
        coloraxis_colorbar_title="% Committed"
    )
    if selected_period and selected_period.startswith("Q"):
        quarter_num = int(selected_period[1:])
        fig_scatter.add_hline(y=quarter_num * 25, line_dash="dash",
                              line_color="#f59e0b", opacity=0.6,
                              annotation_text=f"Expected ({quarter_num*25}%)")
    st.plotly_chart(fig_scatter, use_container_width=True)

    st.markdown('<div class="section-header">Entity Detail Table</div>', unsafe_allow_html=True)

    display_entity = bva_entity[["Budget Entity", "Adjusted_Budget", "YTD_Actuals",
                                  "Encumbrance", "Budget_Balance", "Pct_Spent",
                                  "Pct_Committed", "Budget_FTE", "Actuals_FTE"]].copy()
    display_entity.columns = ["Entity", "Adjusted Budget", "YTD Actuals",
                               "Encumbrance", "Balance", "% Spent",
                               "% Committed", "Budget FTE", "Actual FTE"]

    st.dataframe(
        display_entity.style.format({
            "Adjusted Budget": "${:,.0f}",
            "YTD Actuals": "${:,.0f}",
            "Encumbrance": "${:,.0f}",
            "Balance": "${:,.0f}",
            "% Spent": "{:.1f}%",
            "% Committed": "{:.1f}%",
            "Budget FTE": "{:,.1f}",
            "Actual FTE": "{:,.1f}"
        }),
        use_container_width=True,
        height=500
    )


# ════════════════════════════════════════════════════════════════════════════
# TAB 3: Drill-Down
# ════════════════════════════════════════════════════════════════════════════
with tab_detail:

    st.markdown('<div class="section-header">Dimensional Drill-Down</div>', unsafe_allow_html=True)

    drill_dim = st.selectbox(
        "Group by",
        options=["Fund", "Function", "Object", "Program", "Job Class", "Location"],
        index=0
    )

    col_map = {
        "Fund": "Fund",
        "Function": "Function",
        "Object": "Object",
        "Program": "Program",
        "Job Class": "Job Class",
        "Location": "Location"
    }
    drill_col = col_map[drill_dim]

    bva_drill = compute_budget_vs_actuals(act_f, bud_f, drill_col)
    bva_drill["Short_Name"] = bva_drill[drill_col].apply(extract_name)
    bva_drill["Code"] = bva_drill[drill_col].apply(extract_code)

    top_n = st.slider("Show top N", min_value=5, max_value=50, value=15)
    drill_top = bva_drill.head(top_n)

    fig_drill = go.Figure()
    fig_drill.add_trace(go.Bar(
        name="YTD Actuals",
        y=drill_top["Short_Name"],
        x=drill_top["YTD_Actuals"],
        orientation="h",
        marker_color="#4f8df5",
        hovertemplate="%{y}<br>YTD: $%{x:,.0f}<extra></extra>"
    ))
    fig_drill.add_trace(go.Bar(
        name="Encumbrance",
        y=drill_top["Short_Name"],
        x=drill_top["Encumbrance"],
        orientation="h",
        marker_color="#f59e0b",
        opacity=0.7,
        hovertemplate="%{y}<br>Enc: $%{x:,.0f}<extra></extra>"
    ))
    fig_drill.add_trace(go.Bar(
        name="Remaining Balance",
        y=drill_top["Short_Name"],
        x=drill_top["Budget_Balance"].clip(lower=0),
        orientation="h",
        marker_color="#1e2130",
        marker_line=dict(color="#4f8df5", width=1),
        hovertemplate="%{y}<br>Balance: $%{x:,.0f}<extra></extra>"
    ))
    tmpl_drill = PLOTLY_TEMPLATE["layout"].to_plotly_json()
    tmpl_drill["yaxis"] = dict(autorange="reversed", gridcolor="#1e2130", zerolinecolor="#2a2d3e")
    fig_drill.update_layout(
        **tmpl_drill,
        barmode="stack",
        height=max(350, top_n * 28),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title=""
    )
    st.plotly_chart(fig_drill, use_container_width=True)

    drill_display = bva_drill[[drill_col, "Adjusted_Budget", "YTD_Actuals",
                                "Encumbrance", "Budget_Balance", "Pct_Spent"]].copy()
    drill_display.columns = [drill_dim, "Adjusted Budget", "YTD Actuals",
                              "Encumbrance", "Balance", "% Spent"]
    st.dataframe(
        drill_display.style.format({
            "Adjusted Budget": "${:,.0f}",
            "YTD Actuals": "${:,.0f}",
            "Encumbrance": "${:,.0f}",
            "Balance": "${:,.0f}",
            "% Spent": "{:.1f}%"
        }),
        use_container_width=True,
        height=400
    )


# ════════════════════════════════════════════════════════════════════════════
# TAB 4: Trends (Multi-Period)
# ════════════════════════════════════════════════════════════════════════════
with tab_trends:

    st.markdown('<div class="section-header">Quarter-over-Quarter Trends</div>', unsafe_allow_html=True)

    act_trends = act_raw
    if acct_type:
        act_trends = act_trends[act_trends["Account Type"] == acct_type]
    if selected_entities:
        act_trends = act_trends[act_trends["Budget Entity"].isin(selected_entities)]
    if selected_funds:
        act_trends = act_trends[act_trends["Fund"].isin(selected_funds)]

    trend_data = act_trends.groupby(["Reporting Period", "PeriodOrder", "FiscalYearKey"]).agg(
        Period_Amount=("Actuals Period Amount", "sum"),
        YTD_Amount=("Actuals YTDAmount", "sum"),
        Encumbrance=("Actuals Encumbrance", "sum"),
        FTE=("Actuals FTE", "sum")
    ).reset_index().sort_values(["FiscalYearKey", "PeriodOrder"])

    trend_data["FY_Label"] = trend_data["FiscalYearKey"].map(fy_labels)

    if len(trend_data) > 0:
        tc1, tc2 = st.columns(2)

        with tc1:
            fig_trend1 = go.Figure()
            for fy in trend_data["FiscalYearKey"].unique():
                fy_data = trend_data[trend_data["FiscalYearKey"] == fy]
                fig_trend1.add_trace(go.Scatter(
                    x=fy_data["Reporting Period"],
                    y=fy_data["YTD_Amount"],
                    mode="lines+markers",
                    name=fy_labels.get(fy, str(fy)),
                    line=dict(width=3),
                    marker=dict(size=10),
                    hovertemplate="%{x}<br>YTD: $%{y:,.0f}<extra></extra>"
                ))
            fig_trend1.update_layout(
                **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
                title="YTD Cumulative Spend",
                height=380,
                yaxis_title=""
            )
            st.plotly_chart(fig_trend1, use_container_width=True)

        with tc2:
            fig_trend2 = go.Figure()
            for fy in trend_data["FiscalYearKey"].unique():
                fy_data = trend_data[trend_data["FiscalYearKey"] == fy]
                fig_trend2.add_trace(go.Bar(
                    x=fy_data["Reporting Period"],
                    y=fy_data["Period_Amount"],
                    name=fy_labels.get(fy, str(fy)),
                    hovertemplate="%{x}<br>Period: $%{y:,.0f}<extra></extra>"
                ))
            fig_trend2.update_layout(
                **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
                title="Period Spend by Quarter",
                height=380,
                barmode="group",
                yaxis_title=""
            )
            st.plotly_chart(fig_trend2, use_container_width=True)

        st.markdown('<div class="section-header">FTE Trends</div>', unsafe_allow_html=True)
        fig_fte = go.Figure()
        for fy in trend_data["FiscalYearKey"].unique():
            fy_data = trend_data[trend_data["FiscalYearKey"] == fy]
            fig_fte.add_trace(go.Scatter(
                x=fy_data["Reporting Period"],
                y=fy_data["FTE"],
                mode="lines+markers",
                name=fy_labels.get(fy, str(fy)),
                line=dict(width=3),
                marker=dict(size=10),
                fill="tozeroy",
                hovertemplate="%{x}<br>FTE: %{y:,.1f}<extra></extra>"
            ))
        fig_fte.update_layout(
            **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
            title="FTE by Quarter",
            height=350,
            yaxis_title="FTE"
        )
        st.plotly_chart(fig_fte, use_container_width=True)
    else:
        st.info("No trend data available for current filters.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 5: District Report + Entity Analysis (Sections 4–7)
# ════════════════════════════════════════════════════════════════════════════
with tab_report:

    st.markdown('<div class="section-header">Quarterly District Report</div>', unsafe_allow_html=True)
    st.caption(
        "Generate expenditure and revenue reports in the standard quarterly review "
        "CSV format, plus an interactive financial analysis with HTML export."
    )

    # ── Entity selector (independent of sidebar entity filter) ───────────
    report_entities = sorted(
        set(act_raw["Budget Entity"].unique()) | set(bud_raw["Budget Entity"].unique())
    )

    report_entity = st.selectbox(
        "Select District / Charter School",
        options=report_entities,
        index=0,
        key="report_entity_select"
    )

    # ── Period for actuals ───────────────────────────────────────────────
    act_for_report = act_raw
    if selected_period:
        act_for_report = act_for_report[act_for_report["Reporting Period"] == selected_period]

    bud_for_report = bud_raw

    # ── Build reports ────────────────────────────────────────────────────
    if report_entity:
        entity_short = report_entity.replace(" ", "_").replace("/", "-")
        fy_code = fy_key_to_code(selected_fy[0]) if selected_fy else "xxxx"
        period_code = selected_period.lower() if selected_period else "all"

        # CSV reports (existing)
        exp_report = build_district_report(act_for_report, bud_for_report, report_entity, "E")
        rev_report = build_district_report(act_for_report, bud_for_report, report_entity, "R")

        # ── Summary metrics ──────────────────────────────────────────────
        st.markdown(f"**{report_entity}** · FY {fy_label} · {period_label}")

        # Compute totals for summary cards
        exp_act_entity = act_for_report[
            (act_for_report["Budget Entity"] == report_entity) &
            (act_for_report["Account Type"] == "E")
        ]
        exp_bud_entity = bud_for_report[
            (bud_for_report["Budget Entity"] == report_entity) &
            (bud_for_report["Account Type"] == "E")
        ]
        rev_act_entity = act_for_report[
            (act_for_report["Budget Entity"] == report_entity) &
            (act_for_report["Account Type"] == "R")
        ]

        exp_budget_total = exp_bud_entity["Adjusted Amt"].sum()
        exp_ytd_total = exp_act_entity["Actuals YTDAmount"].sum()
        rev_ytd_total = rev_act_entity["Actuals YTDAmount"].sum()
        net_total = rev_ytd_total - exp_ytd_total

        rm1, rm2, rm3, rm4 = st.columns(4)
        rm1.metric("Revenue YTD", fmt_currency(rev_ytd_total, compact=True))
        rm2.metric("Expenditure YTD", fmt_currency(exp_ytd_total, compact=True))
        rm3.metric("Net (Rev − Exp)", fmt_currency(net_total, compact=True))
        rm4.metric("Exp. Adjusted Budget", fmt_currency(exp_budget_total, compact=True))

        # ──────────────────────────────────────────────────────────────────
        # CSV Data Export Section (existing functionality, preserved)
        # ──────────────────────────────────────────────────────────────────
        with st.expander("📥 CSV / Excel Data Exports", expanded=False):
            st.markdown("**Expenditure Report**")
            if len(exp_report) > 0:
                st.dataframe(exp_report, use_container_width=True, height=300)
                exp_filename = f"{entity_short}_fy{fy_code}_{period_code}_exp.csv"
                ec1, ec2 = st.columns(2)
                with ec1:
                    st.download_button(
                        "📥 Expenditure CSV",
                        data=exp_report.to_csv(index=False),
                        file_name=exp_filename,
                        mime="text/csv",
                        key="dl_exp_csv"
                    )
                with ec2:
                    st.download_button(
                        "📥 Expenditure Excel",
                        data=to_excel_download(exp_report, "Expenditures"),
                        file_name=exp_filename.replace(".csv", ".xlsx"),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_exp_xlsx"
                    )
            else:
                st.info("No expenditure data for this entity.")

            st.markdown("---")
            st.markdown("**Revenue Report**")
            if len(rev_report) > 0:
                st.dataframe(rev_report, use_container_width=True, height=300)
                rev_filename = f"{entity_short}_fy{fy_code}_{period_code}_rev.csv"
                rc1, rc2 = st.columns(2)
                with rc1:
                    st.download_button(
                        "📥 Revenue CSV",
                        data=rev_report.to_csv(index=False),
                        file_name=rev_filename,
                        mime="text/csv",
                        key="dl_rev_csv"
                    )
                with rc2:
                    st.download_button(
                        "📥 Revenue Excel",
                        data=to_excel_download(rev_report, "Revenue"),
                        file_name=rev_filename.replace(".csv", ".xlsx"),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_rev_xlsx"
                    )
            else:
                st.info("No revenue data for this entity.")

        # ──────────────────────────────────────────────────────────────────
        # NEW: Entity Financial Analysis (Sections 4–7)
        # ──────────────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown('<div class="section-header">Financial Analysis</div>', unsafe_allow_html=True)
        st.caption("Interactive analysis for the selected entity. Use the HTML export button below to generate a standalone report.")

        # ── Section 4: Revenue vs Expenditure by Fund ────────────────────
        st.markdown("#### Revenue vs. Expenditure by Fund")

        rev_exp_df = compute_entity_rev_vs_exp(act_for_report, bud_for_report, report_entity)

        if len(rev_exp_df) > 0:
            top_rev_exp = rev_exp_df.head(12)

            fig_revexp = go.Figure()
            fig_revexp.add_trace(go.Bar(
                name="Revenue YTD",
                x=top_rev_exp["Fund_Name"],
                y=top_rev_exp["Revenue_YTD"],
                marker_color="#4f8df5",
                hovertemplate="%{x}<br>Revenue: $%{y:,.0f}<extra></extra>"
            ))
            fig_revexp.add_trace(go.Bar(
                name="Expenditure YTD",
                x=top_rev_exp["Fund_Name"],
                y=top_rev_exp["Expenditure_YTD"],
                marker_color="#f59e0b",
                hovertemplate="%{x}<br>Expenditure: $%{y:,.0f}<extra></extra>"
            ))
            fig_revexp.update_layout(
                **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
                barmode="group",
                height=400,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis_tickangle=-30,
                yaxis_title=""
            )
            st.plotly_chart(fig_revexp, use_container_width=True)
        else:
            st.info("No revenue or expenditure data available.")

        # ── Section 5: Funds Where Exp > Rev ─────────────────────────────
        st.markdown("#### Funds Where Expenditures Exceed Revenue")

        if len(rev_exp_df) > 0:
            non_reimb, reimb, other_funds = compute_funds_exp_exceed_rev(rev_exp_df)

            s5_c1, s5_c2 = st.columns(2)

            with s5_c1:
                st.markdown("**Non-Reimbursable Funds** _(real cash concern)_")
                if len(non_reimb) > 0:
                    nr_display = non_reimb[["Fund", "Revenue_YTD", "Expenditure_YTD", "Net"]].copy()
                    nr_display.columns = ["Fund", "Revenue YTD", "Expenditure YTD", "Net"]
                    st.dataframe(
                        nr_display.style.format({
                            "Revenue YTD": "${:,.0f}",
                            "Expenditure YTD": "${:,.0f}",
                            "Net": "${:,.0f}"
                        }).map(
                            lambda v: "color: #f43f5e" if isinstance(v, (int, float)) and v < 0 else "",
                            subset=["Net"]
                        ),
                        use_container_width=True,
                        height=min(300, max(100, len(non_reimb) * 40 + 60))
                    )
                else:
                    st.success("No non-reimbursable fund deficits found.")

            with s5_c2:
                st.markdown("**Reimbursable Funds** _(expected: spend first, reimburse later)_")
                if len(reimb) > 0:
                    r_display = reimb[["Fund", "Revenue_YTD", "Expenditure_YTD", "Net"]].copy()
                    r_display.columns = ["Fund", "Revenue YTD", "Expenditure YTD", "Net"]
                    st.dataframe(
                        r_display.style.format({
                            "Revenue YTD": "${:,.0f}",
                            "Expenditure YTD": "${:,.0f}",
                            "Net": "${:,.0f}"
                        }),
                        use_container_width=True,
                        height=min(300, max(100, len(reimb) * 40 + 60))
                    )
                else:
                    st.info("No reimbursable fund deficits.")

            if len(other_funds) > 0:
                with st.expander(f"Other / Unclassified Funds ({len(other_funds)})"):
                    o_display = other_funds[["Fund", "Revenue_YTD", "Expenditure_YTD", "Net"]].copy()
                    o_display.columns = ["Fund", "Revenue YTD", "Expenditure YTD", "Net"]
                    st.dataframe(
                        o_display.style.format({
                            "Revenue YTD": "${:,.0f}",
                            "Expenditure YTD": "${:,.0f}",
                            "Net": "${:,.0f}"
                        }),
                        use_container_width=True
                    )

        # ── Section 6: Expenditure Distribution by Fund ──────────────────
        st.markdown("#### Expenditure Distribution by Fund")

        fund_dist = compute_exp_by_fund_type(act_for_report, report_entity)

        if len(fund_dist) > 0 and fund_dist["YTD_Actuals"].sum() > 0:
            s6_c1, s6_c2 = st.columns([2, 3])

            with s6_c1:
                fund_donut_data = fund_dist[fund_dist["YTD_Actuals"] > 0].head(10)
                fig_donut = go.Figure(go.Pie(
                    labels=fund_donut_data["Fund_Name"],
                    values=fund_donut_data["YTD_Actuals"],
                    hole=0.5,
                    textinfo="label+percent",
                    textposition="outside",
                    marker=dict(
                        colors=["#4f8df5", "#2dd4bf", "#f59e0b", "#f43f5e", "#8b5cf6",
                                "#06b6d4", "#84cc16", "#ec4899", "#f97316", "#6366f1"]
                    ),
                    hovertemplate="%{label}<br>$%{value:,.0f}<br>%{percent}<extra></extra>"
                ))
                tmpl_donut = PLOTLY_TEMPLATE["layout"].to_plotly_json()
                tmpl_donut["margin"] = dict(l=10, r=10, t=10, b=10)
                fig_donut.update_layout(**tmpl_donut, height=350, showlegend=False)
                st.plotly_chart(fig_donut, use_container_width=True)

            with s6_c2:
                fd_display = fund_dist.head(10)[["Fund", "YTD_Actuals", "Pct_of_Total"]].copy()
                fd_display.columns = ["Fund", "YTD Spend", "% of Total"]
                st.dataframe(
                    fd_display.style.format({
                        "YTD Spend": "${:,.0f}",
                        "% of Total": "{:.1f}%"
                    }),
                    use_container_width=True,
                    height=min(400, max(150, len(fd_display) * 40 + 60))
                )
        else:
            st.info("No expenditure data available for fund distribution.")

        # ── Section 7: Expenditure by Function ───────────────────────────
        st.markdown("#### Expenditure by Function")

        func_data = compute_exp_by_function(act_for_report, bud_for_report, report_entity)

        if len(func_data) > 0:
            func_chart_data = func_data[func_data["Adjusted_Budget"] > 0].head(12)

            fig_func_bar = go.Figure()
            fig_func_bar.add_trace(go.Bar(
                name="YTD Actuals",
                y=func_chart_data["Function_Name"],
                x=func_chart_data["YTD_Actuals"],
                orientation="h",
                marker_color="#4f8df5",
                hovertemplate="%{y}<br>YTD: $%{x:,.0f}<extra></extra>"
            ))
            fig_func_bar.add_trace(go.Bar(
                name="Encumbrance",
                y=func_chart_data["Function_Name"],
                x=func_chart_data["Encumbrance"],
                orientation="h",
                marker_color="#f59e0b",
                hovertemplate="%{y}<br>Enc: $%{x:,.0f}<extra></extra>"
            ))
            fig_func_bar.add_trace(go.Bar(
                name="Available",
                y=func_chart_data["Function_Name"],
                x=func_chart_data["Available"].clip(lower=0),
                orientation="h",
                marker_color="#1e2130",
                marker_line=dict(color="#4f8df5", width=1),
                hovertemplate="%{y}<br>Available: $%{x:,.0f}<extra></extra>"
            ))
            tmpl_func = PLOTLY_TEMPLATE["layout"].to_plotly_json()
            tmpl_func["yaxis"] = dict(autorange="reversed", gridcolor="#1e2130", zerolinecolor="#2a2d3e")
            fig_func_bar.update_layout(
                **tmpl_func,
                barmode="stack",
                height=max(300, len(func_chart_data) * 35),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis_title=""
            )
            st.plotly_chart(fig_func_bar, use_container_width=True)

            # Function detail table
            func_table = func_data[["Function", "Adjusted_Budget", "YTD_Actuals",
                                     "Encumbrance", "Available", "Pct_Used"]].copy()
            func_table.columns = ["Function", "Budget", "YTD Actuals", "Encumbered", "Available", "% Used (Act+Enc)"]
            st.dataframe(
                func_table.style.format({
                    "Budget": "${:,.0f}",
                    "YTD Actuals": "${:,.0f}",
                    "Encumbered": "${:,.0f}",
                    "Available": "${:,.0f}",
                    "% Used (Act+Enc)": "{:.1f}%"
                }),
                use_container_width=True,
                height=min(500, max(150, len(func_table) * 40 + 60))
            )
        else:
            st.info("No function-level expenditure data available.")

        # ──────────────────────────────────────────────────────────────────
        # HTML Export Button
        # ──────────────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown('<div class="section-header">Export Analysis</div>', unsafe_allow_html=True)

        summary_stats = {
            "rev_ytd": rev_ytd_total,
            "exp_ytd": exp_ytd_total,
            "net": net_total,
            "exp_budget": exp_budget_total,
        }

        # Compute data for HTML export
        if len(rev_exp_df) > 0:
            non_reimb_html, reimb_html, other_html = compute_funds_exp_exceed_rev(rev_exp_df)
        else:
            non_reimb_html = reimb_html = other_html = pd.DataFrame()

        fund_dist_html = compute_exp_by_fund_type(act_for_report, report_entity) if len(act_for_report) > 0 else pd.DataFrame()
        func_html = compute_exp_by_function(act_for_report, bud_for_report, report_entity)

        html_content = build_html_report(
            entity_name=report_entity,
            fy_label=fy_label,
            period_label=period_label,
            rev_exp_df=rev_exp_df if len(rev_exp_df) > 0 else pd.DataFrame(columns=["Fund","Revenue_YTD","Expenditure_YTD","Fund_Name"]),
            non_reimb_df=non_reimb_html,
            reimb_df=reimb_html,
            other_df=other_html,
            fund_dist_df=fund_dist_html if len(fund_dist_html) > 0 else pd.DataFrame(columns=["Fund","YTD_Actuals","Fund_Name","Pct_of_Total"]),
            func_df=func_html if len(func_html) > 0 else pd.DataFrame(columns=["Function","Adjusted_Budget","YTD_Actuals","Encumbrance","Available","Pct_Used"]),
            summary_stats=summary_stats
        )

        html_filename = f"{entity_short}_fy{fy_code}_{period_code}_analysis.html"

        st.download_button(
            "📄 Download HTML Analysis Report",
            data=html_content,
            file_name=html_filename,
            mime="text/html",
            key="dl_html_report"
        )
        st.caption(
            "This HTML report includes Sections 1, 4–7 from the quarterly review template. "
            "Sections requiring your memo (Key Concerns, Compliance, Audit Findings, Action Items) "
            "can be added after export or in a future update."
        )


# ════════════════════════════════════════════════════════════════════════════
# TAB 6: Data Export (unchanged)
# ════════════════════════════════════════════════════════════════════════════
with tab_data:

    st.markdown('<div class="section-header">Filtered Data Export</div>', unsafe_allow_html=True)
    st.caption("Export the currently filtered data to Excel or CSV.")

    exp1, exp2 = st.columns(2)

    with exp1:
        st.markdown("**Budget Data** (filtered)")
        st.write(f"{len(bud_f):,} rows")
        if len(bud_f) > 0:
            st.dataframe(bud_f.head(100), use_container_width=True, height=300)
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button(
                    "📥 Download Excel",
                    data=to_excel_download(bud_f, "Budget"),
                    file_name=f"budget_export_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            with col_dl2:
                st.download_button(
                    "📥 Download CSV",
                    data=bud_f.to_csv(index=False),
                    file_name=f"budget_export_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

    with exp2:
        st.markdown("**Actuals Data** (filtered)")
        st.write(f"{len(act_f):,} rows")
        if len(act_f) > 0:
            st.dataframe(act_f.head(100), use_container_width=True, height=300)
            col_dl3, col_dl4 = st.columns(2)
            with col_dl3:
                st.download_button(
                    "📥 Download Excel",
                    data=to_excel_download(act_f, "Actuals"),
                    file_name=f"actuals_export_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            with col_dl4:
                st.download_button(
                    "📥 Download CSV",
                    data=act_f.to_csv(index=False),
                    file_name=f"actuals_export_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

    st.markdown("---")
    st.markdown('<div class="section-header">Budget vs Actuals Summary Export</div>', unsafe_allow_html=True)

    summary_by = st.selectbox(
        "Summarize by",
        options=["Budget Entity", "Fund", "Function", "Object", "Program"],
        key="export_summary"
    )
    bva_export = compute_budget_vs_actuals(act_f, bud_f, summary_by)
    bva_export.columns = [summary_by, "Adjusted Budget", "Final Budget", "Budget FTE",
                           "YTD Actuals", "Period Actuals", "Encumbrance", "Actual FTE",
                           "Budget Balance", "% Spent", "% Committed"]

    st.dataframe(
        bva_export.style.format({
            "Adjusted Budget": "${:,.0f}",
            "Final Budget": "${:,.0f}",
            "YTD Actuals": "${:,.0f}",
            "Period Actuals": "${:,.0f}",
            "Encumbrance": "${:,.0f}",
            "Budget Balance": "${:,.0f}",
            "% Spent": "{:.1f}%",
            "% Committed": "{:.1f}%",
            "Budget FTE": "{:,.1f}",
            "Actual FTE": "{:,.1f}"
        }),
        use_container_width=True,
        height=400
    )

    dl_s1, dl_s2 = st.columns(2)
    with dl_s1:
        st.download_button(
            "📥 Summary to Excel",
            data=to_excel_download(bva_export, "BvA_Summary"),
            file_name=f"bva_summary_{summary_by.lower().replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with dl_s2:
        st.download_button(
            "📥 Summary to CSV",
            data=bva_export.to_csv(index=False),
            file_name=f"bva_summary_{summary_by.lower().replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )