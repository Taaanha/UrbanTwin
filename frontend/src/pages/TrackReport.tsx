import { FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

type Report = {
  tracking_id: string;
  category: string;
  severity: string;
  status: string;
  description: string;
  location_text?: string | null;
  is_verified_issue: boolean;
  created_at: string;
  evidence: Array<{ id: number; url: string; original_name: string }>;
};

export default function TrackReport() {
  const params = useParams();
  const [query, setQuery] = useState(params.trackingId ?? "");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(id: string) {
    setError(null);
    const response = await fetch(`/api/reports/track/${id}`);
    if (!response.ok) {
      setReport(null);
      setError("Tracking ID not found.");
      return;
    }
    setReport(await response.json());
  }

  useEffect(() => {
    if (params.trackingId) {
      void load(params.trackingId);
    }
  }, [params.trackingId]);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (query.trim()) {
      void load(query.trim());
    }
  }

  return (
    <div className="mx-auto max-w-lg p-6">
      <h1 className="text-xl font-semibold">Track a report</h1>
      <form className="mt-4 flex gap-2" onSubmit={onSubmit}>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="UT-YYYYMMDD-…"
          className="flex-1 rounded bg-slate-900 p-2 font-mono"
        />
        <button className="rounded bg-sky-700 px-4">Check</button>
      </form>
      {error ? <p className="mt-4 text-amber-400">{error}</p> : null}
      {report ? (
        <div className="mt-6 space-y-2 rounded border border-slate-800 p-4">
          <p className="font-mono text-emerald-400">{report.tracking_id}</p>
          <p>Status: {report.status}</p>
          <p>Category: {report.category}</p>
          <p>Severity: {report.severity}</p>
          <p className="text-slate-300">{report.description}</p>
          {report.location_text ? <p className="text-slate-400">Place: {report.location_text}</p> : null}
          <p className="text-xs text-amber-300">
            {report.is_verified_issue
              ? "Verified issue"
              : "Citizen report — not a verified issue."}
          </p>
          {report.evidence.map((file) => (
            <a key={file.id} className="block text-sky-400" href={file.url} target="_blank" rel="noreferrer">
              {file.original_name}
            </a>
          ))}
        </div>
      ) : null}
    </div>
  );
}
