export interface ProgressEvent {
  stage: string;
  message: string;
}

interface ProgressTrackerProps {
  events: ProgressEvent[];
  isRunning: boolean;
}

export default function ProgressTracker({ events, isRunning }: ProgressTrackerProps) {
  if (events.length === 0) {
    return null;
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
      <ul className="space-y-2">
        {events.map((event, index) => {
          const isLast = index === events.length - 1;
          const isError = event.stage === "error";
          const dotClass = isError
            ? "bg-red-500"
            : isLast && isRunning
              ? "animate-pulse bg-sky-400"
              : "bg-emerald-500";

          return (
            <li key={`${event.stage}-${index}`} className="flex items-center gap-3 text-sm">
              <span className={`h-2 w-2 flex-shrink-0 rounded-full ${dotClass}`} />
              <span className={isError ? "text-red-400" : "text-slate-300"}>{event.message}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
