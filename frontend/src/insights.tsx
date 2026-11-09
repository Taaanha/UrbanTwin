import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, apiJson } from "./api";
import { HBars, Icon, Kpi, Notice, Panel, SEVERITY_COLOR, categoryLabel, titleCase } from "./ui";

/* ------------------------------------------------------------------ visible failures */

export function ProblemToast() {
  const [problem, setProblem] = useState<{ message: string; at: number } | null>(null);
  useEffect(() => {
    const onProblem = (e: Event) => setProblem({ message: String((e as CustomEvent).detail ?? "Something went wrong."), at: Date.now() });
    window.addEventListener("urbantwin-problem", onProblem);
    return () => window.removeEventListener("urbantwin-problem", onProblem);
  }, []);
  useEffect(() => {
    if (!problem) return;
    const id = window.setTimeout(() => setProblem(null), 9000);
    return () => window.clearTimeout(id);
  }, [problem]);
  if (!problem) return null;
  return (
    <div role="alert" className="glass rise fixed left-1/2 top-16 z-[60] flex max-w-md -translate-x-1/2 items-start gap-2 border-amber-500/50 px-3.5 py-2.5 text-xs text-amber-100">
      <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
      <span>{problem.message}</span>
      <button className="ml-2 text-amber-300/70 hover:text-white" aria-label="Dismiss" onClick={() => setProblem(null)}>
        ✕
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ ask the city */

type Answer = {
  question: string;
  understood: boolean;
  answer: string;
  sql: string | null;
  params: Record<string, unknown>;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  caveats: string[];
  examples?: string[];
};
const EXAMPLES = ["Which ward has the most unresolved drain reports?", "How many high severity reports in the last 7 days?", "What is the most common problem?", "Show the oldest unresolved reports."];

export function AskCity() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [res, setRes] = useState<Answer | null>(null);

  async function ask(question: string) {
    if (question.trim().length < 3) return;
    setBusy(true);
    setError("");
    try {
      setRes(
        await apiJson<Answer>("/api/insights/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        }),
      );
    } catch (e) {
      setRes(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 hover:border-sky-500"
      >
        <Icon name="search" className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">Ask the city</span>
      </button>
      {open ? (
        <div className="glass absolute right-0 z-50 mt-2 w-[min(32rem,92vw)] space-y-3 p-3.5 text-xs">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void ask(q);
            }}
            className="flex gap-2"
          >
            <input className="min-w-0 flex-1 px-2.5 py-1.5" placeholder="e.g. Which ward has the most unresolved drain reports?" value={q} onChange={(e) => setQ(e.target.value)} maxLength={300} autoFocus />
            <button className="rounded-md bg-sky-600 px-3 py-1.5 font-medium text-white hover:bg-sky-500 disabled:opacity-50" disabled={busy}>
              {busy ? "…" : "Ask"}
            </button>
          </form>
          {!res && !error ? (
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-400 hover:border-sky-500 hover:text-slate-200"
                  onClick={() => {
                    setQ(ex);
                    void ask(ex);
                  }}
                >
                  {ex}
                </button>
              ))}
            </div>
          ) : null}
          {error ? <Notice tone="warn">{error}</Notice> : null}
          {res ? (
            <div className="space-y-2">
              <p className={`text-sm ${res.understood ? "text-white" : "text-amber-200"}`}>{res.answer}</p>
              {res.rows.length ? (
                <div className="overflow-x-auto rounded-lg border border-slate-800">
                  <table className="w-full text-left">
                    <thead className="text-slate-400">
                      <tr>
                        {res.columns.map((c) => (
                          <th key={c} className="px-2 py-1 font-medium">
                            {titleCase(c)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {res.rows.map((row, i) => (
                        <tr key={i} className="border-t border-slate-800">
                          {res.columns.map((c) => (
                            <td key={c} className="px-2 py-1 text-slate-200">
                              {c === "category" ? categoryLabel(String(row[c])) : String(row[c] ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
              {res.sql ? (
                <details open>
                  <summary className="cursor-pointer text-slate-300">Query used (so you can check the answer)</summary>
                  <pre className="mt-1 overflow-x-auto rounded-lg bg-slate-950 p-2 text-[11px] leading-snug text-sky-200">{res.sql}</pre>
                  <pre className="mt-1 overflow-x-auto rounded-lg bg-slate-950 p-2 text-[11px] leading-snug text-slate-400">parameters: {JSON.stringify(res.params)}</pre>
                </details>
              ) : null}
              {res.examples ? (
                <ul className="list-disc pl-4 text-slate-400">
                  {res.examples.map((ex) => (
                    <li key={ex}>{ex}</li>
                  ))}
                </ul>
              ) : null}
              <ul className="list-disc pl-4 text-[11px] text-slate-500">
                {res.caveats.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <p className="text-[10.5px] text-slate-500">Answers come from fixed, read-only database queries chosen by keyword. No AI writes the SQL and nothing is guessed.</p>
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ live alerts */

type Alert = { id: number; tracking_id: string; category: string; severity: string; created_at: string | null; is_demo: boolean; note: string };

function parseBlock(block: string): { event: string; data: string } | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  return data.length ? { event, data: data.join("\n") } : null;
}

export function AlertsBell() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<"connecting" | "live" | "reconnecting" | "login">("connecting");
  const [toast, setToast] = useState<Alert | null>(null);
  const openRef = useRef(false);
  openRef.current = open;

  useEffect(() => {
    let stop = false;
    let controller: AbortController | null = null;
    let lastId: number | null = null;

    const onAlert = (a: Alert) => {
      lastId = Math.max(lastId ?? 0, a.id);
      setAlerts((prev) => (prev.some((x) => x.id === a.id) ? prev : [a, ...prev].slice(0, 20)));
      if (!openRef.current) setUnread((n) => n + 1);
      setToast(a);
    };

    async function run() {
      while (!stop) {
        controller = new AbortController();
        try {
          const res = await apiFetch(`/api/insights/alerts/stream${lastId != null ? `?since_id=${lastId}` : ""}`, { signal: controller.signal }, { quiet: true });
          if (res.status === 401) {
            setState("login");
            return;
          }
          if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
          setState("live");
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let end: number;
            while ((end = buffer.indexOf("\n\n")) >= 0) {
              const parsed = parseBlock(buffer.slice(0, end));
              buffer = buffer.slice(end + 2);
              if (!parsed) continue;
              const payload = JSON.parse(parsed.data);
              if (parsed.event === "ready" || parsed.event === "bye") lastId = Math.max(lastId ?? 0, payload.latest_id ?? 0);
              else if (parsed.event === "alert") onAlert(payload as Alert);
            }
          }
          // the server ends each stream after a short time; reconnect straight away, resuming after the last id seen
          await new Promise((r) => setTimeout(r, 300));
          continue;
        } catch {
          if (stop) return;
        }
        setState("reconnecting");
        await new Promise((r) => setTimeout(r, 5000));
      }
    }
    void run();
    return () => {
      stop = true;
      controller?.abort();
    };
  }, []);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 10000);
    return () => window.clearTimeout(id);
  }, [toast]);

  const dot = state === "live" ? "bg-emerald-400" : state === "login" ? "bg-slate-500" : "bg-amber-400";
  const label = state === "live" ? "Live alerts on" : state === "login" ? "Log in for live alerts" : "Reconnecting to live alerts…";

  return (
    <div className="relative">
      <button
        type="button"
        title={label}
        aria-label={`Alerts. ${label}`}
        onClick={() => {
          setOpen(!open);
          setUnread(0);
        }}
        className="relative grid h-8 w-8 place-items-center rounded-lg border border-slate-700 text-slate-300 hover:border-sky-500"
      >
        <Icon name="alert" className="h-4 w-4" />
        <span className={`absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full ${dot}`} />
        {unread ? (
          <span className="num absolute -bottom-1 -right-1 min-w-4 rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white">{unread}</span>
        ) : null}
      </button>
      {open ? (
        <div className="glass absolute right-0 z-50 mt-2 w-80 p-3 text-xs">
          <p className="eyebrow mb-2">High and critical reports · {label}</p>
          {alerts.length ? (
            <ul className="space-y-1.5">
              {alerts.map((a) => (
                <li key={a.id}>
                  <Link to={`/investigator/${a.tracking_id}`} onClick={() => setOpen(false)} className="block rounded-lg border border-slate-800 bg-slate-950/50 p-2 hover:border-sky-500/60">
                    <span className="flex items-center justify-between">
                      <span className="font-mono text-[11px] text-slate-400">{a.tracking_id}</span>
                      <span className="font-medium" style={{ color: SEVERITY_COLOR[a.severity] }}>{titleCase(a.severity)}</span>
                    </span>
                    <span className="text-slate-200">{categoryLabel(a.category)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-slate-500">Nothing new since you opened this page. New high-severity reports appear here as they arrive.</p>
          )}
          <p className="mt-2 text-[10.5px] text-slate-500">An alert is a new citizen report, not a verified issue.</p>
        </div>
      ) : null}
      {toast ? (
        <Link
          to={`/investigator/${toast.tracking_id}`}
          onClick={() => setToast(null)}
          className="glass rise fixed right-4 top-16 z-[60] block w-72 border-rose-500/50 p-3 text-xs"
        >
          <p className="eyebrow" style={{ color: SEVERITY_COLOR[toast.severity] }}>
            New {toast.severity} report
          </p>
          <p className="mt-0.5 text-sm font-semibold text-white">{categoryLabel(toast.category)}</p>
          <p className="font-mono text-[11px] text-slate-400">{toast.tracking_id}</p>
          <p className="mt-1 text-[11px] text-slate-400">{toast.note} Click to review.</p>
        </Link>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ data quality */

type Quality = {
  generated_at: string;
  reports: {
    total: number;
    demo: number;
    reviewed_by_person: number;
    reviewed_pct: number | null;
    linked_to_verified_issue: number;
    with_photo_evidence: number;
    evidence_pct: number | null;
    stale_open: number;
    stale_after_days: number;
  };
  freshness: { newest_report_age_days: number | null; oldest_report_age_days: number | null; median_report_age_days: number | null };
  coverage: { wards: Array<{ ward: string; number: number; reports: number; thin: boolean }>; reports_outside_wards: number; thin_wards: number; ward_note: string };
  layers: { demo_layers: string[]; building_height_sources: Record<string, number>; buildings: number; buildings_with_measured_height: number };
  warnings: string[];
};

const age = (d: number | null) => (d == null ? "–" : d < 1 ? `${Math.round(d * 24)} h` : `${d.toFixed(1)} d`);

export function QualityPanel() {
  const [q, setQ] = useState<Quality | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    apiJson<Quality>("/api/insights/quality").then(setQ).catch((e: Error) => setError(e.message));
  }, []);
  if (error) return <Notice tone="warn">Data-quality summary unavailable: {error}</Notice>;
  if (!q) return null;
  const measuredPct = q.layers.buildings ? Math.round((100 * q.layers.buildings_with_measured_height) / q.layers.buildings) : null;
  return (
    <Panel title="Data quality" subtitle="How far to trust what the dashboards show">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Reviewed by a person" value={q.reports.reviewed_pct == null ? "–" : `${q.reports.reviewed_pct}%`} sub={`${q.reports.reviewed_by_person} of ${q.reports.total} reports`} icon="check" color="#34d399" />
        <Kpi label="With photo evidence" value={q.reports.evidence_pct == null ? "–" : `${q.reports.evidence_pct}%`} sub={`${q.reports.with_photo_evidence} of ${q.reports.total}`} icon="camera" color="#38bdf8" />
        <Kpi label={`Waiting >${q.reports.stale_after_days} days`} value={q.reports.stale_open} sub="unreviewed reports" icon="clock" color={q.reports.stale_open ? "#fb923c" : "#34d399"} />
        <Kpi label="Newest report" value={age(q.freshness.newest_report_age_days)} sub={`median age ${age(q.freshness.median_report_age_days)}`} icon="pin" color="#818cf8" />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <h3 className="eyebrow mb-2">Reports per ward (orange = thin coverage)</h3>
          <HBars
            rows={q.coverage.wards.map((w) => ({
              label: w.ward.replace(" (demonstration grid)", ""),
              value: w.reports,
              color: w.thin ? "#fb923c" : "#22d3ee",
            }))}
          />
          <p className="mt-2 text-[11px] text-slate-500">{q.coverage.ward_note} A ward with few reports may simply have few reporters.</p>
        </div>
        <div>
          <h3 className="eyebrow mb-2">What to keep in mind</h3>
          {q.warnings.length ? (
            <ul className="space-y-1.5">
              {q.warnings.map((w) => (
                <li key={w}>
                  <Notice tone="warn">{w}</Notice>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-500">No data-quality warnings.</p>
          )}
          {measuredPct != null ? <p className="mt-2 text-[11px] text-slate-500">Buildings with a measured height in OSM: {measuredPct}%.</p> : null}
        </div>
      </div>
    </Panel>
  );
}
