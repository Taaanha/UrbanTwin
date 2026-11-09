import { useCallback, useEffect, useState } from "react";
import { Badge, STATUS_COLOR, titleCase } from "../ui";
import { useNavigate, useParams } from "react-router-dom";
import { apiFetch, apiJson, money } from "../api";

type Brief = {
  public_id: string;
  title: string;
  status: string;
  is_demo: boolean;
  issue_public_id: string | null;
  issue_status: string | null;
  approved_budget_bdt: number;
  spent_bdt: number;
  progress_pct: number;
  contractor_name: string | null;
  completed_at: string | null;
  review_flag: string;
};
type Check = { check: string; status: string; detail: string };
type Findings = {
  disclaimer: string;
  context_limitations: string;
  checks: Check[];
  recurrence: Array<{ issue_public_id: string; distance_m: number; days_after_completion: number; faster_than_threshold: boolean }>;
  review_flag: string;
  reasons: string[];
};
type Detail = Brief & {
  specification: string;
  updates: Array<{ id: number; progress_pct: number; expenditure_bdt: number; note: string; author: string; created_at: string }>;
  inspections: Array<{ id: number; inspector: string; independent: boolean; outcome: string; condition_score: number | null; notes: string }>;
  evidence: Array<{ id: number; kind: string; original_name: string; url: string }>;
  lifecycle: Array<{ stage: string; ref: string; at: string | null; detail: string }>;
  findings: Findings | null;
};
type Eligible = { public_id: string; title: string; issue_public_id: string | null; indicative_mid_bdt: number | null };
type Summary = { disclaimer: string; projects: number; flagged_for_review: number; approved_budget_bdt: number; spent_bdt: number };

const badge = (flag: string) =>
  flag === "worth_independent_review"
    ? "bg-amber-900 text-amber-200"
    : flag === "none"
      ? "bg-emerald-900 text-emerald-200"
      : "bg-slate-800 text-slate-300";
const flagText = (flag: string) =>
  flag === "worth_independent_review" ? "Worth independent review" : flag === "none" ? "No flags" : "Not completed";
const input = "w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs";
const btn = "rounded bg-sky-700 px-3 py-1 text-xs text-white disabled:opacity-50";

