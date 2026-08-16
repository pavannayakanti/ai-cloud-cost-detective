import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import ProgressTracker, { type ProgressEvent } from "../components/ProgressTracker";
import { apiFetch, ApiError, WS_BASE_URL } from "../lib/api";

interface ResourceGroup {
  name: string;
  arn: string | null;
  description: string | null;
}

interface AnalyzeResponse {
  analysis_id: string;
  resource_group: string;
  resources: unknown[];
  analysis: {
    summary?: string;
    issues?: unknown[];
    total_estimated_monthly_savings_usd?: number;
  };
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [groups, setGroups] = useState<ResourceGroup[]>([]);
  const [selectedGroup, setSelectedGroup] = useState("");
  const [isLoadingGroups, setIsLoadingGroups] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [events, setEvents] = useState<ProgressEvent[]>([]);

  useEffect(() => {
    let isMounted = true;
    apiFetch<{ resource_groups: ResourceGroup[] }>("/api/resource-groups")
      .then((data) => {
        if (!isMounted) return;
        setGroups(data.resource_groups);
        if (data.resource_groups.length > 0) {
          setSelectedGroup(data.resource_groups[0].name);
        }
      })
      .catch((err) => {
        if (!isMounted) return;
        setLoadError(err instanceof ApiError ? err.message : "Could not load resource groups.");
      })
      .finally(() => {
        if (isMounted) setIsLoadingGroups(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const runAnalysis = () => {
    if (!selectedGroup || isRunning) return;

    setIsRunning(true);
    setRunError(null);
    setEvents([]);

    const analysisId = crypto.randomUUID();
    const socket = new WebSocket(`${WS_BASE_URL}/ws/progress/${analysisId}`);

    const finish = () => {
      setIsRunning(false);
      socket.close();
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as ProgressEvent;
        setEvents((prev) => [...prev, payload]);
      } catch {
        // ignore malformed progress messages
      }
    };

    socket.onopen = async () => {
      try {
        const result = await apiFetch<AnalyzeResponse>("/api/analyze", {
          method: "POST",
          body: JSON.stringify({ resource_group: selectedGroup, analysis_id: analysisId }),
        });
        finish();
        navigate("/report", {
          state: {
            analysis: {
              resource_group: result.resource_group,
              analysis: result.analysis,
              resources_scanned: result.resources.length,
            },
          },
        });
      } catch (err) {
        finish();
        setRunError(err instanceof ApiError ? err.message : "Analysis failed.");
      }
    };

    socket.onerror = () => {
      finish();
      setRunError("Lost connection to the progress stream.");
    };
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-white">Run a cost analysis</h1>
        <p className="mt-1 text-sm text-slate-400">
          Select a resource group to scan for over-provisioning, idle resources, and cost savings.
        </p>
      </div>

      {loadError && <p className="text-sm text-red-400">{loadError}</p>}

      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label htmlFor="resource-group" className="mb-1 block text-sm text-slate-300">
            Resource group
          </label>
          <select
            id="resource-group"
            value={selectedGroup}
            onChange={(event) => setSelectedGroup(event.target.value)}
            disabled={isLoadingGroups || groups.length === 0}
            className="min-w-[16rem] rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 focus:border-sky-500 focus:outline-none"
          >
            {isLoadingGroups && <option>Loading...</option>}
            {!isLoadingGroups && groups.length === 0 && <option>No resource groups found</option>}
            {groups.map((group) => (
              <option key={group.name} value={group.name}>
                {group.name}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={runAnalysis}
          disabled={isRunning || !selectedGroup}
          className="rounded-md bg-sky-500 px-4 py-2 font-medium text-white hover:bg-sky-400 disabled:opacity-50"
        >
          {isRunning ? "Running analysis..." : "Run Analysis"}
        </button>
      </div>

      {runError && <p className="text-sm text-red-400">{runError}</p>}

      {(isRunning || events.length > 0) && (
        <div>
          <h2 className="mb-2 text-sm font-medium text-slate-300">Progress</h2>
          <ProgressTracker events={events} isRunning={isRunning} />
        </div>
      )}
    </div>
  );
}
