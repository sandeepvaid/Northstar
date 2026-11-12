import { useState } from "react";
import MetricsView from "./components/MetricsView";
import HealthView from "./components/HealthView";
import { triggerIngest } from "./api/client";

type Tab = "metrics" | "health";

export default function App() {
  const [tab, setTab] = useState<Tab>("metrics");
  const [ingesting, setIngesting] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  // Bumped after a re-ingest so the active view refetches.
  const [reloadKey, setReloadKey] = useState(0);

  async function onIngest() {
    setIngesting(true);
    setNote(null);
    try {
      const r = await triggerIngest();
      setNote(`Ingest complete: ${r.metrics} metrics, ${r.issues} issues.`);
      setReloadKey((k) => k + 1);
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Ingest failed.");
    } finally {
      setIngesting(false);
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Campaign Data Hub</h1>
        <div className="header-actions">
          <nav className="tabs">
            <button
              className={tab === "metrics" ? "tab active" : "tab"}
              onClick={() => setTab("metrics")}
            >
              Campaign metrics
            </button>
            <button
              className={tab === "health" ? "tab active" : "tab"}
              onClick={() => setTab("health")}
            >
              Data health
            </button>
          </nav>
          <button className="ingest-btn" onClick={onIngest} disabled={ingesting}>
            {ingesting ? "Ingesting…" : "Re-ingest"}
          </button>
        </div>
      </header>

      {note && <div className="note">{note}</div>}

      <main>
        {tab === "metrics" ? (
          <MetricsView reloadKey={reloadKey} />
        ) : (
          <HealthView reloadKey={reloadKey} />
        )}
      </main>
    </div>
  );
}
