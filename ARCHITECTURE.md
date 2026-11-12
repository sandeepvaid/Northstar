# Architecture

How the pieces fit together, end to end.

> The diagrams below are [Mermaid](https://mermaid.js.org/) — GitHub renders them
> automatically. If you're reading in a plain editor, the ASCII overview is at the bottom.

---

## 1. System overview

```mermaid
flowchart LR
    subgraph FILES["Delivery files (data/deliveries)"]
        M["meta_*.csv"]
        G["google_*.csv"]
        L["linkedin_*.json"]
        R["exchange_rates.json"]
    end

    subgraph PIPE["Ingestion pipeline (Python)"]
        D["Discover + content-hash"]
        N["Normalize per platform<br/>(→ canonical, USD, ISO date)"]
        Q["Quality checks<br/>(row / file / delivery)"]
        P["Persist: upsert by natural key<br/>+ write issues"]
        D --> N --> Q --> P
    end

    subgraph DB["SQLite"]
        T1[("deliveries")]
        T2[("metrics")]
        T3[("data_issues")]
    end

    subgraph API["FastAPI"]
        A1["/metrics, /metrics/summary"]
        A2["/deliveries, /deliveries/:id"]
        A3["POST /ingest"]
    end

    subgraph UI["React + TypeScript"]
        V1["Campaign metrics view"]
        V2["Data health view"]
    end

    FILES --> PIPE
    PIPE --> DB
    DB --> API
    API --> UI
    A3 -. "triggers" .-> PIPE
```

**Flow in one line:** files → normalize + quality-check → SQLite → API → UI.
The UI's *Re-ingest* button calls `POST /ingest`, which re-runs the pipeline.

---

## 2. Components

| Layer | Where | Responsibility |
|---|---|---|
| **Discovery** | `app/ingest/discover.py` | Find delivery files, parse `platform` + `week_start` from the filename, compute a content hash. |
| **Normalizers** | `app/ingest/normalizers/` | One per platform. Turn a raw row into a canonical row (USD, ISO date) and report issues. |
| **Pipeline** | `app/ingest/pipeline.py` | Orchestrates: dedupe → parse → normalize → persist → cross-delivery checks. |
| **Storage** | `app/schema.sql`, `app/db.py` | SQLite: `deliveries`, `metrics`, `data_issues`. |
| **API** | `app/api/` | Read endpoints (metrics, deliveries) + `POST /ingest`. |
| **Frontend** | `frontend/src/` | Two views over the API: metrics table and health dashboard. |

---

## 3. Data model

```mermaid
erDiagram
    deliveries ||--o{ data_issues : "has"
    deliveries ||--o{ metrics : "sources (lineage)"

    deliveries {
        int id PK
        text platform
        text week_start
        text filename
        text content_hash "UNIQUE"
        int row_count
        text status "processed | skipped_duplicate | parse_error | missing"
        text health "pass | warn | fail"
    }
    metrics {
        int id PK
        text platform
        text campaign
        text date
        real spend_usd "nullable"
        int impressions "nullable"
        int clicks "nullable"
        text raw_amount "traceability"
        text raw_currency "traceability"
        int source_delivery_id FK
    }
    data_issues {
        int id PK
        int delivery_id FK
        text level "row | file | delivery"
        text check_name
        text severity "warn | fail"
        text field
        text raw_value "original value kept"
        text raw_row "quarantined row as JSON"
        text message
    }
```

**Key design points**

- `metrics` has `UNIQUE(platform, campaign, date)` — the **natural key**. Upserting on it
  means re-running the pipeline converges to the same rows (idempotency). `delivery_id`
  is deliberately *not* part of the key; it is kept as `source_delivery_id` for lineage.
- `deliveries.content_hash` is `UNIQUE` — identical bytes are skipped automatically,
  which is how the duplicate `_resend` file is caught.
- Numbers are **only transformed when reversible**. Lossy conversions (EUR→USD) are
  allowed only because `raw_amount` + `raw_currency` are stored. If a value can't be
  trusted it is set to `null` and the original is recorded in `data_issues`.
  If a *key* field (date/campaign) can't be trusted, the whole row is quarantined.

---

## 4. ASCII fallback

```
data/deliveries/*             ┌──────────── Ingestion pipeline (Python) ────────────┐
  meta_*.csv     ───────────▶ │ 1. Discover + content-hash (file dedupe)            │
  google_*.csv   ───────────▶ │ 2. Parse (per-platform adapter) → raw rows          │
  linkedin_*.json ──────────▶ │ 3. Normalize (→ canonical: USD, ISO date)           │
  exchange_rates.json ──────▶ │ 4. Quality checks (row / file / delivery) → health  │
                              │ 5. Persist (upsert by natural key; write issues)    │
                              └───────────────┬─────────────────────────────────────┘
                                              ▼
                               SQLite (deliveries, metrics, data_issues)
                                              ▲
                              FastAPI ────────┘   (/metrics, /deliveries, /ingest)
                                              ▲
                              React + TS (metrics view, health view)
```
