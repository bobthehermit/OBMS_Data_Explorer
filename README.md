# OBMS Financial Explorer

A Streamlit-based financial analysis platform for the New Mexico Public Education Department's School Budget Bureau. Provides interactive budget authority tracking, actuals reporting, and salary/FTE analytics for 216+ school districts and charter schools — powered by OBMS data extracted from SSAS cubes via XMLA.

## Overview

The OBMS Financial Explorer replaces manual Power BI workflows with a lightweight, shareable web app that reads parquet files directly from Google Drive. Data is extracted daily from the OBMS SSAS cubes using Python/XMLA scripts and stored as parquet files (~40 files, ~8M rows, FY2006–present). The app loads only the fiscal years you select, keeping things fast even with 20 years of history available.

## Tabs

### 1. Overview
Executive snapshot for the selected entity (or all entities). Revenue and expenditure budgets, YTD actuals, encumbrance, and net position at a glance. Revenue vs. expenditure by fund with grouped bar chart. Funds where expenditures exceed revenue, split by non-reimbursable (cash concern) vs. reimbursable (expected behavior). Budget execution gauges — expenditure % spent, % committed, and revenue % collected vs. expected pace. Expenditure treemap by function with % spent color scale.

### 2. Budget Authority
Dedicated view of the budget authority lifecycle: Beginning Budget → BAR Adjustments → Adjusted Budget, with FTE. Revenue budget vs. expenditure budget side-by-side comparison showing where approved authority is allocated. BAR adjustment analysis with waterfall chart (increases vs. decreases by fund) and detail table by fund/function. Budget authority vs. actuals comparison grouped by function, object, or fund — flags lines where expenditures + encumbrances exceed budget authority (NMAC compliance). CSV/Excel export matching the standard format: Entity, Fund, Function, Object, Program, Location, JobClass, Beginning Budget, Beginning FTE, Adjustment Amount, Adjustment FTE, Adjusted Budget, Adjusted FTE.

### 3. Actuals
Actuals analysis with spend distribution (toggleable by fund, function, or object), budget vs. actuals by function with stacked bars, and full detail tables. CSV/Excel export of line-item expenditure and revenue reports at the full OBMS dimensional grain including Location (Fund → Function → Object → Program → Location → Job Class), formatted for the Actuals Analysis compliance app.

### 4. Salary & Benefits
Analysis of the largest expenditure category. Expenditure composition breakdown: salaries, benefits, contracted services, and other — with budget vs. YTD comparison. FTE budget vs. actual by job class with variance flags and average salary calculations. Staffing balance by function category (instruction, student support, school administration, general administration, etc.) — surfaces top-heavy admin ratios. Contracted services detail (Object 53xxx) showing where non-FTE dollars are going by function and object.

## Filter Architecture

**Global filters (sidebar):** Fiscal Year, Reporting Period, Budget Entity — apply to all tabs.

**Per-tab filters (inline):** Fund, Function, Object, Program, Location, Job Class — each tab maintains its own dimensional filters so you can filter Budget Authority to Fund 11000 without affecting your Salary & Benefits view.

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

**Budget fact table:** `Budget Entity`, `Fund`, `Function`, `Object`, `Program`, `Job Class`, `Location`, `Account Type` (E/R), `Final Amt` (beginning budget), `Adjustment Amt` (BAR changes), `Adjusted Amt` (final budget), `Final FTE`, `Adjustment FTE`, `Adjusted FTE`, `FiscalYearKey`

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

## Setup

### Requirements
- Python 3.10+
- Streamlit
- pandas, plotly, openpyxl, pyarrow, numpy

### Running Locally

```bash
pip install streamlit pandas plotly openpyxl pyarrow numpy
streamlit run obms_explorer.py
```

### Deployment

Designed for Streamlit Community Cloud via GitHub. Parquet files must be publicly shared on Google Drive (view access).

To add a new fiscal year:
1. Upload the actuals and budget parquet files to Google Drive
2. Add the file IDs to `GDRIVE_FILES` in the script
3. Push to GitHub — Streamlit Cloud picks up the change automatically

## Roadmap

- **HTML Export** — Standalone quarterly review report (Playfair Display / Source Sans 3, cream background, Chart.js) with NMAC 6.20.2 disclaimer
- **Encumbrance Risk Analysis** — Flag lines where actuals + encumbrances exceed adjusted budget
- **Burn Rate / Pace Analysis** — Over-pace and under-pace detection by quarter
- **Enrollment Projection Outlook** — Track growth projections vs. 40-day count; flag mid-year SEG cut risk
- **Memo Integration** — Reviewer notes (Key Concerns, Compliance, Audit Findings, Action Items) woven into HTML export

## Author

School Budget Bureau, New Mexico Public Education Department
