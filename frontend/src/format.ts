// Display helpers. A null metric renders as an em dash so "missing" is never
// confused with zero (traceability: nulls come from quarantine/divide-by-zero).
const DASH = "—";

export function money(v: number | null): string {
  return v == null ? DASH : v.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export function int(v: number | null): string {
  return v == null ? DASH : v.toLocaleString("en-US");
}

export function pct(v: number | null): string {
  return v == null ? DASH : `${(v * 100).toFixed(2)}%`;
}

export function cpcFmt(v: number | null): string {
  return v == null ? DASH : `$${v.toFixed(2)}`;
}
