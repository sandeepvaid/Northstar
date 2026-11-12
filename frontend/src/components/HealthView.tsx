import { useEffect, useState } from "react";
import { fetchDeliveries, fetchDelivery } from "../api/client";
import type { DeliveryDetail, DeliveryListItem } from "../api/types";

// Health drives the color. "missing" deliveries have health=fail but we show the
// status separately so a gap reads differently from a delivery that failed checks.
function healthClass(d: DeliveryListItem): string {
  if (d.status === "missing") return "missing";
  return d.health ?? "pass";
}

const HEALTH_ORDER: Record<string, number> = { fail: 0, warn: 1, pass: 2 };

export default function HealthView({ reloadKey }: { reloadKey: number }) {
  const [deliveries, setDeliveries] = useState<DeliveryListItem[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<DeliveryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDeliveries()
      .then((d) => !cancelled && setDeliveries(d))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  useEffect(() => {
    if (selected == null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    fetchDelivery(selected)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [selected, reloadKey]);

  // Problem deliveries first (fail, then warn, then pass), then by week/platform.
  const sorted = [...deliveries].sort(
    (a, b) =>
      (HEALTH_ORDER[healthClass(a)] ?? 3) - (HEALTH_ORDER[healthClass(b)] ?? 3) ||
      a.week_start.localeCompare(b.week_start) ||
      a.platform.localeCompare(b.platform),
  );

  const counts = deliveries.reduce<Record<string, number>>((acc, d) => {
    const k = healthClass(d);
    acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <section className="health-view">
      {error && <div className="error">{error}</div>}

      <div className="legend">
        {(["fail", "warn", "pass", "missing"] as const).map((k) => (
          <span key={k} className={`legend-item ${k}`}>
            <span className="dot" /> {k} ({counts[k] ?? 0})
          </span>
        ))}
      </div>

      <div className="delivery-grid">
        {sorted.map((d) => (
          <button
            key={d.id}
            className={`delivery-card ${healthClass(d)} ${selected === d.id ? "selected" : ""}`}
            onClick={() => setSelected(selected === d.id ? null : d.id)}
          >
            <div className="card-top">
              <span className="platform">{d.platform}</span>
              <span className="badge">{d.status === "missing" ? "missing" : d.health}</span>
            </div>
            <div className="week">{d.week_start}</div>
            <div className="card-meta">
              {d.status === "missing" ? (
                <span className="muted">no file delivered</span>
              ) : (
                <>
                  <span>{d.row_count ?? 0} rows</span>
                  {d.fail_count > 0 && <span className="pill fail">{d.fail_count} fail</span>}
                  {d.warn_count > 0 && <span className="pill warn">{d.warn_count} warn</span>}
                  {d.issue_count === 0 && <span className="pill pass">clean</span>}
                </>
              )}
            </div>
          </button>
        ))}
      </div>

      {detail && (
        <div className="detail-panel">
          <div className="detail-head">
            <h2>
              {detail.platform} · {detail.week_start}
            </h2>
            <button className="close-btn" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          <div className="detail-sub">
            <code>{detail.filename}</code> · status <b>{detail.status}</b> · health{" "}
            <b>{detail.health ?? "—"}</b> · {detail.row_count ?? 0} rows
          </div>

          {detail.issues.length === 0 ? (
            <p className="muted">No quality issues recorded for this delivery.</p>
          ) : (
            <table className="issues-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Check</th>
                  <th>Level</th>
                  <th>Campaign / Date</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {detail.issues.map((i) => (
                  <tr key={i.id}>
                    <td>
                      <span className={`pill ${i.severity}`}>{i.severity}</span>
                    </td>
                    <td>
                      <code>{i.check_name}</code>
                    </td>
                    <td>{i.level}</td>
                    <td className="muted">
                      {[i.campaign, i.date].filter(Boolean).join(" · ") || "—"}
                    </td>
                    <td>
                      {i.message}
                      {i.raw_value != null && (
                        <>
                          {" "}
                          <span className="raw">
                            raw {i.field ? `${i.field}=` : ""}
                            {i.raw_value}
                          </span>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}
