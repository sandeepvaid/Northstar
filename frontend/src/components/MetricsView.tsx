import { useEffect, useState } from "react";
import { fetchSummary } from "../api/client";
import type { Order, Platform, SortBy, SummaryResponse } from "../api/types";
import { cpcFmt, int, money, pct } from "../format";

const PLATFORMS: Platform[] = ["meta", "google", "linkedin"];

// Column spec: key drives the server sort_by; numeric columns right-align.
const COLUMNS: { key: SortBy; label: string; numeric: boolean }[] = [
  { key: "group", label: "Campaign", numeric: false },
  { key: "spend", label: "Spend (USD)", numeric: true },
  { key: "impressions", label: "Impressions", numeric: true },
  { key: "clicks", label: "Clicks", numeric: true },
  { key: "ctr", label: "CTR", numeric: true },
  { key: "cpc", label: "CPC", numeric: true },
];

export default function MetricsView({ reloadKey }: { reloadKey: number }) {
  const [platform, setPlatform] = useState<Platform | "">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortBy, setSortBy] = useState<SortBy>("spend");
  const [order, setOrder] = useState<Order>("desc");

  const [data, setData] = useState<SummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchSummary("campaign", {
      platform,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      sort_by: sortBy,
      order,
    })
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [platform, dateFrom, dateTo, sortBy, order, reloadKey]);

  function sortOn(key: SortBy) {
    if (key === sortBy) {
      setOrder((o) => (o === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(key);
      setOrder(key === "group" ? "asc" : "desc"); // names A->Z, numbers high->low
    }
  }

  const totals = data?.totals;

  return (
    <section>
      <div className="filters">
        <label>
          Platform
          <select value={platform} onChange={(e) => setPlatform(e.target.value as Platform | "")}>
            <option value="">All</option>
            {PLATFORMS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label>
          From
          <input
            type="date"
            value={dateFrom}
            max={dateTo || undefined}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={dateTo}
            min={dateFrom || undefined}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </label>
        {(platform || dateFrom || dateTo) && (
          <button
            className="clear-btn"
            onClick={() => {
              setPlatform("");
              setDateFrom("");
              setDateTo("");
            }}
          >
            Clear filters
          </button>
        )}
      </div>

      {totals?.date_min && totals.date_max && (
        <div className="range-caption">
          Showing data from <b>{totals.date_min}</b> to <b>{totals.date_max}</b>
          <span className="muted">
            {" · "}
            {!dateFrom && !dateTo ? "all dates" : "filtered range"}
          </span>
        </div>
      )}

      {error && <div className="error">{error}</div>}

      <table className="data-table">
        <thead>
          <tr>
            {COLUMNS.map((c) => (
              <th
                key={c.key}
                className={`${c.numeric ? "num" : ""} sortable`}
                onClick={() => sortOn(c.key)}
              >
                {c.label}
                {sortBy === c.key && <span className="arrow">{order === "desc" ? " ↓" : " ↑"}</span>}
              </th>
            ))}
            <th className="num">Platform</th>
          </tr>
        </thead>
        <tbody>
          {data?.items.map((r) => (
            <tr key={`${r.platform ?? ""}:${r.group}`}>
              <td>{r.group}</td>
              <td className="num">{money(r.spend_usd)}</td>
              <td className="num">{int(r.impressions)}</td>
              <td className="num">{int(r.clicks)}</td>
              <td className="num">{pct(r.ctr)}</td>
              <td className="num">{cpcFmt(r.cpc)}</td>
              <td className="num platform-cell">{r.platform}</td>
            </tr>
          ))}
          {!loading && data?.items.length === 0 && (
            <tr>
              <td colSpan={7} className="empty">
                No campaigns match these filters.
              </td>
            </tr>
          )}
        </tbody>
        {totals && (
          <tfoot>
            <tr className="totals-row">
              <td>
                Totals{" "}
                <span className="muted">
                  {"—"} {data?.items.length ?? 0} campaigns {"·"} {totals.row_count} daily
                  records{loading ? ", updating…" : ""}
                </span>
              </td>
              <td className="num">{money(totals.spend_usd)}</td>
              <td className="num">{int(totals.impressions)}</td>
              <td className="num">{int(totals.clicks)}</td>
              <td className="num">{pct(totals.ctr)}</td>
              <td className="num">{cpcFmt(totals.cpc)}</td>
              <td></td>
            </tr>
          </tfoot>
        )}
      </table>
    </section>
  );
}
