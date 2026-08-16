import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

interface Issue {
  resource_name?: string;
  resource_id?: string;
  resource_type?: string;
  issue_type?: "over-provisioned" | "unused" | "misconfigured" | "other" | string;
  issue?: string;
  severity?: "high" | "medium" | "low" | string;
  estimated_monthly_savings_usd?: number;
  fix_command?: string;
}

interface ReportState {
  resource_group: string;
  created_at?: string;
  resources_scanned?: number;
  analysis: {
    summary?: string;
    issues?: Issue[];
    total_estimated_monthly_savings_usd?: number;
  };
}

const SEVERITY_STYLES: Record<string, string> = {
  high: "border-red-500/30 bg-red-500/15 text-red-400",
  medium: "border-yellow-500/30 bg-yellow-500/15 text-yellow-400",
  low: "border-green-500/30 bg-green-500/15 text-green-400",
};

const ISSUE_TYPE_LABELS: Record<string, string> = {
  "over-provisioned": "Over-provisioned",
  unused: "Unused",
  misconfigured: "Misconfigured",
  other: "Other",
};

function formatUsd(value: number): string {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function CopyableCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API unavailable; nothing to fall back to
    }
  };

  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded-md bg-slate-950 p-3 pr-16 text-xs text-slate-200">
        <code>{command}</code>
      </pre>
      <button
        onClick={handleCopy}
        className="absolute right-2 top-2 rounded bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

export default function Report() {
  const location = useLocation();
  const navigate = useNavigate();
  const data = (location.state as { analysis?: ReportState } | undefined)?.analysis;

  if (!data) {
    return (
      <div className="py-16 text-center text-slate-400">
        <p>No report to show.</p>
        <button
          onClick={() => navigate("/dashboard")}
          className="mt-4 rounded-md bg-sky-500 px-4 py-2 text-white hover:bg-sky-400"
        >
          Back to Dashboard
        </button>
      </div>
    );
  }

  const issues = data.analysis.issues ?? [];
  const totalSavings = data.analysis.total_estimated_monthly_savings_usd ?? 0;

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm text-slate-400">Resource group</p>
        <h1 className="text-2xl font-semibold text-white">{data.resource_group}</h1>
        {data.created_at && (
          <p className="mt-1 text-xs text-slate-500">{new Date(data.created_at).toLocaleString()}</p>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
          <p className="text-sm text-slate-400">Resources scanned</p>
          <p className="mt-2 text-3xl font-semibold text-white">
            {data.resources_scanned ?? "-"}
          </p>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
          <p className="text-sm text-slate-400">Issues found</p>
          <p className="mt-2 text-3xl font-semibold text-white">{issues.length}</p>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
          <p className="text-sm text-slate-400">Estimated monthly savings</p>
          <p className="mt-2 text-3xl font-semibold text-emerald-400">{formatUsd(totalSavings)}</p>
        </div>
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
        <p className="text-sm text-slate-400">Summary</p>
        <p className="mt-2 text-slate-200">{data.analysis.summary || "No summary available."}</p>
      </div>

      <div>
        <h2 className="mb-3 text-lg font-medium text-white">Issues found ({issues.length})</h2>
        {issues.length === 0 ? (
          <p className="text-sm text-slate-400">No issues found. Nice and lean.</p>
        ) : (
          <div className="space-y-4">
            {issues.map((issue, index) => (
              <div key={index} className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-medium text-white">
                      {issue.resource_name || issue.resource_id || "Resource"}
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      {issue.resource_type && <span>{issue.resource_type}</span>}
                      {issue.issue_type && (
                        <span className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300">
                          {ISSUE_TYPE_LABELS[issue.issue_type] ?? issue.issue_type}
                        </span>
                      )}
                    </div>
                  </div>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${
                      SEVERITY_STYLES[issue.severity ?? ""] ?? "border-slate-700 text-slate-300"
                    }`}
                  >
                    {issue.severity ?? "unknown"}
                  </span>
                </div>
                {issue.issue && <p className="mt-2 text-sm text-slate-300">{issue.issue}</p>}
                {typeof issue.estimated_monthly_savings_usd === "number" && (
                  <p className="mt-2 text-sm text-emerald-400">
                    Est. savings: {formatUsd(issue.estimated_monthly_savings_usd)}/mo
                  </p>
                )}
                {issue.fix_command && (
                  <div className="mt-3">
                    <CopyableCommand command={issue.fix_command} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
