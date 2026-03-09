# OBMS Financial Explorer

A Streamlit-based financial analysis platform for the New Mexico Public Education Department's School Budget Bureau. Provides interactive budget-vs-actuals reporting, entity-level drill-downs, and quarterly review analytics for 216+ school districts and charter schools — powered by OBMS data extracted from SSAS cubes via XMLA.

## Overview

The OBMS Financial Explorer replaces manual Power BI workflows with a lightweight, shareable web app that reads parquet files directly from Google Drive. Data is extracted daily from the OBMS SSAS cubes using Python/XMLA scripts and stored as parquet files (~40 files, ~8M rows, FY2006–present). The app loads only the fiscal years you select, keeping things fast even with 20 years of history available.

## Features

### Global Views
- **Overview Dashboard** — KPI cards (budget, YTD actuals, encumbrance, balance, % spent/committed), budget-vs-actuals by fund, spend distribution treemap by function, and execution gauges with expected-pace benchmarks
- **Entity Analysis** — Scatter plot of all entities by budget size vs. spend rate, with color-coded commitment levels and expected-pace reference lines; sortable detail table
- **Drill-Down** — Dimensional analysis by fund, function, object, program, job class, or location with stacked horizontal bars and full data tables
- **Trends** — Quarter-over-quarter YTD cumulative spend, period spend, and FTE trends with multi-year overlay

### District Report Tab
- **CSV/Excel Data Exports** — Line-item expenditure and revenue reports at the full dimensional grain (entity/fund/function/object/program/job class), formatted in the standard quarterly review CSV format for upload to the Actuals Analysis compliance app
- **Revenue vs. Expenditure Analysis** (Section 4) — Grouped bar chart comparing revenue and expenditure YTD by fund for the selected entity
- **Funds Where Expenditures Exceed Revenue** (Section 5) — Automatic classification of deficit funds as non-reimbursable (operational, capital, debt service — real cash concerns) or reimbursable (federal/state flow-through — expected behavior), with color-coded severity
- **Expenditure Distribution by Fund** (Section 6) — Donut chart and top-10 table showing where expenditure dollars are concentrated
- **Expenditure by Function** (Section 7) — Horizontal stacked bar (actuals + encumbrance + available) with detail table including budget, YTD, encumbered, available balance, and % used
- **HTML Export** — One-click download of a standalone HTML analysis report styled with Playfair Display / Source Sans 3 on a cream background, matching the quarterly review report format, with Chart.js visualizations and the NMAC 6.20.2 disclaimer

### Data Export Tab
- Filtered budget and actuals data export to Excel/CSV
- Budget-vs-actuals summary export grouped by any dimension

## Data Architecture

```
Google Drive (shared folder)
├── actuals_0607.parquet    # FY2006-07 actuals
├── actuals_0708.parquet
├── ...
├── actuals_2526.parquet    # FY2025-26 actuals
├── budget_0607.parquet     # FY2006-07 budget
├── ...
└── budget_2526.parquet     # FY2025-26 budget
```

Each parquet file is extracted daily at 5:30 AM via Windows Task Scheduler running Python scripts that query the OBMS SSAS cubes over XMLA. Google Drive file IDs are permanent — when the file contents are refreshed, the ID stays the same, so no app updates are needed for daily data refreshes.

### Key Columns

**Actuals fact table:** `Budget Entity`, `Fund`, `Function`, `Object`, `Program`, `Job Class`, `Location`, `Account Type` (E/R), `Reporting Period` (Q1–Q4), `Actuals YTDAmount`, `Actuals Period Amount`, `Actuals Encumbrance`, `Actuals FTE`, `FiscalYearKey`, `PeriodOrder`

**Budget fact table:** `Budget Entity`, `Fund`, `Function`, `Object`, `Program`, `Job Class`, `Location`, `Account Type` (E/R), `Adjusted Amt`, `Final Amt`, `Final FTE`, `FiscalYearKey`

## Fund Classification

The app classifies funds by leading code digits for the revenue-vs-expenditure deficit analysis:

| Prefix | Classification | Examples |
|--------|---------------|----------|
| 11 | Non-Reimbursable | Operational |
| 13, 14 | Non-Reimbursable | Transportation, Instructional Materials |
| 21, 23 | Non-Reimbursable | Food Services, Non-Instructional Support |
| 31, 32 | Non-Reimbursable | Debt Service |
| 41, 42, 43 | Non-Reimbursable | Capital Improvements |
| 24 | Reimbursable | Federal Flow-Through (IDEA-B, Title I) |
| 25 | Reimbursable | State Flow-Through |
| 26, 27 | Reimbursable | Federal/State Direct |
| 28 | Reimbursable | Federal Stimulus (ESSER) |
| 29 | Reimbursable | State/Other Grants |

This mapping is defined in `FUND_CLASSIFICATION` and can be adjusted as needed.

## Setup

### Requirements
- Python 3.10+
- Streamlit
- pandas
- plotly
- openpyxl (for Excel export)
- pyarrow (for parquet reading)

### Installation

```bash
pip install streamlit pandas plotly openpyxl pyarrow
```

### Running Locally

```bash
streamlit run obms_financial_explorer.py
```

### Deployment

The app is designed for Streamlit Community Cloud deployment via GitHub. The parquet files must be publicly shared on Google Drive (view access) for the app to read them without authentication.

To add a new fiscal year:
1. Upload the actuals and budget parquet files to the Google Drive folder
2. Add the file IDs to the `GDRIVE_FILES` dictionary in the script
3. Push to GitHub — Streamlit Cloud picks up the change automatically

## Roadmap

Planned additions to the District Report analysis:

- **Section 8 — Encumbrance Risk Analysis:** Flag line items where actuals + encumbrances exceed adjusted budget (committed over-expenditures)
- **Section 9 — Burn Rate / Pace Analysis:** Flag over-pace lines (>40% at Q1) and under-pace lines ($0 actuals on budgets >$50K), excluding cash/reserve objects
- **Section 10 — FTE Variance Analysis:** Compare actuals FTE to budgeted FTE on Object 51100 (salaries) by job class, flagging understaffed/overstaffed positions
- **Section 11 — Salary by Job Class:** Object 51100 breakdown with FTE delta
- **Section 12 — Program-Level Spending:** Expenditures grouped by program code with donut chart
- **Memo Integration:** Optional text input or file upload for reviewer notes (Key Concerns, Compliance Highlights, Audit Findings, Action Items) that get woven into the HTML export

## Author

School Budget Bureau, New Mexico Public Education Department
