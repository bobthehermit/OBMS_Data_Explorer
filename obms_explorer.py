"""
OBMS Financial Explorer v2
NM PED · School Budget Bureau
Reads parquet files from Google Drive (extracted from OBMS SSAS cubes via XMLA)

Tabs:
  1. Overview        – Executive snapshot per entity
  2. Budget Authority – Revenue & expenditure budget detail, BAR analysis, CSV export
  3. Actuals          – Quarterly actuals with full OBMS string (incl. Location), CSV export
  4. Salary & Benefits – FTE analysis, job class breakdown, contracted services
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime
import json
import numpy as np
import base64
from pathlib import Path
from PIL import Image

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="OBMS Financial Explorer",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Brand CSS (NMPED palette) ────────────────────────────────────────────────
# PED brand palette
#   Primary teal:  #245d62   Dark teal: #1a474b
#   Coral red:     #c64c43   Orange:    #f4784e
#   Gold:          #edc872   Lt yellow: #fef0c3
st.markdown("""
<style>
/* Layout */
.block-container { padding-top: .8rem !important; }

/* Metrics */
.stMetric {
    background: #fef0c3; padding: 14px; border-radius: 6px;
    border-left: 4px solid #245d62;
}
.stMetric label { color: #245d62 !important; font-weight: 600; font-size: .85rem; }
.stMetric [data-testid="stMetricValue"] {
    color: #245d62 !important; font-weight: 700; font-size: 1.7rem;
}

/* Headings */
h1, h2, h3 { color: #245d62; }

/* Download buttons */
.stDownloadButton button {
    width: 100%; background: #245d62; color: #fff !important;
}
.stDownloadButton button:hover { background: #1a474b; }
.stDownloadButton button p,
.stDownloadButton button span,
.stDownloadButton button:hover p,
.stDownloadButton button:hover span { color: #fff !important; }

/* Sidebar tags */
[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] {
    background: #245d62 !important; color: #fff !important;
}
[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] span { color: #fff !important; }
[data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"] svg  { fill: #fff !important; }

/* Links */
a { color: #c64c43; text-decoration: none; }
a:hover { color: #a03d35; text-decoration: underline; }

/* Section header */
.section-header {
    font-weight: 700;
    font-size: 1.1rem;
    color: #245d62;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 1.5rem 0 0.8rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 2px solid #245d62;
    display: inline-block;
}

/* App title in sidebar */
.app-title {
    font-weight: 700;
    font-size: 1.6rem;
    color: #245d62;
    margin-bottom: 0;
    line-height: 1.2;
}
.app-subtitle {
    font-size: 0.78rem;
    color: #666;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-top: 2px;
}

/* Expander details */
details {
    border: 1px solid #edc872 !important;
    border-radius: 8px !important;
}

/* Tab styling */
button[data-baseweb="tab"] {
    font-weight: 600;
    font-size: 0.9rem;
}
</style>
""", unsafe_allow_html=True)


# ── Plotly Theme (NMPED brand – light mode) ─────────────────────────────────
_PLOTLY_BASE = dict(
    font=dict(family="sans-serif", color="#333333"),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    colorway=["#245d62", "#c64c43", "#edc872", "#f4784e", "#1a474b",
               "#5a9ea3", "#8fae5f", "#d4956a", "#b85a3a", "#7a8c6e"],
    hoverlabel=dict(
        bgcolor="#ffffff",
        bordercolor="#245d62",
        font=dict(family="sans-serif", color="#333333", size=13)
    ),
)

# Kept as a spreadable dict for simple cases (no xaxis/yaxis/margin overrides)
PLOTLY_LAYOUT = {
    **_PLOTLY_BASE,
    "xaxis": dict(gridcolor="#e5e7eb", zerolinecolor="#d1d5db"),
    "yaxis": dict(gridcolor="#e5e7eb", zerolinecolor="#d1d5db"),
    "margin": dict(l=40, r=20, t=50, b=40),
}


def plotly_layout(**overrides):
    """Return layout dict with defaults. Overrides replace conflicting keys."""
    base = dict(PLOTLY_LAYOUT)
    base.update(overrides)
    return base


# ── Fund Classification ─────────────────────────────────────────────────────
FUND_CLASSIFICATION = {
    "11": "Non-Reimbursable", "13": "Non-Reimbursable", "14": "Non-Reimbursable",
    "21": "Non-Reimbursable", "23": "Non-Reimbursable",
    "31": "Non-Reimbursable", "32": "Non-Reimbursable",
    "41": "Non-Reimbursable", "42": "Non-Reimbursable", "43": "Non-Reimbursable",
    "24": "Reimbursable", "25": "Reimbursable", "26": "Reimbursable",
    "27": "Reimbursable", "28": "Reimbursable", "29": "Reimbursable",
}


def classify_fund(fund_str):
    code = extract_code(str(fund_str))
    for prefix, classification in FUND_CLASSIFICATION.items():
        if code.startswith(prefix):
            return classification
    return "Other"


# ── Google Drive File Registry ───────────────────────────────────────────────
GDRIVE_FILES = {
    "actuals_0607": "1tRjPX98VYEU9hA8KpOxoe4g16gz7XzF7",
    "actuals_0708": "1O02w9W496AGDy6RiNCO3jcDRas6S5wc8",
    "actuals_0809": "17Qwl1VERONBkkjJ8cQi_8KuBJfg-Ob3N",
    "actuals_0910": "1YSkyrCXUoq7LdxaVXjkjbQqmrxvX0QrA",
    "actuals_1011": "1xEYOm1NdCWmDHMbVDAsCk1KvAiAOvRBK",
    "actuals_1112": "1uASQYCiKVarfgOy8-XrOHGGTqWrGSEQJ",
    "actuals_1213": "19iBG7QTUSi-sJ5gkM6ywHpncAxfv5vMv",
    "actuals_1314": "1wHFoDeJ-npoe-NV4pye-wzzUgvVGBqRO",
    "actuals_1415": "1WeizvDpLmgRtTsbQjB6uIx-iab0mZDCi",
    "actuals_1516": "1WqKeUBuAR67_Qc9nOst9WsYo_V5wxQ5k",
    "actuals_1617": "1vk98bONVcVlXWOs-bxBGAHBdXYX-B_n6",
    "actuals_1718": "1N2c58Vtz9qdNpJclJZ6_dKodYsyWFBwD",
    "actuals_1819": "1eOwagVlJEpXxKxcVYoa765LCXyL7xfw9",
    "actuals_1920": "1fx3zenr3wco4O9EMsGxAVguWNMcUhW77",
    "actuals_2021": "12z0mb7jLnx9jWf7QnGlm5dcy8lDgjJR5",
    "actuals_2122": "1oIwcfntBqCQKjCfKqMwu2AtFsxt0P1u2",
    "actuals_2223": "1WHzdvgqZT_ZjerGZHoqtkv46ScNnPi54",
    "actuals_2324": "15aR7lFEuj-NvF33L22GsWe0guI4Hyzrp",
    "actuals_2425": "1FZsV_4CKhPhl8kFFdG4IodTv8XRe3_Sz",
    "actuals_2526": "1B1VTimEWzn7m0rY1Y_UjDbobb4dBtzUg",
    "budget_0607": "132sgPwq4mTX2uTk_pJbna_WwM2uGm9P2",
    "budget_0708": "1hxS4Zs8qnkbmtz37Cya8YjFmUdurt2TB",
    "budget_0809": "19d8C_OlO1pbbpe9TGnGVlNPqAJUDFzXC",
    "budget_0910": "1tIIRnzmC9uXo2PdYdvDqK0NnJgFOgGof",
    "budget_1011": "1H-TarWgSu5rGH-cYc_URed5efLVWmsro",
    "budget_1112": "1gOqbXOB1BF0yVWPDvMQySfR91zc70WKm",
    "budget_1213": "1UI24Z4v56zBvWjKD70OTT9GEYMI2v4pp",
    "budget_1314": "1kB8YjcUpTNyPgWcF0ZPregpMT-MhwlYq",
    "budget_1415": "1eYTODQTUUB9iEsPV1d36clqLcJKCxBBd",
    "budget_1516": "1Myvm8NhO_kZ6OFSSBtV231qRtm0m0N9P",
    "budget_1617": "1yfAX5KTGPJPB25BlU6sDUoy4BxnDRxJr",
    "budget_1718": "1czetBYrHTASpNqiqXBCeB1jpkBI0vBj_",
    "budget_1819": "1VD8SQJV_IbKM870FwELpTPb6zPUi5tLq",
    "budget_1920": "1GHqpE_iu3kvW0iK2817jnFANsMSmyUJ4",
    "budget_2021": "1xwDyqRDazGpLxR4R95ON7XK4LVxSvTQN",
    "budget_2122": "1ytOcoRjqSWYeRBlfJ14n6nfbOSF7J0Xx",
    "budget_2223": "1ghFHKCBnXPRklO1piSLEh-HXnUMUZz9K",
    "budget_2324": "1S0Ru87FcSenACF2_MARn0aqLpfdFfGYM",
    "budget_2425": "19G--IZmrAH2qkmwZlGm4Lm598Ee0MMsH",
    "budget_2526": "1Wt1vuIJCn16r5vZA_NKPSaxfsvKu10mN",
}


def gdrive_download_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"


# ── Fiscal Year Helpers ──────────────────────────────────────────────────────
ALL_FY_CODES = sorted(set(k.split("_")[1] for k in GDRIVE_FILES.keys()))

def fy_key_to_code(fy_key: int) -> str:
    return f"{(fy_key-1) % 100:02d}{fy_key % 100:02d}"

def fy_code_to_key(fy_code: str) -> int:
    return 2000 + int(fy_code[2:4])

ALL_FY_KEYS = sorted([fy_code_to_key(c) for c in ALL_FY_CODES])
FY_LABELS = {k: f"{k-1}–{k}" for k in ALL_FY_KEYS}


@st.cache_data(ttl=3600)
def load_single_parquet(file_key: str) -> pd.DataFrame:
    file_id = GDRIVE_FILES.get(file_key)
    if not file_id:
        return pd.DataFrame()
    try:
        return pd.read_parquet(gdrive_download_url(file_id))
    except Exception as e:
        st.warning(f"Failed to load {file_key}: {e}")
        return pd.DataFrame()


def load_data_for_years(fy_keys: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    actuals_dfs, budget_dfs = [], []
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


def fmt_acct_currency(val):
    """Format currency for accounting exports: $1,234.56 or ($1,234.56) for negatives."""
    if pd.isna(val):
        return ""
    if val < 0:
        return f"(${abs(val):,.2f})"
    return f"${val:,.2f}"


def fmt_pct(val):
    if pd.isna(val) or val == float('inf') or val == float('-inf'):
        return "N/A"
    return f"{val:.1f}%"


def extract_code(text):
    if pd.isna(text):
        return ""
    return str(text).split(" - ", 1)[0].strip()


def extract_name(text):
    if pd.isna(text):
        return ""
    parts = str(text).split(" - ", 1)
    return parts[1].strip() if len(parts) > 1 else parts[0].strip()


def to_excel_download(df, sheet_name="Data"):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()


# ── OBMS Dimension Columns ──────────────────────────────────────────────────
# Full OBMS string: Fund, Function, Object, Program, Location, Job Class
OBMS_DIMS = ["Budget Entity", "Fund", "Function", "Object", "Program", "Location", "Job Class"]
# Filterable dimensions (excludes entity which is global)
FILTER_DIMS = ["Fund", "Function", "Object", "Program", "Location", "Job Class"]


def get_unique_values(act_df, bud_df, col):
    """Get sorted unique values for a dimension across both datasets."""
    vals = set()
    if len(act_df) > 0 and col in act_df.columns:
        vals.update(act_df[col].dropna().unique())
    if len(bud_df) > 0 and col in bud_df.columns:
        vals.update(bud_df[col].dropna().unique())
    return sorted(vals)


def apply_dim_filters(df, filters: dict) -> pd.DataFrame:
    """Apply a dictionary of {column: [values]} filters to a DataFrame."""
    if len(df) == 0:
        return df
    for col, vals in filters.items():
        if vals and col in df.columns:
            df = df[df[col].isin(vals)]
    return df


# ══════════════════════════════════════════════════════════════════════════════
# BUDGET AUTHORITY REPORT BUILDER
# ══════════════════════════════════════════════════════════════════════════════
def build_budget_report(bud_df, entity_name, account_type):
    """
    Build budget authority CSV matching the exact format:
    Entity, Fund, Function, Object, Program, Location, JobClass,
    Beginning Budget, Beginning FTE, Adjustment Amount, Adjustment FTE,
    Adjusted Budget, Adjusted FTE
    """
    b = bud_df[
        (bud_df["Budget Entity"] == entity_name) &
        (bud_df["Account Type"] == account_type)
    ].copy()

    if len(b) == 0:
        return pd.DataFrame(columns=[
            "Entity", "Fund", "Function", "Object", "Program", "Location", "JobClass",
            "Beginning Budget", "Beginning FTE", "Adjustment Amount", "Adjustment FTE",
            "Adjusted Budget", "Adjusted FTE"
        ])

    agg = b.groupby(OBMS_DIMS, dropna=False).agg(
        beg_budget=("Final Amt", "sum"),
        beg_fte=("Final FTE", "sum"),
        adj_amt=("Adjustment Amt", "sum"),
        adj_fte=("Adjustment FTE", "sum"),
        adj_budget=("Adjusted Amt", "sum"),
        adjusted_fte=("Adjusted FTE", "sum"),
    ).reset_index()

    agg = agg.sort_values(OBMS_DIMS).reset_index(drop=True)

    report = pd.DataFrame()
    report["Entity"] = agg["Budget Entity"]
    report["Fund"] = agg["Fund"]
    report["Function"] = agg["Function"]
    report["Object"] = agg["Object"]
    report["Program"] = agg["Program"]
    report["Location"] = agg["Location"]
    report["JobClass"] = agg["Job Class"]
    report["Beginning Budget"] = agg["beg_budget"].apply(fmt_acct_currency)
    report["Beginning FTE"] = agg["beg_fte"].apply(lambda v: f"{v:.2f}")
    report["Adjustment Amount"] = agg["adj_amt"].apply(fmt_acct_currency)
    report["Adjustment FTE"] = agg["adj_fte"].apply(lambda v: f"{v:.2f}")
    report["Adjusted Budget"] = agg["adj_budget"].apply(fmt_acct_currency)
    report["Adjusted FTE"] = agg["adjusted_fte"].apply(lambda v: f"{v:.2f}")

    return report


# ══════════════════════════════════════════════════════════════════════════════
# ACTUALS REPORT BUILDER (updated with Location)
# ══════════════════════════════════════════════════════════════════════════════
ACTUALS_CSV_COLS = [
    "Entity", "Fund", "Function", "Object", "Program", "Location", "JobClass",
    "Actuals Period Amount", "Actuals YTD", "Encumbrance", "Actuals FTE",
    "Adjusted Budget", "Adjusted FTE", "Available Balance", "Burn % (Actuals + Enc)"
]


def build_actuals_report(act_df, bud_df, entity_name, account_type):
    """Build line-item actuals report with full OBMS string including Location."""
    act = act_df[
        (act_df["Budget Entity"] == entity_name) &
        (act_df["Account Type"] == account_type)
    ].copy()

    bud = bud_df[
        (bud_df["Budget Entity"] == entity_name) &
        (bud_df["Account Type"] == account_type)
    ].copy()

    if len(act) == 0 and len(bud) == 0:
        return pd.DataFrame(columns=ACTUALS_CSV_COLS)

    if len(act) > 0:
        a_agg = act.groupby(OBMS_DIMS, dropna=False).agg(
            period_amt=("Actuals Period Amount", "sum"),
            ytd_amt=("Actuals YTDAmount", "sum"),
            enc_amt=("Actuals Encumbrance", "sum"),
            act_fte=("Actuals FTE", "sum"),
        ).reset_index()
    else:
        a_agg = pd.DataFrame(columns=OBMS_DIMS + ["period_amt", "ytd_amt", "enc_amt", "act_fte"])

    if len(bud) > 0:
        b_agg = bud.groupby(OBMS_DIMS, dropna=False).agg(
            adj_budget=("Adjusted Amt", "sum"),
            adj_fte=("Adjusted FTE", "sum"),
        ).reset_index()
    else:
        b_agg = pd.DataFrame(columns=OBMS_DIMS + ["adj_budget", "adj_fte"])

    merged = b_agg.merge(a_agg, on=OBMS_DIMS, how="outer")

    merged["avail_balance"] = (
        merged["adj_budget"].fillna(0)
        - merged["ytd_amt"].fillna(0)
        - merged["enc_amt"].fillna(0)
    )

    has_budget = merged["adj_budget"].notna() & (merged["adj_budget"] != 0)
    has_actuals = merged["ytd_amt"].notna() | merged["enc_amt"].notna()
    merged["burn_pct"] = pd.NA
    mask = has_actuals & has_budget
    merged.loc[mask, "burn_pct"] = (
        (merged.loc[mask, "ytd_amt"].fillna(0) + merged.loc[mask, "enc_amt"].fillna(0))
        / merged.loc[mask, "adj_budget"] * 100
    )

    merged = merged.sort_values(OBMS_DIMS).reset_index(drop=True)

    report = pd.DataFrame()
    report["Entity"] = merged["Budget Entity"]
    report["Fund"] = merged["Fund"]
    report["Function"] = merged["Function"]
    report["Object"] = merged["Object"]
    report["Program"] = merged["Program"]
    report["Location"] = merged["Location"]
    report["JobClass"] = merged["Job Class"]

    report["Actuals Period Amount"] = merged["period_amt"].apply(
        lambda v: fmt_acct_currency(v) if pd.notna(v) and v != 0 else ("" if pd.isna(v) else fmt_acct_currency(v))
    )
    report["Actuals YTD"] = merged["ytd_amt"].apply(
        lambda v: fmt_acct_currency(v) if pd.notna(v) and v != 0 else ("" if pd.isna(v) else fmt_acct_currency(v))
    )
    report["Encumbrance"] = merged["enc_amt"].apply(
        lambda v: fmt_acct_currency(v) if pd.notna(v) and v != 0 else ("" if pd.isna(v) else fmt_acct_currency(v))
    )
    report["Actuals FTE"] = merged["act_fte"].apply(
        lambda v: "" if pd.isna(v) else f"{v:.2f}" if v != 0 else "0.00"
    )
    report["Adjusted Budget"] = merged["adj_budget"].apply(
        lambda v: fmt_acct_currency(v) if pd.notna(v) else ""
    )
    report["Adjusted FTE"] = merged["adj_fte"].apply(
        lambda v: "" if pd.isna(v) else f"{v:.2f}" if v != 0 else "0.00"
    )
    report["Available Balance"] = merged["avail_balance"].apply(fmt_acct_currency)
    report["Burn % (Actuals + Enc)"] = merged["burn_pct"].apply(
        lambda v: "" if pd.isna(v) else f"{v:.2f}%"
    )

    # Blank out actuals cols for budget-only rows
    budget_only = ~has_actuals
    for col in ["Actuals Period Amount", "Actuals YTD", "Encumbrance", "Actuals FTE"]:
        report.loc[budget_only, col] = ""

    actuals_only = ~has_budget
    for col in ["Adjusted Budget", "Adjusted FTE"]:
        report.loc[actuals_only, col] = ""

    return report


# ══════════════════════════════════════════════════════════════════════════════
# SALARY / BENEFITS CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════
# Object codes 51xxx = Salaries, 52xxx = Benefits, 53xxx = Contracted Services
def classify_object_category(obj_str):
    code = extract_code(str(obj_str))
    if code.startswith("51"):
        return "Salaries"
    elif code.startswith("52"):
        return "Benefits"
    elif code.startswith("53"):
        return "Contracted Services"
    elif code.startswith("54"):
        return "Other Purchased Services"
    elif code.startswith("55"):
        return "Supplies"
    elif code.startswith("56"):
        return "Property"
    else:
        return "Other"


def classify_function_category(func_str):
    code = extract_code(str(func_str))
    if code.startswith("1"):
        return "Instruction"
    elif code.startswith("21"):
        return "Support - Students"
    elif code.startswith("22"):
        return "Support - Instruction"
    elif code.startswith("23"):
        return "General Administration"
    elif code.startswith("24"):
        return "School Administration"
    elif code.startswith("25"):
        return "Central Services"
    elif code.startswith("26"):
        return "Operations & Maintenance"
    elif code.startswith("27"):
        return "Student Transportation"
    elif code.startswith("3"):
        return "Food Services"
    elif code.startswith("4"):
        return "Capital Outlay"
    elif code.startswith("5"):
        return "Debt Service"
    else:
        return "Other"


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR: Global Filters (Entity + FY + Period)
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    # ── Logo ──────────────────────────────────────────────────────────────
    LOGO_PATH = Path(__file__).parent / "300 DPI NM PED Logo JPEG.jpg"
    LOGO_LINK = "https://web.ped.nm.gov/bureaus/school-budget-bureau/"

    def _load_logo():
        if not LOGO_PATH.exists():
            return None
        try:
            buf = BytesIO()
            Image.open(LOGO_PATH).save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            return (
                f'<a href="{LOGO_LINK}" target="_blank">'
                f'<img src="data:image/png;base64,{b64}" '
                f'style="max-height:90px;height:auto;max-width:100%"></a>'
            )
        except Exception:
            return None

    logo = _load_logo()
    if logo:
        st.markdown(logo, unsafe_allow_html=True)
    st.caption("School Budget Bureau")
    st.markdown("---")

    fy_options = sorted(ALL_FY_KEYS, reverse=True)
    selected_fy = [st.selectbox(
        "Fiscal Year",
        options=fy_options,
        index=0,
        format_func=lambda x: FY_LABELS.get(x, str(x))
    )]

if not selected_fy:
    st.warning("Select at least one fiscal year.")
    st.stop()

act_raw, bud_raw = load_data_for_years(selected_fy)

if len(act_raw) == 0 and len(bud_raw) == 0:
    st.error("No data loaded. Check that Google Drive files are publicly shared.")
    st.stop()

with st.sidebar:
    # Period selector
    available_periods = sorted(
        act_raw["Reporting Period"].unique()
    ) if len(act_raw) > 0 else []

    if available_periods:
        selected_period = st.selectbox(
            "Reporting Period",
            options=available_periods,
            index=len(available_periods) - 1,
            help="YTD amounts are cumulative through this quarter."
        )
    else:
        selected_period = None

    st.markdown("---")

    # Entity selector (global — applies to all tabs)
    all_entities = sorted(get_unique_values(act_raw, bud_raw, "Budget Entity"))
    selected_entity = st.selectbox(
        "Budget Entity",
        options=["— All Entities —"] + all_entities,
        index=0,
        help="Select a specific district or charter school, or view all."
    )

    st.markdown("---")
    act_count = len(act_raw)
    bud_count = len(bud_raw)
    st.caption(f"📁 {act_count:,} actuals · {bud_count:,} budget rows · {len(selected_fy)} FY(s)")
    st.caption(f"☁️ Data source: Google Drive parquet files")


# ── Apply global entity filter to raw data ───────────────────────────────────
if selected_entity != "— All Entities —":
    act_global = act_raw[act_raw["Budget Entity"] == selected_entity].copy()
    bud_global = bud_raw[bud_raw["Budget Entity"] == selected_entity].copy()
else:
    act_global = act_raw.copy()
    bud_global = bud_raw.copy()

# Apply period filter to actuals
if selected_period and len(act_global) > 0:
    act_global = act_global[act_global["Reporting Period"] == selected_period]

# Context labels
fy_label = ", ".join(FY_LABELS.get(k, str(k)) for k in selected_fy)
period_label = selected_period if selected_period else "All Periods"
entity_label = selected_entity if selected_entity != "— All Entities —" else "All Entities"


# ── Inline Tab Filter Helper ────────────────────────────────────────────────
def render_tab_filters(tab_key: str, act_df: pd.DataFrame, bud_df: pd.DataFrame,
                       dims: list[str] = None, show_acct_type: bool = False):
    """
    Render inline dimensional filters for a tab.
    Returns (filtered_act, filtered_bud, account_type_selection).
    """
    if dims is None:
        dims = FILTER_DIMS

    filters = {}
    acct_type = None

    cols = st.columns(min(len(dims) + (1 if show_acct_type else 0), 4))
    col_idx = 0

    if show_acct_type:
        with cols[col_idx % len(cols)]:
            acct_type = st.radio(
                "Account Type",
                options=["E", "R"],
                format_func=lambda x: "Expenditure" if x == "E" else "Revenue",
                index=0,
                horizontal=True,
                key=f"{tab_key}_acct_type"
            )
        col_idx += 1

    # If more dims than columns, use an expander
    if len(dims) <= 3:
        for dim in dims:
            with cols[col_idx % len(cols)]:
                vals = get_unique_values(act_df, bud_df, dim)
                selected = st.multiselect(dim, options=vals, default=[], key=f"{tab_key}_{dim}")
                if selected:
                    filters[dim] = selected
            col_idx += 1
    else:
        with st.expander("🔍 Dimension Filters", expanded=False):
            fcols = st.columns(3)
            for i, dim in enumerate(dims):
                with fcols[i % 3]:
                    vals = get_unique_values(act_df, bud_df, dim)
                    selected = st.multiselect(dim, options=vals, default=[], key=f"{tab_key}_{dim}")
                    if selected:
                        filters[dim] = selected

    a = apply_dim_filters(act_df, filters)
    b = apply_dim_filters(bud_df, filters)

    if acct_type:
        if len(a) > 0 and "Account Type" in a.columns:
            a = a[a["Account Type"] == acct_type]
        if len(b) > 0 and "Account Type" in b.columns:
            b = b[b["Account Type"] == acct_type]

    return a, b, acct_type


# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="margin-bottom: 0.5rem;">
    <span class="app-title" style="font-size: 1.3rem;">OBMS Financial Explorer</span>
    <span style="color: #666; font-size: 0.85rem; margin-left: 12px;">
        {entity_label} · {fy_label} · {period_label}
    </span>
</div>
""", unsafe_allow_html=True)


# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_overview, tab_budget, tab_actuals, tab_salary = st.tabs([
    "📊 Overview", "📋 Budget Authority", "📈 Actuals", "👥 Salary & Benefits"
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
with tab_overview:

    # Revenue side totals
    rev_bud = bud_global[bud_global["Account Type"] == "R"] if len(bud_global) > 0 else pd.DataFrame()
    rev_act = act_global[act_global["Account Type"] == "R"] if len(act_global) > 0 else pd.DataFrame()
    exp_bud = bud_global[bud_global["Account Type"] == "E"] if len(bud_global) > 0 else pd.DataFrame()
    exp_act = act_global[act_global["Account Type"] == "E"] if len(act_global) > 0 else pd.DataFrame()

    rev_budget_total = rev_bud["Adjusted Amt"].sum() if len(rev_bud) > 0 else 0
    rev_ytd_total = rev_act["Actuals YTDAmount"].sum() if len(rev_act) > 0 else 0
    exp_budget_total = exp_bud["Adjusted Amt"].sum() if len(exp_bud) > 0 else 0
    exp_ytd_total = exp_act["Actuals YTDAmount"].sum() if len(exp_act) > 0 else 0
    exp_enc_total = exp_act["Actuals Encumbrance"].sum() if len(exp_act) > 0 else 0
    exp_balance = exp_budget_total - exp_ytd_total - exp_enc_total
    net_ytd = rev_ytd_total - exp_ytd_total

    # KPI Cards
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Revenue Budget", fmt_currency(rev_budget_total, compact=True))
    k2.metric("Revenue YTD", fmt_currency(rev_ytd_total, compact=True))
    k3.metric("Expenditure Budget", fmt_currency(exp_budget_total, compact=True))
    k4.metric("Expenditure YTD", fmt_currency(exp_ytd_total, compact=True))
    k5.metric("Encumbrance", fmt_currency(exp_enc_total, compact=True))
    k6.metric("Net (Rev − Exp YTD)", fmt_currency(net_ytd, compact=True))

    st.markdown("---")

    # ── Revenue vs Expenditure by Fund ───────────────────────────────────
    st.markdown('<div class="section-header">Revenue vs. Expenditure by Fund</div>', unsafe_allow_html=True)

    rev_by_fund = rev_act.groupby("Fund").agg(
        Revenue_YTD=("Actuals YTDAmount", "sum")
    ).reset_index() if len(rev_act) > 0 else pd.DataFrame(columns=["Fund", "Revenue_YTD"])

    exp_by_fund = exp_act.groupby("Fund").agg(
        Expenditure_YTD=("Actuals YTDAmount", "sum")
    ).reset_index() if len(exp_act) > 0 else pd.DataFrame(columns=["Fund", "Expenditure_YTD"])

    fund_merged = rev_by_fund.merge(exp_by_fund, on="Fund", how="outer").fillna(0)
    fund_merged["Net"] = fund_merged["Revenue_YTD"] - fund_merged["Expenditure_YTD"]
    fund_merged["Total_Activity"] = fund_merged["Revenue_YTD"].abs() + fund_merged["Expenditure_YTD"].abs()
    fund_merged["Fund_Name"] = fund_merged["Fund"].apply(extract_name)
    fund_merged["Fund_Class"] = fund_merged["Fund"].apply(classify_fund)
    fund_merged = fund_merged.sort_values("Total_Activity", ascending=False)

    if len(fund_merged) > 0:
        top_chart = fund_merged.head(12)
        fig_revexp = go.Figure()
        fig_revexp.add_trace(go.Bar(
            name="Revenue YTD", x=top_chart["Fund_Name"], y=top_chart["Revenue_YTD"],
            marker_color="#245d62",
            hovertemplate="%{x}<br>Revenue: $%{y:,.0f}<extra></extra>"
        ))
        fig_revexp.add_trace(go.Bar(
            name="Expenditure YTD", x=top_chart["Fund_Name"], y=top_chart["Expenditure_YTD"],
            marker_color="#edc872",
            hovertemplate="%{x}<br>Expenditure: $%{y:,.0f}<extra></extra>"
        ))
        fig_revexp.update_layout(
            **plotly_layout(barmode="group", height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis_tickangle=-30, yaxis_title="")
        )
        st.plotly_chart(fig_revexp, use_container_width=True)

    # ── Funds where expenditures exceed revenue ──────────────────────────
    deficit_funds = fund_merged[fund_merged["Net"] < 0].copy()
    deficit_funds["Deficit"] = deficit_funds["Net"].abs()

    if len(deficit_funds) > 0:
        st.markdown('<div class="section-header">Funds: Expenditures Exceed Revenue</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)

        non_reimb = deficit_funds[deficit_funds["Fund_Class"] == "Non-Reimbursable"]
        reimb = deficit_funds[deficit_funds["Fund_Class"] == "Reimbursable"]

        with c1:
            st.markdown("**Non-Reimbursable** _(cash concern)_")
            if len(non_reimb) > 0:
                nr = non_reimb[["Fund", "Revenue_YTD", "Expenditure_YTD", "Net"]].copy()
                nr.columns = ["Fund", "Revenue YTD", "Expenditure YTD", "Net"]
                st.dataframe(nr.style.format({
                    "Revenue YTD": "${:,.0f}", "Expenditure YTD": "${:,.0f}", "Net": "${:,.0f}"
                }), use_container_width=True, height=min(300, len(non_reimb) * 40 + 60))
            else:
                st.success("No non-reimbursable fund deficits.")

        with c2:
            st.markdown("**Reimbursable** _(expected: spend first, reimburse later)_")
            if len(reimb) > 0:
                r = reimb[["Fund", "Revenue_YTD", "Expenditure_YTD", "Net"]].copy()
                r.columns = ["Fund", "Revenue YTD", "Expenditure YTD", "Net"]
                st.dataframe(r.style.format({
                    "Revenue YTD": "${:,.0f}", "Expenditure YTD": "${:,.0f}", "Net": "${:,.0f}"
                }), use_container_width=True, height=min(300, len(reimb) * 40 + 60))
            else:
                st.info("No reimbursable fund deficits.")

    # ── Budget Execution Gauges ──────────────────────────────────────────
    st.markdown('<div class="section-header">Budget Execution</div>', unsafe_allow_html=True)

    if selected_period and selected_period.startswith("Q"):
        quarter_num = int(selected_period[1:])
        expected_pct = quarter_num * 25
    else:
        expected_pct = 50

    exp_pct_spent = (exp_ytd_total / exp_budget_total * 100) if exp_budget_total else 0
    exp_pct_committed = ((exp_ytd_total + exp_enc_total) / exp_budget_total * 100) if exp_budget_total else 0
    rev_pct_collected = (rev_ytd_total / rev_budget_total * 100) if rev_budget_total else 0

    g1, g2, g3 = st.columns(3)

    with g1:
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=exp_pct_spent,
            number={"suffix": "%", "font": {"size": 36, "family": "JetBrains Mono"}},
            delta={"reference": expected_pct, "suffix": "%", "relative": False},
            title={"text": "Exp. % Spent vs Expected", "font": {"size": 14}},
            gauge={
                "axis": {"range": [0, 100], "ticksuffix": "%"},
                "bar": {"color": "#245d62"}, "bgcolor": "#fef0c3",
                "steps": [{"range": [0, expected_pct], "color": "#f5f5f5"},
                          {"range": [expected_pct, 100], "color": "#1a1a2e"}],
                "threshold": {"line": {"color": "#edc872", "width": 3},
                              "thickness": 0.8, "value": expected_pct}
            }
        ))
        fig_g.update_layout(**plotly_layout(height=250, margin=dict(l=30, r=30, t=60, b=20)))
        st.plotly_chart(fig_g, use_container_width=True)

    with g2:
        fig_g2 = go.Figure(go.Indicator(
            mode="gauge+number",
            value=exp_pct_committed,
            number={"suffix": "%", "font": {"size": 36, "family": "JetBrains Mono"}},
            title={"text": "Exp. % Committed (YTD + Enc)", "font": {"size": 14}},
            gauge={
                "axis": {"range": [0, 120], "ticksuffix": "%"},
                "bar": {"color": "#c64c43"}, "bgcolor": "#fef0c3",
                "steps": [{"range": [0, 100], "color": "#f5f5f5"},
                          {"range": [100, 120], "color": "#3d1515"}],
                "threshold": {"line": {"color": "#f4784e", "width": 3},
                              "thickness": 0.8, "value": 100}
            }
        ))
        fig_g2.update_layout(**plotly_layout(height=250, margin=dict(l=30, r=30, t=60, b=20)))
        st.plotly_chart(fig_g2, use_container_width=True)

    with g3:
        fig_g3 = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=rev_pct_collected,
            number={"suffix": "%", "font": {"size": 36, "family": "JetBrains Mono"}},
            delta={"reference": expected_pct, "suffix": "%", "relative": False},
            title={"text": "Revenue % Collected vs Expected", "font": {"size": 14}},
            gauge={
                "axis": {"range": [0, 120], "ticksuffix": "%"},
                "bar": {"color": "#8fae5f"}, "bgcolor": "#fef0c3",
                "steps": [{"range": [0, expected_pct], "color": "#f5f5f5"},
                          {"range": [expected_pct, 120], "color": "#1a1a2e"}],
                "threshold": {"line": {"color": "#edc872", "width": 3},
                              "thickness": 0.8, "value": expected_pct}
            }
        ))
        fig_g3.update_layout(**plotly_layout(height=250, margin=dict(l=30, r=30, t=60, b=20)))
        st.plotly_chart(fig_g3, use_container_width=True)

    # ── Expenditure by Function (treemap) ────────────────────────────────
    st.markdown('<div class="section-header">Expenditure by Function</div>', unsafe_allow_html=True)

    if len(exp_act) > 0:
        func_exp = exp_act.groupby("Function").agg(
            YTD=("Actuals YTDAmount", "sum")
        ).reset_index()
        func_exp["Name"] = func_exp["Function"].apply(extract_name)
        func_exp = func_exp[func_exp["YTD"] > 0].sort_values("YTD", ascending=False)

        func_bud_agg = exp_bud.groupby("Function").agg(
            Budget=("Adjusted Amt", "sum")
        ).reset_index() if len(exp_bud) > 0 else pd.DataFrame(columns=["Function", "Budget"])

        func_merged = func_exp.merge(func_bud_agg, on="Function", how="left").fillna(0)
        func_merged["Pct_Spent"] = (func_merged["YTD"] / func_merged["Budget"].replace(0, np.nan) * 100)

        if len(func_merged) > 0:
            fig_tree = go.Figure(go.Treemap(
                labels=func_merged["Name"].head(12),
                values=func_merged["YTD"].head(12),
                parents=[""] * min(12, len(func_merged)),
                textinfo="label+value+percent root",
                texttemplate="%{label}<br>$%{value:,.0f}<br>%{percentRoot:.1%}",
                marker=dict(
                    colors=func_merged["Pct_Spent"].head(12).fillna(0),
                    colorscale=[[0, "#245d62"], [0.5, "#edc872"], [1, "#c64c43"]],
                    showscale=True,
                    colorbar=dict(title="% Spent", ticksuffix="%")
                ),
                hovertemplate="%{label}<br>YTD: $%{value:,.0f}<br>% Spent: %{color:.1f}%<extra></extra>"
            ))
            fig_tree.update_layout(**plotly_layout(height=420, margin=dict(l=10, r=10, t=30, b=10)))
            st.plotly_chart(fig_tree, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: BUDGET AUTHORITY
# ══════════════════════════════════════════════════════════════════════════════
with tab_budget:

    st.markdown('<div class="section-header">Budget Authority Analysis</div>', unsafe_allow_html=True)

    bud_act_f, bud_bud_f, bud_acct_type = render_tab_filters(
        "budget", act_global, bud_global, dims=FILTER_DIMS, show_acct_type=True
    )
    bud_acct_label = "Expenditure" if bud_acct_type == "E" else "Revenue"

    # ── Summary KPIs ─────────────────────────────────────────────────────
    beg_total = bud_bud_f["Final Amt"].sum() if len(bud_bud_f) > 0 else 0
    adj_amt_total = bud_bud_f["Adjustment Amt"].sum() if len(bud_bud_f) > 0 else 0
    adj_bud_total = bud_bud_f["Adjusted Amt"].sum() if len(bud_bud_f) > 0 else 0
    beg_fte_total = bud_bud_f["Final FTE"].sum() if len(bud_bud_f) > 0 else 0
    adj_fte_total = bud_bud_f["Adjusted FTE"].sum() if len(bud_bud_f) > 0 else 0

    bk1, bk2, bk3, bk4, bk5 = st.columns(5)
    bk1.metric("Beginning Budget", fmt_currency(beg_total, compact=True))
    bk2.metric("BAR Adjustments", fmt_currency(adj_amt_total, compact=True))
    bk3.metric("Adjusted Budget", fmt_currency(adj_bud_total, compact=True))
    bk4.metric("Beginning FTE", f"{beg_fte_total:,.1f}")
    bk5.metric("Adjusted FTE", f"{adj_fte_total:,.1f}")

    st.markdown("---")

    # ── Revenue Budget vs Expenditure Budget ─────────────────────────────
    st.markdown("#### Revenue Budget vs. Expenditure Budget")
    st.caption(
        "Revenue and expenditure budgets must balance. This shows where approved "
        "budget authority is allocated across revenue sources and expenditure categories."
    )

    rev_bud_tab = bud_global[bud_global["Account Type"] == "R"] if len(bud_global) > 0 else pd.DataFrame()
    exp_bud_tab = bud_global[bud_global["Account Type"] == "E"] if len(bud_global) > 0 else pd.DataFrame()

    rb1, rb2 = st.columns(2)

    with rb1:
        st.markdown("**Revenue Budget by Fund**")
        if len(rev_bud_tab) > 0:
            rev_by_fund_bud = rev_bud_tab.groupby("Fund").agg(
                Beginning=("Final Amt", "sum"),
                Adjustments=("Adjustment Amt", "sum"),
                Adjusted=("Adjusted Amt", "sum"),
            ).reset_index().sort_values("Adjusted", ascending=False)
            rev_by_fund_bud["Fund_Name"] = rev_by_fund_bud["Fund"].apply(extract_name)

            fig_rev_bud = go.Figure()
            fig_rev_bud.add_trace(go.Bar(
                name="Beginning", y=rev_by_fund_bud["Fund_Name"].head(10),
                x=rev_by_fund_bud["Beginning"].head(10),
                orientation="h", marker_color="#245d62",
                hovertemplate="%{y}<br>Beginning: $%{x:,.0f}<extra></extra>"
            ))
            fig_rev_bud.add_trace(go.Bar(
                name="BAR Adjustments", y=rev_by_fund_bud["Fund_Name"].head(10),
                x=rev_by_fund_bud["Adjustments"].head(10),
                orientation="h", marker_color="#c64c43",
                hovertemplate="%{y}<br>Adjustments: $%{x:,.0f}<extra></extra>"
            ))
            fig_rev_bud.update_layout(
                **plotly_layout(barmode="stack", height=400,
                yaxis=dict(autorange="reversed", gridcolor="#e5e7eb"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)),
            )
            st.plotly_chart(fig_rev_bud, use_container_width=True)
        else:
            st.info("No revenue budget data.")

    with rb2:
        st.markdown("**Expenditure Budget by Function**")
        if len(exp_bud_tab) > 0:
            exp_by_func_bud = exp_bud_tab.groupby("Function").agg(
                Beginning=("Final Amt", "sum"),
                Adjustments=("Adjustment Amt", "sum"),
                Adjusted=("Adjusted Amt", "sum"),
            ).reset_index().sort_values("Adjusted", ascending=False)
            exp_by_func_bud["Func_Name"] = exp_by_func_bud["Function"].apply(extract_name)

            fig_exp_bud = go.Figure()
            fig_exp_bud.add_trace(go.Bar(
                name="Beginning", y=exp_by_func_bud["Func_Name"].head(10),
                x=exp_by_func_bud["Beginning"].head(10),
                orientation="h", marker_color="#edc872",
                hovertemplate="%{y}<br>Beginning: $%{x:,.0f}<extra></extra>"
            ))
            fig_exp_bud.add_trace(go.Bar(
                name="BAR Adjustments", y=exp_by_func_bud["Func_Name"].head(10),
                x=exp_by_func_bud["Adjustments"].head(10),
                orientation="h", marker_color="#f4784e",
                hovertemplate="%{y}<br>Adjustments: $%{x:,.0f}<extra></extra>"
            ))
            fig_exp_bud.update_layout(
                **plotly_layout(barmode="stack", height=400,
                yaxis=dict(autorange="reversed", gridcolor="#e5e7eb"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)),
            )
            st.plotly_chart(fig_exp_bud, use_container_width=True)
        else:
            st.info("No expenditure budget data.")

    # ── BAR Analysis: Where are adjustments happening? ───────────────────
    st.markdown("---")
    st.markdown("#### BAR Adjustment Analysis")
    st.caption("Identifies where budget adjustments (BARs) have shifted funding.")

    if len(bud_bud_f) > 0:
        # Only show lines with non-zero adjustments
        bars_data = bud_bud_f[bud_bud_f["Adjustment Amt"] != 0].copy()

        if len(bars_data) > 0:
            bar_by_fund = bars_data.groupby("Fund").agg(
                Increases=("Adjustment Amt", lambda x: x[x > 0].sum()),
                Decreases=("Adjustment Amt", lambda x: x[x < 0].sum()),
                Net_Adjustment=("Adjustment Amt", "sum"),
            ).reset_index()
            bar_by_fund["Fund_Name"] = bar_by_fund["Fund"].apply(extract_name)
            bar_by_fund = bar_by_fund.sort_values("Net_Adjustment", key=abs, ascending=False)

            # Waterfall-style chart
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                name="Increases",
                y=bar_by_fund["Fund_Name"].head(12),
                x=bar_by_fund["Increases"].head(12),
                orientation="h", marker_color="#c64c43",
                hovertemplate="%{y}<br>Increases: $%{x:,.0f}<extra></extra>"
            ))
            fig_bar.add_trace(go.Bar(
                name="Decreases",
                y=bar_by_fund["Fund_Name"].head(12),
                x=bar_by_fund["Decreases"].head(12),
                orientation="h", marker_color="#f4784e",
                hovertemplate="%{y}<br>Decreases: $%{x:,.0f}<extra></extra>"
            ))
            fig_bar.update_layout(
                **plotly_layout(barmode="relative", height=max(300, min(12, len(bar_by_fund)) * 32),
                yaxis=dict(autorange="reversed", gridcolor="#e5e7eb"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                title=f"{bud_acct_label} BAR Adjustments by Fund")
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            # Detail table
            bar_detail = bars_data.groupby(["Fund", "Function"]).agg(
                Beginning=("Final Amt", "sum"),
                Adjustment=("Adjustment Amt", "sum"),
                Adjusted=("Adjusted Amt", "sum"),
                FTE_Adj=("Adjustment FTE", "sum"),
            ).reset_index().sort_values("Adjustment", key=abs, ascending=False)

            st.dataframe(
                bar_detail.style.format({
                    "Beginning": "${:,.0f}", "Adjustment": "${:,.0f}",
                    "Adjusted": "${:,.0f}", "FTE_Adj": "{:,.2f}"
                }).map(
                    lambda v: "color: #245d62" if isinstance(v, (int, float)) and v > 0
                    else ("color: #c64c43" if isinstance(v, (int, float)) and v < 0 else ""),
                    subset=["Adjustment"]
                ),
                use_container_width=True, height=min(500, len(bar_detail) * 35 + 60)
            )
        else:
            st.info("No BAR adjustments found for current filters.")

    # ── Budget vs Actuals Comparison (exceeding budget authority) ─────────
    st.markdown("---")
    st.markdown("#### Budget Authority vs. Actuals")
    st.caption(
        "NMAC requires budget authority at the function level. This view checks "
        "for expenditures exceeding budget authority, with optional drill-down to object."
    )

    if len(bud_bud_f) > 0 and len(bud_act_f) > 0:
        bva_group = st.radio(
            "Group by", options=["Function", "Object", "Fund"],
            index=0, horizontal=True, key="bva_group"
        )

        b_agg = bud_bud_f.groupby(bva_group).agg(
            Adjusted_Budget=("Adjusted Amt", "sum"),
            Budget_FTE=("Adjusted FTE", "sum"),
        ).reset_index()

        a_agg = bud_act_f.groupby(bva_group).agg(
            YTD_Actuals=("Actuals YTDAmount", "sum"),
            Encumbrance=("Actuals Encumbrance", "sum"),
            Actuals_FTE=("Actuals FTE", "sum"),
        ).reset_index()

        bva = b_agg.merge(a_agg, on=bva_group, how="outer").fillna(0)
        bva["Available"] = bva["Adjusted_Budget"] - bva["YTD_Actuals"] - bva["Encumbrance"]
        bva["Pct_Used"] = ((bva["YTD_Actuals"] + bva["Encumbrance"]) /
                           bva["Adjusted_Budget"].replace(0, np.nan) * 100)
        bva["Name"] = bva[bva_group].apply(extract_name)
        bva = bva.sort_values("Adjusted_Budget", ascending=False)

        # Flag lines exceeding budget authority
        exceeding = bva[bva["Available"] < 0]
        if len(exceeding) > 0:
            st.warning(f"⚠️ {len(exceeding)} {bva_group.lower()}(s) have expenditures + encumbrances exceeding budget authority.")

        # Stacked horizontal bar
        top_bva = bva[bva["Adjusted_Budget"] > 0].head(15)
        fig_bva = go.Figure()
        fig_bva.add_trace(go.Bar(
            name="YTD Actuals", y=top_bva["Name"], x=top_bva["YTD_Actuals"],
            orientation="h", marker_color="#245d62",
            hovertemplate="%{y}<br>YTD: $%{x:,.0f}<extra></extra>"
        ))
        fig_bva.add_trace(go.Bar(
            name="Encumbrance", y=top_bva["Name"], x=top_bva["Encumbrance"],
            orientation="h", marker_color="#edc872",
            hovertemplate="%{y}<br>Enc: $%{x:,.0f}<extra></extra>"
        ))
        fig_bva.add_trace(go.Bar(
            name="Available", y=top_bva["Name"], x=top_bva["Available"].clip(lower=0),
            orientation="h", marker_color="#f0f0f0", marker_line=dict(color="#245d62", width=1),
            hovertemplate="%{y}<br>Available: $%{x:,.0f}<extra></extra>"
        ))
        fig_bva.update_layout(
            **plotly_layout(barmode="stack", height=max(300, len(top_bva) * 30),
            yaxis=dict(autorange="reversed", gridcolor="#e5e7eb"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)),
        )
        st.plotly_chart(fig_bva, use_container_width=True)

        # Full table
        bva_display = bva[[bva_group, "Adjusted_Budget", "YTD_Actuals", "Encumbrance",
                           "Available", "Pct_Used", "Budget_FTE", "Actuals_FTE"]].copy()
        bva_display.columns = [bva_group, "Budget", "YTD Actuals", "Encumbrance",
                               "Available", "% Used", "Budget FTE", "Actual FTE"]
        st.dataframe(
            bva_display.style.format({
                "Budget": "${:,.0f}", "YTD Actuals": "${:,.0f}",
                "Encumbrance": "${:,.0f}", "Available": "${:,.0f}",
                "% Used": "{:.1f}%", "Budget FTE": "{:,.1f}", "Actual FTE": "{:,.1f}"
            }).map(
                lambda v: "color: #c64c43; font-weight: 600" if isinstance(v, (int, float)) and v < 0 else "",
                subset=["Available"]
            ),
            use_container_width=True, height=min(500, len(bva_display) * 35 + 60)
        )

    # ── CSV Export ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="section-header">Budget Authority Export</div>', unsafe_allow_html=True)

    if selected_entity != "— All Entities —":
        exp_budget_report = build_budget_report(bud_raw, selected_entity, "E")
        rev_budget_report = build_budget_report(bud_raw, selected_entity, "R")

        entity_short = selected_entity.replace(" ", "_").replace("/", "-")
        fy_code = fy_key_to_code(selected_fy[0]) if selected_fy else "xxxx"

        bc1, bc2 = st.columns(2)
        with bc1:
            st.markdown(f"**Expenditure Budget** — {len(exp_budget_report):,} lines")
            if len(exp_budget_report) > 0:
                st.dataframe(exp_budget_report, use_container_width=True, height=300)
                e1, e2 = st.columns(2)
                with e1:
                    st.download_button(
                        "📥 Exp Budget CSV",
                        data=exp_budget_report.to_csv(index=False),
                        file_name=f"{entity_short}_fy{fy_code}_exp_budget.csv",
                        mime="text/csv", key="dl_bud_exp_csv"
                    )
                with e2:
                    st.download_button(
                        "📥 Exp Budget Excel",
                        data=to_excel_download(exp_budget_report, "Exp Budget"),
                        file_name=f"{entity_short}_fy{fy_code}_exp_budget.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_bud_exp_xlsx"
                    )

        with bc2:
            st.markdown(f"**Revenue Budget** — {len(rev_budget_report):,} lines")
            if len(rev_budget_report) > 0:
                st.dataframe(rev_budget_report, use_container_width=True, height=300)
                r1, r2 = st.columns(2)
                with r1:
                    st.download_button(
                        "📥 Rev Budget CSV",
                        data=rev_budget_report.to_csv(index=False),
                        file_name=f"{entity_short}_fy{fy_code}_rev_budget.csv",
                        mime="text/csv", key="dl_bud_rev_csv"
                    )
                with r2:
                    st.download_button(
                        "📥 Rev Budget Excel",
                        data=to_excel_download(rev_budget_report, "Rev Budget"),
                        file_name=f"{entity_short}_fy{fy_code}_rev_budget.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_bud_rev_xlsx"
                    )
    else:
        st.info("Select a specific entity in the sidebar to generate budget authority CSV exports.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: ACTUALS
# ══════════════════════════════════════════════════════════════════════════════
with tab_actuals:

    st.markdown('<div class="section-header">Actuals Analysis & Export</div>', unsafe_allow_html=True)

    act_act_f, act_bud_f, act_acct_type = render_tab_filters(
        "actuals", act_global, bud_global, dims=FILTER_DIMS, show_acct_type=True
    )
    act_acct_label = "Expenditure" if act_acct_type == "E" else "Revenue"

    # ── KPIs ─────────────────────────────────────────────────────────────
    act_budget_t = act_bud_f["Adjusted Amt"].sum() if len(act_bud_f) > 0 else 0
    act_ytd_t = act_act_f["Actuals YTDAmount"].sum() if len(act_act_f) > 0 else 0
    act_enc_t = act_act_f["Actuals Encumbrance"].sum() if len(act_act_f) > 0 else 0
    act_bal_t = act_budget_t - act_ytd_t - act_enc_t
    act_pct = (act_ytd_t / act_budget_t * 100) if act_budget_t else 0
    act_comm = ((act_ytd_t + act_enc_t) / act_budget_t * 100) if act_budget_t else 0

    ak1, ak2, ak3, ak4, ak5, ak6 = st.columns(6)
    ak1.metric("Adjusted Budget", fmt_currency(act_budget_t, compact=True))
    ak2.metric("YTD Actuals", fmt_currency(act_ytd_t, compact=True))
    ak3.metric("Encumbrance", fmt_currency(act_enc_t, compact=True))
    ak4.metric("Available Balance", fmt_currency(act_bal_t, compact=True))
    ak5.metric("% Spent", fmt_pct(act_pct))
    ak6.metric("% Committed", fmt_pct(act_comm))

    # ── Expenditure by Fund (donut + table) ──────────────────────────────
    st.markdown("---")
    st.markdown("#### Spend Distribution")

    if len(act_act_f) > 0:
        spend_group = st.radio(
            "View by", options=["Fund", "Function", "Object"],
            index=0, horizontal=True, key="act_spend_group"
        )

        spend_data = act_act_f.groupby(spend_group).agg(
            YTD=("Actuals YTDAmount", "sum"),
            Enc=("Actuals Encumbrance", "sum"),
        ).reset_index()
        spend_data["Name"] = spend_data[spend_group].apply(extract_name)
        spend_data = spend_data[spend_data["YTD"] > 0].sort_values("YTD", ascending=False)
        total_spend = spend_data["YTD"].sum()
        spend_data["Pct"] = spend_data["YTD"] / total_spend * 100

        sc1, sc2 = st.columns([2, 3])
        with sc1:
            top_donut = spend_data.head(10)
            fig_d = go.Figure(go.Pie(
                labels=top_donut["Name"], values=top_donut["YTD"],
                hole=0.35, textinfo="label+percent", textposition="outside",
                marker=dict(colors=["#245d62", "#c64c43", "#edc872", "#f4784e", "#1a474b",
                                    "#5a9ea3", "#8fae5f", "#d4956a", "#b85a3a", "#7a8c6e"]),
                hovertemplate="%{label}<br>$%{value:,.0f}<br>%{percent}<extra></extra>"
            ))
            fig_d.update_layout(**plotly_layout(height=400, showlegend=False,
                                margin=dict(l=120, r=120, t=10, b=30)))
            st.plotly_chart(fig_d, use_container_width=True)

        with sc2:
            sd = spend_data[[spend_group, "YTD", "Enc", "Pct"]].head(15).copy()
            sd.columns = [spend_group, "YTD Actuals", "Encumbrance", "% of Total"]
            st.dataframe(sd.style.format({
                "YTD Actuals": "${:,.0f}", "Encumbrance": "${:,.0f}", "% of Total": "{:.1f}%"
            }), use_container_width=True, height=min(400, len(sd) * 35 + 60))

    # ── Budget vs Actuals by Function ────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Budget vs. Actuals by Function")

    if len(act_act_f) > 0 and len(act_bud_f) > 0:
        func_b = act_bud_f.groupby("Function").agg(Budget=("Adjusted Amt", "sum")).reset_index()
        func_a = act_act_f.groupby("Function").agg(
            YTD=("Actuals YTDAmount", "sum"), Enc=("Actuals Encumbrance", "sum")
        ).reset_index()
        func_m = func_b.merge(func_a, on="Function", how="outer").fillna(0)
        func_m["Available"] = func_m["Budget"] - func_m["YTD"] - func_m["Enc"]
        func_m["Pct_Used"] = ((func_m["YTD"] + func_m["Enc"]) / func_m["Budget"].replace(0, np.nan) * 100)
        func_m["Name"] = func_m["Function"].apply(extract_name)
        func_m = func_m.sort_values("Budget", ascending=False)

        top_func = func_m[func_m["Budget"] > 0].head(12)
        fig_fb = go.Figure()
        fig_fb.add_trace(go.Bar(
            name="YTD Actuals", y=top_func["Name"], x=top_func["YTD"],
            orientation="h", marker_color="#245d62",
            hovertemplate="%{y}<br>YTD: $%{x:,.0f}<extra></extra>"
        ))
        fig_fb.add_trace(go.Bar(
            name="Encumbrance", y=top_func["Name"], x=top_func["Enc"],
            orientation="h", marker_color="#edc872",
            hovertemplate="%{y}<br>Enc: $%{x:,.0f}<extra></extra>"
        ))
        fig_fb.add_trace(go.Bar(
            name="Available", y=top_func["Name"], x=top_func["Available"].clip(lower=0),
            orientation="h", marker_color="#f0f0f0", marker_line=dict(color="#245d62", width=1),
            hovertemplate="%{y}<br>Available: $%{x:,.0f}<extra></extra>"
        ))
        fig_fb.update_layout(
            **plotly_layout(barmode="stack", height=max(300, len(top_func) * 32),
            yaxis=dict(autorange="reversed", gridcolor="#e5e7eb"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)),
        )
        st.plotly_chart(fig_fb, use_container_width=True)

        st.dataframe(
            func_m[["Function", "Budget", "YTD", "Enc", "Available", "Pct_Used"]].rename(columns={
                "Budget": "Adjusted Budget", "YTD": "YTD Actuals", "Enc": "Encumbrance",
                "Pct_Used": "% Used (Act+Enc)"
            }).style.format({
                "Adjusted Budget": "${:,.0f}", "YTD Actuals": "${:,.0f}",
                "Encumbrance": "${:,.0f}", "Available": "${:,.0f}",
                "% Used (Act+Enc)": "{:.1f}%"
            }).map(
                lambda v: "color: #c64c43; font-weight: 600" if isinstance(v, (int, float)) and v < 0 else "",
                subset=["Available"]
            ),
            use_container_width=True, height=min(500, len(func_m) * 35 + 60)
        )

    # ── CSV Exports ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="section-header">Actuals Export</div>', unsafe_allow_html=True)

    if selected_entity != "— All Entities —":
        entity_short = selected_entity.replace(" ", "_").replace("/", "-")
        fy_code = fy_key_to_code(selected_fy[0]) if selected_fy else "xxxx"
        period_code = selected_period.lower() if selected_period else "all"

        exp_act_report = build_actuals_report(act_global, bud_global, selected_entity, "E")
        rev_act_report = build_actuals_report(act_global, bud_global, selected_entity, "R")

        ac1, ac2 = st.columns(2)
        with ac1:
            st.markdown(f"**Expenditure Actuals** — {len(exp_act_report):,} lines")
            if len(exp_act_report) > 0:
                st.dataframe(exp_act_report, use_container_width=True, height=300)
                ae1, ae2 = st.columns(2)
                with ae1:
                    st.download_button(
                        "📥 Exp Actuals CSV",
                        data=exp_act_report.to_csv(index=False),
                        file_name=f"{entity_short}_fy{fy_code}_{period_code}_exp.csv",
                        mime="text/csv", key="dl_act_exp_csv"
                    )
                with ae2:
                    st.download_button(
                        "📥 Exp Actuals Excel",
                        data=to_excel_download(exp_act_report, "Expenditures"),
                        file_name=f"{entity_short}_fy{fy_code}_{period_code}_exp.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_act_exp_xlsx"
                    )

        with ac2:
            st.markdown(f"**Revenue Actuals** — {len(rev_act_report):,} lines")
            if len(rev_act_report) > 0:
                st.dataframe(rev_act_report, use_container_width=True, height=300)
                ar1, ar2 = st.columns(2)
                with ar1:
                    st.download_button(
                        "📥 Rev Actuals CSV",
                        data=rev_act_report.to_csv(index=False),
                        file_name=f"{entity_short}_fy{fy_code}_{period_code}_rev.csv",
                        mime="text/csv", key="dl_act_rev_csv"
                    )
                with ar2:
                    st.download_button(
                        "📥 Rev Actuals Excel",
                        data=to_excel_download(rev_act_report, "Revenue"),
                        file_name=f"{entity_short}_fy{fy_code}_{period_code}_rev.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_act_rev_xlsx"
                    )
    else:
        st.info("Select a specific entity in the sidebar to generate actuals CSV exports.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: SALARY & BENEFITS
# ══════════════════════════════════════════════════════════════════════════════
with tab_salary:

    st.markdown('<div class="section-header">Salary & Benefits Analysis</div>', unsafe_allow_html=True)

    # Filter to expenditures only, salary/benefits/contracted objects
    sal_act = act_global[act_global["Account Type"] == "E"].copy() if len(act_global) > 0 else pd.DataFrame()
    sal_bud = bud_global[bud_global["Account Type"] == "E"].copy() if len(bud_global) > 0 else pd.DataFrame()

    # Add classification columns
    if len(sal_act) > 0:
        sal_act["Obj_Category"] = sal_act["Object"].apply(classify_object_category)
        sal_act["Func_Category"] = sal_act["Function"].apply(classify_function_category)
    if len(sal_bud) > 0:
        sal_bud["Obj_Category"] = sal_bud["Object"].apply(classify_object_category)
        sal_bud["Func_Category"] = sal_bud["Function"].apply(classify_function_category)

    # Tab-level filters (Fund, Function, Location)
    with st.expander("🔍 Filters", expanded=False):
        sf1, sf2, sf3 = st.columns(3)
        with sf1:
            sal_funds = st.multiselect("Fund", get_unique_values(sal_act, sal_bud, "Fund"),
                                        default=[], key="sal_fund")
        with sf2:
            sal_funcs = st.multiselect("Function", get_unique_values(sal_act, sal_bud, "Function"),
                                        default=[], key="sal_func")
        with sf3:
            sal_locs = st.multiselect("Location", get_unique_values(sal_act, sal_bud, "Location"),
                                       default=[], key="sal_loc")

    sal_filters = {}
    if sal_funds: sal_filters["Fund"] = sal_funds
    if sal_funcs: sal_filters["Function"] = sal_funcs
    if sal_locs: sal_filters["Location"] = sal_locs

    sal_act = apply_dim_filters(sal_act, sal_filters)
    sal_bud = apply_dim_filters(sal_bud, sal_filters)

    # ── Salary / Benefits / Contracted breakdown ─────────────────────────
    st.markdown("#### Expenditure Composition")

    if len(sal_act) > 0:
        comp = sal_act.groupby("Obj_Category").agg(
            YTD=("Actuals YTDAmount", "sum"), Enc=("Actuals Encumbrance", "sum")
        ).reset_index()
        comp["Total"] = comp["YTD"] + comp["Enc"]
        comp = comp.sort_values("YTD", ascending=False)
        grand_total = comp["YTD"].sum()
        comp["Pct"] = comp["YTD"] / grand_total * 100

        comp_bud = sal_bud.groupby("Obj_Category").agg(
            Budget=("Adjusted Amt", "sum")
        ).reset_index() if len(sal_bud) > 0 else pd.DataFrame(columns=["Obj_Category", "Budget"])

        comp = comp.merge(comp_bud, on="Obj_Category", how="left").fillna(0)
        comp["Pct_Used"] = ((comp["YTD"] + comp["Enc"]) / comp["Budget"].replace(0, np.nan) * 100)

        # KPI cards for salary / benefits / contracted
        sal_row = comp[comp["Obj_Category"] == "Salaries"]
        ben_row = comp[comp["Obj_Category"] == "Benefits"]
        con_row = comp[comp["Obj_Category"] == "Contracted Services"]

        sk1, sk2, sk3, sk4 = st.columns(4)
        sk1.metric("Salary YTD",
                    fmt_currency(sal_row["YTD"].sum() if len(sal_row) > 0 else 0, compact=True),
                    delta=f"{sal_row['Pct'].sum():.0f}% of total" if len(sal_row) > 0 else None,
                    delta_color="off")
        sk2.metric("Benefits YTD",
                    fmt_currency(ben_row["YTD"].sum() if len(ben_row) > 0 else 0, compact=True),
                    delta=f"{ben_row['Pct'].sum():.0f}% of total" if len(ben_row) > 0 else None,
                    delta_color="off")
        sk3.metric("Contracted Svcs YTD",
                    fmt_currency(con_row["YTD"].sum() if len(con_row) > 0 else 0, compact=True),
                    delta=f"{con_row['Pct'].sum():.0f}% of total" if len(con_row) > 0 else None,
                    delta_color="off")
        sk4.metric("All Other YTD",
                    fmt_currency(grand_total - sal_row["YTD"].sum() - ben_row["YTD"].sum() - con_row["YTD"].sum(), compact=True))

        # Composition bar
        fig_comp = go.Figure(go.Bar(
            x=comp["YTD"], y=comp["Obj_Category"], orientation="h",
            text=comp["Pct"].apply(lambda v: f"{v:.1f}%"),
            textposition="auto",
            marker_color=["#245d62", "#c64c43", "#edc872", "#f4784e",
                           "#1a474b", "#8fae5f", "#d4956a"][:len(comp)],
            hovertemplate="%{y}<br>YTD: $%{x:,.0f}<extra></extra>"
        ))
        fig_comp.update_layout(**plotly_layout(height=max(200, len(comp) * 40),
                                yaxis=dict(autorange="reversed"), xaxis_title=""))
        st.plotly_chart(fig_comp, use_container_width=True)

        st.dataframe(comp[["Obj_Category", "Budget", "YTD", "Enc", "Pct", "Pct_Used"]].rename(columns={
            "Obj_Category": "Category", "Pct": "% of Total Exp", "Pct_Used": "% of Budget Used"
        }).style.format({
            "Budget": "${:,.0f}", "YTD": "${:,.0f}", "Enc": "${:,.0f}",
            "% of Total Exp": "{:.1f}%", "% of Budget Used": "{:.1f}%"
        }), use_container_width=True)

    # ── FTE Analysis ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### FTE: Budget vs. Actual")

    # Focus on salary objects (51xxx) which carry FTE
    sal_fte_act = sal_act[sal_act["Obj_Category"] == "Salaries"] if len(sal_act) > 0 else pd.DataFrame()
    sal_fte_bud = sal_bud[sal_bud["Obj_Category"] == "Salaries"] if len(sal_bud) > 0 else pd.DataFrame()

    if len(sal_fte_bud) > 0 or len(sal_fte_act) > 0:
        fte_bud_total = sal_fte_bud["Adjusted FTE"].sum() if len(sal_fte_bud) > 0 else 0
        fte_act_total = sal_fte_act["Actuals FTE"].sum() if len(sal_fte_act) > 0 else 0
        fte_diff = fte_act_total - fte_bud_total

        fk1, fk2, fk3 = st.columns(3)
        fk1.metric("Budgeted FTE", f"{fte_bud_total:,.1f}")
        fk2.metric("Actual FTE", f"{fte_act_total:,.1f}")
        fk3.metric("Variance", f"{fte_diff:+,.1f}",
                    delta_color="inverse" if fte_diff > 0 else "normal")

        # FTE by Job Class
        st.markdown("**FTE by Job Class**")

        fte_bud_jc = sal_fte_bud.groupby("Job Class").agg(
            Budget_FTE=("Adjusted FTE", "sum"),
            Budget_Salary=("Adjusted Amt", "sum"),
        ).reset_index() if len(sal_fte_bud) > 0 else pd.DataFrame(columns=["Job Class", "Budget_FTE", "Budget_Salary"])

        fte_act_jc = sal_fte_act.groupby("Job Class").agg(
            Actual_FTE=("Actuals FTE", "sum"),
            Actual_Salary=("Actuals YTDAmount", "sum"),
        ).reset_index() if len(sal_fte_act) > 0 else pd.DataFrame(columns=["Job Class", "Actual_FTE", "Actual_Salary"])

        fte_jc = fte_bud_jc.merge(fte_act_jc, on="Job Class", how="outer").fillna(0)
        fte_jc["FTE_Variance"] = fte_jc["Actual_FTE"] - fte_jc["Budget_FTE"]
        fte_jc["Avg_Salary_Budget"] = (fte_jc["Budget_Salary"] / fte_jc["Budget_FTE"].replace(0, np.nan))
        fte_jc["Avg_Salary_Actual"] = (fte_jc["Actual_Salary"] / fte_jc["Actual_FTE"].replace(0, np.nan))
        fte_jc["JC_Name"] = fte_jc["Job Class"].apply(extract_name)
        fte_jc = fte_jc.sort_values("Budget_FTE", ascending=False)

        # Grouped bar: Budget FTE vs Actual FTE by Job Class
        top_jc = fte_jc[fte_jc["Budget_FTE"] > 0].head(15)
        if len(top_jc) > 0:
            fig_fte = go.Figure()
            fig_fte.add_trace(go.Bar(
                name="Budget FTE", y=top_jc["JC_Name"], x=top_jc["Budget_FTE"],
                orientation="h", marker_color="#245d62",
                hovertemplate="%{y}<br>Budget: %{x:,.1f} FTE<extra></extra>"
            ))
            fig_fte.add_trace(go.Bar(
                name="Actual FTE", y=top_jc["JC_Name"], x=top_jc["Actual_FTE"],
                orientation="h", marker_color="#c64c43",
                hovertemplate="%{y}<br>Actual: %{x:,.1f} FTE<extra></extra>"
            ))
            fig_fte.update_layout(
                **plotly_layout(barmode="group", height=max(300, len(top_jc) * 32),
                yaxis=dict(autorange="reversed", gridcolor="#e5e7eb"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)),
            )
            st.plotly_chart(fig_fte, use_container_width=True)

        # Detail table
        fte_display = fte_jc[["Job Class", "Budget_FTE", "Actual_FTE", "FTE_Variance",
                              "Avg_Salary_Budget", "Avg_Salary_Actual",
                              "Budget_Salary", "Actual_Salary"]].copy()
        fte_display.columns = ["Job Class", "Budget FTE", "Actual FTE", "FTE Variance",
                               "Avg Salary (Budget)", "Avg Salary (Actual)",
                               "Total Budget", "Total YTD"]
        st.dataframe(
            fte_display.style.format({
                "Budget FTE": "{:,.2f}", "Actual FTE": "{:,.2f}", "FTE Variance": "{:+,.2f}",
                "Avg Salary (Budget)": "${:,.0f}", "Avg Salary (Actual)": "${:,.0f}",
                "Total Budget": "${:,.0f}", "Total YTD": "${:,.0f}"
            }).map(
                lambda v: "color: #c64c43" if isinstance(v, (int, float)) and v < -1
                else ("color: #245d62" if isinstance(v, (int, float)) and v > 1 else ""),
                subset=["FTE Variance"]
            ),
            use_container_width=True, height=min(500, len(fte_display) * 35 + 60)
        )

    # ── Staffing Balance: Function Category ──────────────────────────────
    st.markdown("---")
    st.markdown("#### Staffing Balance by Function")
    st.caption(
        "Compares FTE allocation across function categories. Watch for top-heavy "
        "administration relative to instruction and support."
    )

    if len(sal_fte_bud) > 0 or len(sal_fte_act) > 0:
        fb = sal_fte_bud.groupby("Func_Category").agg(
            Budget_FTE=("Adjusted FTE", "sum"),
            Budget_Salary=("Adjusted Amt", "sum"),
        ).reset_index() if len(sal_fte_bud) > 0 else pd.DataFrame(columns=["Func_Category", "Budget_FTE", "Budget_Salary"])

        fa = sal_fte_act.groupby("Func_Category").agg(
            Actual_FTE=("Actuals FTE", "sum"),
            Actual_Salary=("Actuals YTDAmount", "sum"),
        ).reset_index() if len(sal_fte_act) > 0 else pd.DataFrame(columns=["Func_Category", "Actual_FTE", "Actual_Salary"])

        fc = fb.merge(fa, on="Func_Category", how="outer").fillna(0)
        fc_total_fte = fc["Actual_FTE"].sum()
        fc["Pct_of_FTE"] = (fc["Actual_FTE"] / fc_total_fte * 100) if fc_total_fte > 0 else 0
        fc = fc.sort_values("Budget_FTE", ascending=False)

        sc1, sc2 = st.columns([2, 3])

        with sc1:
            fig_staff = go.Figure(go.Pie(
                labels=fc["Func_Category"], values=fc["Actual_FTE"],
                hole=0.35, textinfo="label+percent", textposition="outside",
                marker=dict(colors=["#245d62", "#c64c43", "#edc872", "#f4784e",
                                    "#1a474b", "#8fae5f", "#d4956a", "#5a9ea3",
                                    "#b85a3a", "#7a8c6e"][:len(fc)]),
                hovertemplate="%{label}<br>FTE: %{value:,.1f}<br>%{percent}<extra></extra>"
            ))
            fig_staff.update_layout(**plotly_layout(height=400, showlegend=False,
                                     margin=dict(l=120, r=120, t=30, b=30)))
            st.plotly_chart(fig_staff, use_container_width=True)

        with sc2:
            fc_display = fc[["Func_Category", "Budget_FTE", "Actual_FTE",
                             "Pct_of_FTE", "Budget_Salary", "Actual_Salary"]].copy()
            fc_display.columns = ["Function Category", "Budget FTE", "Actual FTE",
                                   "% of Total FTE", "Salary Budget", "Salary YTD"]
            st.dataframe(fc_display.style.format({
                "Budget FTE": "{:,.1f}", "Actual FTE": "{:,.1f}",
                "% of Total FTE": "{:.1f}%",
                "Salary Budget": "${:,.0f}", "Salary YTD": "${:,.0f}"
            }), use_container_width=True, height=min(400, len(fc_display) * 35 + 60))

    # ── Contracted Services ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Contracted Services (Object 53xxx)")
    st.caption("Contracted services do not carry FTE but represent significant expenditures.")

    con_act = sal_act[sal_act["Obj_Category"] == "Contracted Services"] if len(sal_act) > 0 else pd.DataFrame()
    con_bud = sal_bud[sal_bud["Obj_Category"] == "Contracted Services"] if len(sal_bud) > 0 else pd.DataFrame()

    if len(con_act) > 0 or len(con_bud) > 0:
        con_b = con_bud.groupby(["Function", "Object"]).agg(
            Budget=("Adjusted Amt", "sum")
        ).reset_index() if len(con_bud) > 0 else pd.DataFrame(columns=["Function", "Object", "Budget"])

        con_a = con_act.groupby(["Function", "Object"]).agg(
            YTD=("Actuals YTDAmount", "sum"), Enc=("Actuals Encumbrance", "sum")
        ).reset_index() if len(con_act) > 0 else pd.DataFrame(columns=["Function", "Object", "YTD", "Enc"])

        con_m = con_b.merge(con_a, on=["Function", "Object"], how="outer").fillna(0)
        con_m["Available"] = con_m["Budget"] - con_m["YTD"] - con_m["Enc"]
        con_m["Pct_Used"] = ((con_m["YTD"] + con_m["Enc"]) / con_m["Budget"].replace(0, np.nan) * 100)
        con_m = con_m.sort_values("Budget", ascending=False)

        con_display = con_m[["Function", "Object", "Budget", "YTD", "Enc", "Available", "Pct_Used"]].copy()
        con_display.columns = ["Function", "Object", "Budget", "YTD Actuals",
                               "Encumbrance", "Available", "% Used"]
        st.dataframe(
            con_display.style.format({
                "Budget": "${:,.0f}", "YTD Actuals": "${:,.0f}",
                "Encumbrance": "${:,.0f}", "Available": "${:,.0f}",
                "% Used": "{:.1f}%"
            }).map(
                lambda v: "color: #c64c43; font-weight: 600" if isinstance(v, (int, float)) and v < 0 else "",
                subset=["Available"]
            ),
            use_container_width=True, height=min(500, len(con_display) * 35 + 60)
        )
    else:
        st.info("No contracted services data available.")

# Footer
st.markdown("---")
st.caption("New Mexico Public Education Department · School Budget Bureau")