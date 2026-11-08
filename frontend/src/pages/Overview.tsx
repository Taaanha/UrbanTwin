import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiJson, money } from "../api";

type Counts = Record<string, number>;
type OverviewData = {
  note: string;
  reports: { total: number; demo: number; by_status: Counts; by_severity: Counts; by_category: Counts };
  issues: { total: number; by_status: Counts };
  intelligence: { possible_recurrence_flags: number };
  planner: { interventions: number; by_status: Counts };
  accountability: { projects: number; by_status: Counts; approved_budget_bdt: number };
  audit_entries: number;
};
type Health = { status: string; staff_auth?: string; postgis?: string };

function Card({ title, value, sub, to }: { title: string; value: string | number; sub?: string; to: string }) {
  return (
    <Link to={to} className="rounded border border-slate-800 bg-slate-900 p-4 hover:border-sky-700">
      <div className="text-xs uppercase tracking-wide text-slate-400">{title}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
      {sub ? <div className="mt-1 text-xs text-slate-500">{sub}</div> : null}
    </Link>
  );
}

function Bars({ data }: { data: Counts }) {
  const max = Math.max(1, ...Object.values(data));
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return <p className="text-xs text-slate-500">No records yet.</p>;
  return (
    <ul className="space-y-1 text-xs">
      {entries.map(([key, value]) => (
        <li key={key} className="flex items-center gap-2">
          <span className="w-36 truncate text-slate-300">{key.replace(/_/g, " ")}</span>
          <span className="h-2 rounded bg-sky-600" style={{ width: `${(value / max) * 60}%` }} />
          <span className="text-slate-400">{value}</span>
        </li>
      ))}
    </ul>
  );
}

export default function Overview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiJson<OverviewData>("/api/overview").then(setData).catch((e: Error) => setError(e.message));
    apiJson<Health>("/api/health").then(setHealth).catch(() => undefined);
  }, []);

  if (error) return <p className="p-6 text-sm text-amber-300">{error}</p>;
  if (!data) return <p className="p-6 text-sm text-slate-400">Loading…</p>;

  const open = data.issues.by_status.open ?? 0;
  const flagged = data.intelligence.possible_recurrence_flags;
  return (
    <div className="h-full space-y-5 overflow-y-auto p-5">
      <header>
        <h1 className="text-lg font-semibold">UrbanTwin overview · Noakhali Paurashava (study area)</h1>
        <p className="text-xs text-slate-400">{data.note}</p>
        {health?.staff_auth?.startsWith("DISABLED") ? (
          <p className="mt-2 rounded border border-amber-700 bg-amber-950 p-2 text-xs text-amber-200">
            Staff login is disabled. Set STAFF_TOKEN in backend/.env before showing this to anyone else.
          </p>
        ) : null}
        {data.reports.demo > 0 ? (
          <p className="mt-2 rounded border border-sky-800 bg-sky-950 p-2 text-xs text-sky-200">
            {data.reports.demo} of {data.reports.total} reports are labelled DEMO data (synthetic, not real incidents).
          </p>
        ) : null}
      </header>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Card title="1 · Reports" value={data.reports.total} sub="City Monitor" to="/dashboard" />
        <Card title="2 · Verified issues" value={data.issues.total} sub={`${open} open`} to="/investigator" />
        <Card title="3 · Recurrence flags" value={flagged} sub="City Intelligence" to="/intelligence" />
        <Card title="4 · Interventions" value={data.planner.interventions} sub="City Planner" to="/planner" />
        <Card
          title="5 · Projects"
          value={data.accountability.projects}
          sub={money(data.accountability.approved_budget_bdt) + " approved"}
          to="/accountability"
        />
      </section>

      <section className="grid gap-5 md:grid-cols-3">
        <div className="rounded border border-slate-800 bg-slate-900 p-4">
          <h2 className="mb-2 text-sm font-medium">Reports by category</h2>
          <Bars data={data.reports.by_category} />
        </div>
        <div className="rounded border border-slate-800 bg-slate-900 p-4">
          <h2 className="mb-2 text-sm font-medium">Reports by severity</h2>
          <Bars data={data.reports.by_severity} />
          <h2 className="mb-2 mt-4 text-sm font-medium">Reports by status</h2>
          <Bars data={data.reports.by_status} />
        </div>
        <div className="rounded border border-slate-800 bg-slate-900 p-4">
          <h2 className="mb-2 text-sm font-medium">Issue status</h2>
          <Bars data={data.issues.by_status} />
          <h2 className="mb-2 mt-4 text-sm font-medium">Project status</h2>
          <Bars data={data.accountability.by_status} />
        </div>
      </section>

      <p className="text-xs text-slate-500">
        A report is a citizen submission. An issue exists only after a staff member verifies it. Interventions are
        proposals, projects are approved works, and nothing here is an official municipal record unless it came from
        one. Audit log entries: {data.audit_entries}.
      </p>
    </div>
  );
}
