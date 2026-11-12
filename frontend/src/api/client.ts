// Thin typed API client. One fetch wrapper; one function per endpoint.
import type {
  DeliveryDetail,
  DeliveryListItem,
  IngestResponse,
  MetricsFilters,
  SummaryResponse,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`);
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${BASE}. Is the backend running?`);
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail?.detail ?? `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

function qs(params: Record<string, string | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v) q.set(k, v);
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

// FR-7: campaign (or platform) aggregates with filter-aware totals + derived CTR/CPC.
export function fetchSummary(
  groupBy: "campaign" | "platform",
  f: MetricsFilters,
): Promise<SummaryResponse> {
  return getJson<SummaryResponse>(
    `/metrics/summary${qs({
      group_by: groupBy,
      platform: f.platform || undefined,
      date_from: f.date_from,
      date_to: f.date_to,
      sort_by: f.sort_by,
      order: f.order,
    })}`,
  );
}

// FR-8: all deliveries with health classification.
export function fetchDeliveries(): Promise<DeliveryListItem[]> {
  return getJson<DeliveryListItem[]>("/deliveries");
}

// FR-8 drill-down: one delivery's full quality report.
export function fetchDelivery(id: number): Promise<DeliveryDetail> {
  return getJson<DeliveryDetail>(`/deliveries/${id}`);
}

// FR-6: trigger (re-)ingestion.
export async function triggerIngest(): Promise<IngestResponse> {
  const res = await fetch(`${BASE}/ingest`, { method: "POST" });
  if (!res.ok) throw new ApiError(res.status, `Ingest failed (${res.status})`);
  return res.json() as Promise<IngestResponse>;
}
