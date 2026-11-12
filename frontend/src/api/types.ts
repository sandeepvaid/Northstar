// TypeScript mirrors of the backend Pydantic response models (app/api/schemas.py).
// Kept in one place so the UI and API share one contract.

export interface Totals {
  row_count: number;
  spend_usd: number | null;
  impressions: number | null;
  clicks: number | null;
  ctr: number | null;
  cpc: number | null;
  date_min: string | null; // earliest date in the data currently shown
  date_max: string | null; // latest date in the data currently shown
}

export interface SummaryRow {
  group: string; // campaign name or platform name
  platform: string | null; // present when grouping by campaign
  spend_usd: number | null;
  impressions: number | null;
  clicks: number | null;
  ctr: number | null;
  cpc: number | null;
  rows: number;
}

export interface SummaryResponse {
  group_by: string;
  items: SummaryRow[];
  totals: Totals;
}

export interface DeliveryListItem {
  id: number;
  platform: string;
  week_start: string;
  filename: string;
  status: string;
  health: string | null;
  row_count: number | null;
  issue_count: number;
  fail_count: number;
  warn_count: number;
  ingested_at: string;
}

export interface IssueOut {
  id: number;
  level: string;
  check_name: string;
  severity: string;
  field: string | null;
  raw_value: string | null;
  raw_row: Record<string, unknown> | null;
  campaign: string | null;
  date: string | null;
  message: string;
}

export interface DeliveryDetail {
  id: number;
  platform: string;
  week_start: string;
  filename: string;
  status: string;
  health: string | null;
  row_count: number | null;
  ingested_at: string;
  issues: IssueOut[];
}

export interface IngestResponse {
  files: number;
  outcomes: Record<string, number>;
  metrics: number;
  issues: number;
}

export type Platform = "meta" | "google" | "linkedin";
export type SortBy = "spend" | "ctr" | "cpc" | "impressions" | "clicks" | "group";
export type Order = "asc" | "desc";

export interface MetricsFilters {
  platform?: Platform | "";
  date_from?: string;
  date_to?: string;
  sort_by?: SortBy;
  order?: Order;
}