export default function Accountability() {
  const params = useParams();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [projects, setProjects] = useState<Brief[]>([]);
  const [eligible, setEligible] = useState<Eligible[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      setSummary(await apiJson<Summary>("/api/accountability/summary"));
      setProjects((await apiJson<{ items: Brief[] }>("/api/accountability/projects")).items);
      setEligible((await apiJson<{ items: Eligible[] }>("/api/accountability/eligible-interventions")).items);
    } catch (e) {
      setMessage((e as Error).message);
    }
  }, []);

  const open = useCallback(async (id: string) => {
    try {
      setDetail(await apiJson<Detail>(`/api/accountability/projects/${id}`));
    } catch (e) {
      setMessage((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);
  useEffect(() => {
    if (params.publicId) void open(params.publicId);
  }, [params.publicId, open]);

  async function send(url: string, form: FormData | Record<string, unknown>, then?: string) {
    setBusy(true);
    setMessage("");
    try {
      const isForm = form instanceof FormData;
      const response = await apiFetch(url, {
        method: "POST",
        body: isForm ? form : JSON.stringify(form),
        headers: isForm ? undefined : { "Content-Type": "application/json" },
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body));
      await loadAll();
      const id = (body as Brief).public_id ?? then;
      if (id) {
        navigate(`/accountability/${id}`);
        await open(id);
      }
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function submitCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    void send("/api/accountability/projects", {
      intervention_public_id: f.get("intervention"),
      approved_budget_bdt: Number(f.get("budget")),
      specification: f.get("spec"),
      contractor_name: (f.get("contractor") as string) || null,
    });
    e.currentTarget.reset();
  }

  function submitForm(path: string) {
    return (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!detail) return;
      const form = new FormData(e.currentTarget);
      void send(`/api/accountability/projects/${detail.public_id}/${path}`, form, detail.public_id);
      e.currentTarget.reset();
    };
  }

  return (
    <div className="grid h-full grid-cols-1 overflow-hidden md:grid-cols-[360px_1fr]">
      <aside className="space-y-4 overflow-y-auto border-r border-slate-800 p-4 text-xs">
        <div>
          <p className="eyebrow">Module 5</p>
          <h2 className="text-base font-semibold text-white">City Accountability</h2>
        </div>
        {summary ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              {[
                ["Projects", String(summary.projects), "#22d3ee"],
                ["Flagged for review", String(summary.flagged_for_review), "#fbbf24"],
                ["Approved", money(summary.approved_budget_bdt), "#34d399"],
                ["Recorded spend", money(summary.spent_bdt), "#818cf8"],
              ].map(([label, value, color]) => (
                <div key={label} className="panel p-3">
                  <p className="eyebrow">{label}</p>
                  <p className="num mt-1 text-base font-semibold" style={{ color }}>
                    {value}
                  </p>
                </div>
              ))}
            </div>
            <p className="rounded-md bg-slate-900/70 p-2.5 text-[11px] leading-relaxed text-slate-400 ring-1 ring-slate-800">{summary.disclaimer}</p>
          </div>
        ) : null}
        {message ? <p className="rounded border border-amber-700 bg-amber-950 p-2 text-amber-200">{message}</p> : null}

        <ul className="space-y-2">
          {projects.map((p) => (
            <li key={p.public_id}>
              <button
                onClick={() => navigate(`/accountability/${p.public_id}`)}
                className={`panel w-full p-3 text-left transition-colors ${detail?.public_id === p.public_id ? "!border-sky-400" : "hover:border-slate-500"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[11px] text-slate-400">{p.public_id}</span>
                  {p.is_demo ? <Badge color="#22d3ee">DEMO</Badge> : null}
                </div>
                <div className="mt-1 text-sm font-medium text-white">{p.title}</div>
                <div className="mt-2 flex items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800">
                    <div className="h-full rounded-full" style={{ width: `${p.progress_pct}%`, background: STATUS_COLOR[p.status] ?? "#22d3ee" }} />
                  </div>
                  <span className="num text-[11px] text-slate-300">{p.progress_pct}%</span>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <Badge color={STATUS_COLOR[p.status] ?? "#94a3b8"}>{titleCase(p.status)}</Badge>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] ${badge(p.review_flag)}`}>{flagText(p.review_flag)}</span>
                </div>
              </button>
            </li>
          ))}
          {!projects.length ? <li className="text-slate-500">No projects yet.</li> : null}
        </ul>

        <form onSubmit={submitCreate} className="space-y-2 rounded border border-slate-800 p-3">
          <h2 className="text-sm font-medium">Approve a project from an intervention</h2>
          <select name="intervention" required className={input}>
            <option value="">Choose intervention…</option>
            {eligible.map((i) => (
              <option key={i.public_id} value={i.public_id}>
                {i.public_id} · {i.issue_public_id} · est. {money(i.indicative_mid_bdt)}
              </option>
            ))}
          </select>
          <input name="budget" type="number" min="1" step="any" required placeholder="Approved budget (BDT)" className={input} />
          <textarea name="spec" required minLength={10} placeholder="Specification (what must be built, to what standard)" className={input} />
          <input name="contractor" placeholder="Contractor (only if authorised to record)" className={input} />
          <button className={btn} disabled={busy}>
            Create project
          </button>
        </form>
      </aside>

      <main className="space-y-4 overflow-y-auto p-5 text-xs">
        {!detail ? (
          <p className="text-slate-400">Select a project to see its full chain: problem → intervention → project → progress → inspection → recurrence.</p>
        ) : (
          <>
            <header>
              <h2 className="font-mono text-sm">{detail.public_id}</h2>
              <p className="text-slate-300">{detail.title}</p>
              <p className="text-slate-400">
                Issue {detail.issue_public_id} ({detail.issue_status}) · budget {money(detail.approved_budget_bdt)} · recorded spending{" "}
                {money(detail.spent_bdt)} · {detail.contractor_name ?? "contractor not recorded"}
              </p>
              <p className="mt-1 text-slate-400">Specification: {detail.specification}</p>
            </header>

            {detail.findings ? (
              <section className="rounded border border-slate-800 bg-slate-900 p-3">
                <h3 className="mb-1 text-sm font-medium">
                  Screening result{" "}
                  <span className={`rounded px-1 ${badge(detail.findings.review_flag)}`}>{flagText(detail.findings.review_flag)}</span>
                </h3>
                <p className="mb-2 text-slate-400">{detail.findings.disclaimer}</p>
                <ul className="space-y-1">
                  {detail.findings.checks.map((c) => (
                    <li key={c.check}>
                      <span className="font-mono">{c.check}</span> — <b>{c.status}</b>: {c.detail}
                    </li>
                  ))}
                </ul>
                {detail.findings.reasons.length ? (
                  <ul className="mt-2 list-disc pl-4 text-amber-200">
                    {detail.findings.reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                ) : null}
                <p className="mt-2 text-slate-500">{detail.findings.context_limitations}</p>
              </section>
            ) : null}

            <section>
              <h3 className="mb-1 text-sm font-medium">Lifecycle</h3>
              <ol className="space-y-1 border-l border-slate-700 pl-3">
                {detail.lifecycle.map((s, i) => (
                  <li key={i}>
                    <span className="font-mono text-sky-300">{s.stage.replace(/_/g, " ")}</span> · {s.ref}
                    {s.at ? <span className="text-slate-500"> · {s.at.slice(0, 10)}</span> : null}
                    <div className="text-slate-400">{s.detail}</div>
                  </li>
                ))}
              </ol>
            </section>

            <section>
              <h3 className="mb-1 text-sm font-medium">Evidence files</h3>
              <ul className="flex flex-wrap gap-2">
                {detail.evidence.map((e) => (
                  <li key={e.id} className="rounded border border-slate-800 px-2 py-1">
                    {e.kind}: {e.original_name} <EvidenceLink url={e.url} />
                  </li>
                ))}
                {!detail.evidence.length ? <li className="text-slate-500">None uploaded.</li> : null}
              </ul>
            </section>

            {detail.status !== "completed" && detail.status !== "cancelled" ? (
              <div className="grid gap-3 md:grid-cols-2">
                <form onSubmit={submitForm("updates")} className="space-y-2 rounded border border-slate-800 p-3">
                  <h3 className="text-sm font-medium">Add progress update</h3>
                  <input name="progress_pct" type="number" min={0} max={100} required placeholder="Progress %" className={input} />
                  <input name="expenditure_bdt" type="number" min={0} step="any" defaultValue={0} placeholder="Spent in this period (BDT)" className={input} />
                  <input name="note" required minLength={3} placeholder="What was done" className={input} />
                  <input name="files" type="file" accept="image/*" multiple className={input} />
                  <button className={btn} disabled={busy}>Save update</button>
                </form>
                <form onSubmit={submitForm("complete")} className="space-y-2 rounded border border-slate-800 p-3">
                  <h3 className="text-sm font-medium">Report completion</h3>
                  <input name="note" required minLength={3} placeholder="Completion note" className={input} />
                  <input name="completed_on" type="date" className={input} />
                  <input name="files" type="file" accept="image/*" multiple required className={input} />
                  <p className="text-slate-500">At least one completion photo is required.</p>
                  <button className={btn} disabled={busy}>Mark complete</button>
                </form>
              </div>
            ) : null}

            {detail.status === "completed" ? (
              <form onSubmit={submitForm("inspections")} className="max-w-md space-y-2 rounded border border-slate-800 p-3">
                <h3 className="text-sm font-medium">Record an inspection</h3>
                <input name="inspector" required placeholder="Inspector name / body" className={input} />
                <select name="outcome" className={input} defaultValue="meets_specification">
                  <option value="meets_specification">Meets specification</option>
                  <option value="partially_meets">Partially meets</option>
                  <option value="does_not_meet">Does not meet</option>
                  <option value="inconclusive">Inconclusive</option>
                </select>
                <select name="independent" className={input} defaultValue="false">
                  <option value="false">Internal inspection</option>
                  <option value="true">Independent inspection (not the delivery team)</option>
                </select>
                <input name="condition_score" type="number" min={1} max={5} placeholder="Condition 1–5 (optional)" className={input} />
                <textarea name="notes" required minLength={3} placeholder="Findings" className={input} />
                <input name="files" type="file" accept="image/*" multiple className={input} />
                <button className={btn} disabled={busy}>Save inspection</button>
              </form>
            ) : null}

            {detail.inspections.length ? (
              <section>
                <h3 className="mb-1 text-sm font-medium">Inspections</h3>
                <ul className="space-y-1">
                  {detail.inspections.map((i) => (
                    <li key={i.id}>
                      {i.independent ? "Independent" : "Internal"} · {i.inspector} · <b>{i.outcome}</b>
                      {i.condition_score ? ` · condition ${i.condition_score}/5` : ""} — {i.notes}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </>
        )}
      </main>
    </div>
  );
}

/** Evidence needs the staff header, so fetch it as a blob and open it. */
function EvidenceLink({ url }: { url: string }) {
  async function show() {
    const response = await apiFetch(url);
    if (!response.ok) return;
    const blob = await response.blob();
    window.open(URL.createObjectURL(blob), "_blank");
  }
  return (
    <button type="button" className="ml-1 text-sky-300 underline" onClick={() => void show()}>
      view
    </button>
  );
}
