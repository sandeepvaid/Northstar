# Northstar

**Campaign Data Hub** — normalizes weekly ad-platform delivery files (Meta CSV, Google
CSV, LinkedIn JSON) into one canonical dataset, checks their data quality, and shows both
in a web UI.

- **Backend:** Python 3.12+ / FastAPI / SQLite
- **Frontend:** React + TypeScript (Vite)

---

## Prerequisites

- Python **3.12+**
- Node.js **18+** (includes npm)

---

## 1. Backend

Open a terminal in the project root.

```bash
cd backend

# create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# install dependencies
pip install -r requirements.txt

# load the data into the database (run this once, first)
python run_ingest.py --reset

# start the API
uvicorn app.api.main:app --reload
```

The API is now running at **http://localhost:8000**
(interactive docs at **http://localhost:8000/docs**).

Leave this terminal running.

---

## 2. Frontend

Open a **second** terminal in the project root.

```bash
cd frontend

npm install
npm run dev
```

Open the app at **http://localhost:5173**.

That's it — the app is running.

---

## Using the app

- **Campaign metrics** — table of campaigns with spend, impressions, clicks, CTR,
  and CPC. Click a column header to sort. Filter by platform and date range; the
  totals row updates with your filters.
- **Data health** — every delivery, color-coded by status. Click a card to see its
  quality issues in detail.
- **Re-ingest** — the button in the top right re-runs the pipeline. Running it again
  does not change the results (safe to repeat).

---

## Running the tests (optional)

```bash
cd backend
source .venv/bin/activate
python -m pytest
```

---

## Architecture

See `ARCHITECTURE.md` for the system diagram (deliveries → pipeline → storage → API →
frontend) and the data model.

---

## Storage choice

**SQLite.** It is file-based and needs zero setup, so the project runs from a fresh clone
with no database server to install or configure — which suits a 4–5 hour take-home. It
also enforces the idempotency guarantees directly: a `UNIQUE(platform, campaign, date)`
constraint on `metrics` makes the upsert converge, and a `UNIQUE` content hash on
`deliveries` catches duplicate files. For production scale the same schema moves to
Postgres with little change; that is the natural next step, not a rewrite.

---

## Quality checks and what they found

Checks run at three levels and are recorded in the `data_issues` table (reported by
exception — a delivery with no rows is "clean"). Each delivery gets a health rollup:
**fail** if any fail-severity issue, **warn** if any issue, otherwise **pass**.

**Row level:** `invalid_date` (quarantines the row), `missing`/`invalid`/`negative_spend`,
`unknown_currency`, `invalid`/`negative_impressions`, `missing`/`negative_clicks`,
`clicks_gt_impressions`, `date_out_of_window`.
**File level:** `duplicate_delivery`, `duplicate_row`, `conflicting_duplicate_row`,
`parse_error`.
**Delivery level:** `missing_delivery`, `spend_implausible`.

What they caught in the provided June 2026 data:

| Platform | Found |
|---|---|
| Meta | invalid calendar date `06/31` (quarantined); negative spend `-111.41`; empty `clicks`; **06-08 spend ~100× off-scale** → `spend_implausible` (CPM $342 vs $3.55 median) |
| Google | 8 within-file duplicate rows (06-01); `google_ads_2026-06-15_resend.csv` byte-identical to the original → duplicate delivery |
| LinkedIn | 5 records with the `clicks` field absent (06-08); **no 06-22 file** → missing delivery |

Canonical result: **368 metrics · 21 issues · 16 deliveries**, stable across re-runs.

---

## Key design decisions and trade-offs

- **Transform only when reversible.** A value is converted only if the original can be
  reconstructed (micros→USD, EUR→USD with `raw_amount`+`raw_currency` kept). If a value
  can't be trusted it becomes `null` and the raw is recorded in `data_issues`. If a *key*
  field (date/campaign) can't be trusted, the whole row is **quarantined** — it never
  pollutes the metrics.
- **Idempotency via the natural key.** `metrics` is keyed by `(platform, campaign, date)`
  with upsert — deliberately *not* by `delivery_id` — so re-ingesting the same or a resent
  delivery converges. `delivery_id` is kept only as lineage.
- **Spend plausibility: flag, don't correct.** The off-scale Meta delivery is flagged
  (relative-to-median CPM + absolute ceiling) but its raw spend is preserved, consistent
  with the reversibility principle. Trade-off: it stays in the totals (as a documented
  warn) rather than being silently dropped.
- **Report by exception.** We persist issues, not a pass/fail row for every check — simpler
  and smaller. Trade-off: the full check roster isn't materialized (see below).
- **Strict date parsing** (per-platform ordered formats, no fuzzy guessing) and
  **campaign normalization** (trim + collapse whitespace + lowercase) give one canonical
  shape without guessing.
- **Extensibility:** a new platform is one `Normalizer` subclass; a new check is one issue
  append — no refactor. SQL and constants are centralized.
- **CTR/CPC divide-by-zero → `null`** (never an error), documented and unit-tested.

---

## What I'd do with more time

- A `docker-compose.yml` for one-command bring-up (backend + frontend).
- Broader cadence/volume checks: per-campaign weekly completeness and row-count bands
  (skipped now to avoid false-positives on the legitimately short 06-29 week).
- Materialize the **full check roster** per delivery (record passes too, not only issues)
  for the strictest reading of "which checks ran."
- Symmetric spend anomaly (detect under-reporting, not just inflation).
- API pagination and auth; charts in the metrics view; a Postgres migration path.
