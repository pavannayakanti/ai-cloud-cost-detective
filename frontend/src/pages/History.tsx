import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../lib/api";

interface HistoryRow {
  id: string;
  resource_group: string;
  resources_scanned: number | null;
  issues_found: number | null;
  estimated_savings: string | null;
  analysis_result: Record<string, unknown> | null;
  status: string;
  created_at: string;
}

export default function History() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    apiFetch<{ history: HistoryRow[] }>("/api/history")
      .then((data) => {
        if (isMounted) setRows(data.history);
      })
      .catch((err) => {
        if (isMounted) setError(err instanceof ApiError ? err.message : "Could not load history.");
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const openReport = (row: HistoryRow) => {
    navigate("/report", {
      state: {
        analysis: {
          resource_group: row.resource_group,
          created_at: row.created_at,
          resources_scanned: row.resources_scanned ?? undefined,
          analysis: row.analysis_result ?? { summary: "", issues: [] },
        },
      },
    });
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-white">Analysis history</h1>

      {isLoading && <p className="text-sm text-slate-400">Loading...</p>}
      {error && <p className="text-sm text-red-400">{error}</p>}
      {!isLoading && !error && rows.length === 0 && (
        <p className="text-sm text-slate-400">No analyses yet. Run one from the Dashboard.</p>
      )}

      {rows.length > 0 && (
        <div className="divide-y divide-slate-800 rounded-lg border border-slate-800">
          {rows.map((row) => (
            <button
              key={row.id}
              onClick={() => openReport(row)}
              disabled={row.status !== "complete"}
              className="flex w-full flex-wrap items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-900/60 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <div>
                <p className="font-medium text-white">{row.resource_group}</p>
                <p className="text-xs text-slate-500">{new Date(row.created_at).toLocaleString()}</p>
              </div>
              <div className="flex items-center gap-6 text-sm text-slate-300">
                <span>{row.issues_found ?? 0} issues</span>
                <span className="text-emerald-400">{row.estimated_savings ?? "-"}</span>
                <span className="text-xs uppercase text-slate-500">{row.status}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
