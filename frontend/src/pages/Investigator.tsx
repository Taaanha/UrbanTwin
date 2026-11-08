import { useEffect, useState } from "react";
import { apiFetch, apiJson } from "../api";
import { useParams } from "react-router-dom";

type QueueItem = {
  tracking_id: string;
  category: string;
  severity: string;
  description: string;
  has_verification: boolean;
  top_score: number;
  top_label: string;
  match_count: number;
};

type Match = {
  kind: string;
  tracking_id?: string;
  public_id?: string;
  issue_id?: number;
  score: number;
  suggested_label: string;
  distance_m: number;
  reasons: string[];
  candidate: Record<string, unknown>;
};

type Inspect = {
  report: {
    tracking_id: string;
    category: string;
    severity: string;
    description: string;
    latitude: number;
    longitude: number;
    evidence: Array<{ url: string }>;
  };
  matches: Match[];
  verifications: Array<{ decision: string; notes?: string; decided_at?: string }>;
  policy: string[];
};

type AiBox = { label: string; x: number; y: number; w: number; h: number };
type AiResult = {
  provider: string;
  model: string;
  warning: string;
  is_problem: boolean | null;
  category: string | null;
  severity: string | null;
  confidence: number | null;
  boxes: AiBox[];
  summary: string;
  generated_at: string;
};
type AiProviders = Record<string, { configured: boolean; model: string | null }>;

function AiOpinionPanel({ trackingId, imageUrl }: { trackingId: string; imageUrl?: string }) {
  const [providers, setProviders] = useState<AiProviders>({});
  const [provider, setProvider] = useState("gemini");
  const [result, setResult] = useState<AiResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiJson<{ providers: AiProviders }>("/api/investigator/ai-providers")
      .then((b) => setProviders(b.providers))
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    setResult(null);
    setError("");
  }, [trackingId]);

  async function run() {
    setBusy(true);
    setError("");
    try {
      setResult(
        await apiJson<AiResult>(`/api/investigator/reports/${trackingId}/ai-opinion`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider }),
        }),
      );
    } catch (e) {
      setResult(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const anyConfigured = Object.values(providers).some((p) => p.configured);
  return (
    <div className="space-y-2 rounded border border-slate-800 p-3 text-xs">
      <h2 className="text-sm font-semibold">AI second opinion (optional)</h2>
      <p className="text-slate-400">
        Sends this report's photo (location data removed) to a third-party AI service. Suggestion only: it never changes the
        report or creates an issue.
      </p>
      {!anyConfigured ? (
        <p className="text-slate-500">No provider configured. Add GEMINI_API_KEY or HF_API_TOKEN + HF_DETECTION_MODEL to backend/.env.</p>
      ) : null}
      <div className="flex gap-2">
        <select value={provider} onChange={(e) => setProvider(e.target.value)} className="rounded border border-slate-700 bg-slate-950 px-2 py-1">
          {Object.entries(providers).map(([name, info]) => (
            <option key={name} value={name} disabled={!info.configured}>
              {name}
              {info.configured ? "" : " (not configured)"}
            </option>
          ))}
        </select>
        <button className="rounded bg-sky-700 px-3 py-1 text-white disabled:opacity-50" disabled={busy || !providers[provider]?.configured} onClick={() => void run()}>
          {busy ? "Asking…" : "Ask AI"}
        </button>
      </div>
      {error ? <p className="text-amber-300">{error}</p> : null}
      {result ? (
        <div className="space-y-1">
          <p className="rounded bg-amber-950 p-2 text-amber-200">{result.warning}</p>
          <p>
            {result.provider} · {result.model} · problem seen: <b>{result.is_problem == null ? "unknown" : result.is_problem ? "yes" : "no"}</b>
            {result.category ? ` · ${result.category}` : ""}
            {result.severity ? ` · ${result.severity}` : ""}
            {result.confidence != null ? ` · confidence ${(result.confidence * 100).toFixed(0)}%` : ""}
          </p>
          <p className="text-slate-300">{result.summary}</p>
          {imageUrl && result.boxes.length ? (
            <div className="relative inline-block">
              <img src={imageUrl} alt="with AI boxes" className="max-h-64 rounded" />
              {result.boxes.map((b, i) => (
                <div
                  key={i}
                  title={b.label}
                  className="absolute border-2 border-amber-400"
                  style={{ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` }}
                />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

const DECISIONS = [
  ["new_candidate_issue", "New candidate issue"],
  ["possible_duplicate", "Possible duplicate"],
  ["existing_issue", "Existing issue"],
  ["insufficient_evidence", "Insufficient evidence"],
  ["evidence_mismatch", "Evidence mismatch"],
  ["possibly_resolved", "Possibly resolved"],
];

export default function Investigator() {
  const params = useParams();
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [inspect, setInspect] = useState<Inspect | null>(null);
  const [selectedMatch, setSelectedMatch] = useState<Match | null>(null);
  const [decision, setDecision] = useState("new_candidate_issue");
  const [notes, setNotes] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  async function loadQueue() {
    const body = await apiFetch("/api/investigator/queue").then((r) => r.json());
    setQueue(body.items ?? []);
  }

  async function openReport(trackingId: string) {
    const body = (await apiFetch(`/api/investigator/reports/${trackingId}`).then((r) => r.json())) as Inspect;
    setInspect(body);
    setSelectedMatch(body.matches[0] ?? null);
    setDecision(body.matches[0]?.score >= 70 ? "possible_duplicate" : "new_candidate_issue");
    setMessage(null);
  }

  useEffect(() => {
    void loadQueue();
  }, []);

  useEffect(() => {
    if (params.trackingId) {
      void openReport(params.trackingId);
    }
  }, [params.trackingId]);

  async function submitDecision() {
    if (!inspect) return;
    const payload: Record<string, unknown> = {
      tracking_id: inspect.report.tracking_id,
      decision,
      notes,
      score: selectedMatch?.score,
      reasons: selectedMatch ? { notes: selectedMatch.reasons, distance_m: selectedMatch.distance_m } : {},
    };
    if (selectedMatch?.kind === "report") payload.related_tracking_id = selectedMatch.tracking_id;
    if (selectedMatch?.kind === "issue") payload.related_issue_id = selectedMatch.issue_id;
    const response = await apiFetch("/api/investigator/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) {
      setMessage(body.detail ?? "Decision failed");
      return;
    }
    setMessage(`Saved: ${body.decision}. Reports preserved.`);
    await loadQueue();
    await openReport(inspect.report.tracking_id);
  }

  return (
    <div className="grid h-full min-h-0 lg:grid-cols-[20rem_1fr_22rem]">
      <aside className="overflow-auto border-r border-slate-800 p-3 text-sm">
        <p className="text-xs uppercase tracking-wide text-slate-500">City Investigator</p>
        <p className="mt-1 text-xs text-amber-300">Suggestions only. Nothing is auto-merged.</p>
        <ul className="mt-3 space-y-2">
          {queue.map((item) => (
            <li key={item.tracking_id}>
              <button
                className="w-full rounded border border-slate-800 p-2 text-left hover:border-slate-600"
                onClick={() => void openReport(item.tracking_id)}
              >
                <p className="font-mono text-xs">{item.tracking_id}</p>
                <p>
                  {item.category} · score {item.top_score} · {item.top_label}
                </p>
                {item.has_verification ? (
                  <p className="text-xs text-emerald-400">Has verification history</p>
                ) : (
                  <p className="text-xs text-amber-400">Needs review</p>
                )}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <section className="overflow-auto p-4">
        {!inspect ? (
          <p className="text-slate-400">Select a report to compare nearby evidence.</p>
        ) : (
          <div className="space-y-3">
            <h1 className="font-mono text-lg">{inspect.report.tracking_id}</h1>
            <p>
              {inspect.report.category} · {inspect.report.severity}
            </p>
            <p className="text-slate-300">{inspect.report.description}</p>
            <p className="text-xs text-slate-500">
              {inspect.report.latitude.toFixed(5)}, {inspect.report.longitude.toFixed(5)}
            </p>
            {inspect.report.evidence.map((file) => (
              <img key={file.url} src={file.url} alt="evidence" className="max-h-40 rounded" />
            ))}
            <AiOpinionPanel trackingId={inspect.report.tracking_id} imageUrl={inspect.report.evidence[0]?.url} />
            <h2 className="pt-2 font-semibold">Possible matches</h2>
            {inspect.matches.length === 0 ? (
              <p className="text-sm text-slate-400">No reports or issues within 120 m.</p>
            ) : (
              inspect.matches.map((match) => (
                <button
                  key={`${match.kind}-${match.tracking_id ?? match.public_id}`}
                  className={`block w-full rounded border p-2 text-left ${
                    selectedMatch === match ? "border-sky-500" : "border-slate-800"
                  }`}
                  onClick={() => setSelectedMatch(match)}
                >
                  <p className="text-sm">
                    {match.kind} · {match.tracking_id ?? match.public_id} · {match.score} pts · {match.distance_m} m ·{" "}
                    {match.suggested_label}
                  </p>
                  <ul className="mt-1 list-disc pl-4 text-xs text-slate-400">
                    {match.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </button>
              ))
            )}
            {inspect.verifications.length > 0 ? (
              <div>
                <h2 className="font-semibold">Verification history</h2>
                {inspect.verifications.map((row, index) => (
                  <p key={index} className="text-xs text-slate-400">
                    {row.decided_at}: {row.decision}
                    {row.notes ? ` — ${row.notes}` : ""}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
        )}
      </section>
      <aside className="overflow-auto border-l border-slate-800 p-4 text-sm">
        <h2 className="font-semibold">Officer decision</h2>
        <ul className="mt-2 list-disc pl-4 text-xs text-slate-400">
          {(inspect?.policy ?? []).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <label className="mt-3 block">
          Decision
          <select
            className="mt-1 w-full rounded bg-slate-900 p-2"
            value={decision}
            onChange={(event) => setDecision(event.target.value)}
          >
            {DECISIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="mt-3 block">
          Notes
          <textarea
            className="mt-1 w-full rounded bg-slate-900 p-2"
            rows={4}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </label>
        <button
          className="mt-3 w-full rounded bg-sky-700 py-2 disabled:opacity-40"
          disabled={!inspect}
          onClick={() => void submitDecision()}
        >
          Save decision
        </button>
        {message ? <p className="mt-3 text-emerald-400">{message}</p> : null}
      </aside>
    </div>
  );
}
