import { QualityPanel } from "../insights";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiJson, money } from "../api";
import {
  AreaChart,
  CHART_COLORS,
  Donut,
  Funnel,
  HBars,
  HeatMatrix,
  Icon,
  Kpi,
  Notice,
  PageHeader,
  Panel,
  SEVERITY_COLOR,
  SEVERITY_ORDER,
  STATUS_COLOR,
  categoryLabel,
  titleCase,
  type Slice,
} from "../ui";

type Counts = Record<string, number>;
type OverviewData = {
  note: string;
  reports: { total: number; demo: number; by_status: Counts; by_severity: Counts; by_category: Counts };
  issues: { total: number; by_status: Counts };
  intelligence: { possible_recurrence_flags: number };
  planner: { interventions: number; by_status: Counts };
  accountability: { projects: number; by_status: Counts; approved_budget_bdt: number };
  timeline: Array<{ date: string; count: number }>;
  matrix: Array<{ category: string; severity: string; count: number }>;
  funnel: Array<{ stage: string; count: number }>;
  audit_entries: number;
};
type Health = { status: string; staff_auth?: string; postgis?: string };

const toSlices = (counts: Counts, color: (k: string, i: number) => string, label = titleCase): Slice[] =>
  Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v], i) => ({ label: label(k), value: v, color: color(k, i) }));

export default function Overview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    apiJson<OverviewData>("/api/overview").then(setData).catch((e: Error) => setError(e.message));
    apiJson<Health>("/api/health").then(setHealth).catch(() => undefined);
  }, []);

  const spark = useMemo(() => data?.timeline.map((d) => d.count) ?? [], [data]);
  const last7 = useMemo(() => (data ? data.timeline.slice(-7).reduce((a, d) => a + d.count, 0) : 0), [data]);

  if (error) return <p className="p-6 text-sm text-amber-300">{error}</p>;
  if (!data) return <p className="p-6 text-sm text-slate-400">Loading the city picture…</p>;

  const openIssues = data.issues.by_status.open ?? 0;
  const flagged = data.intelligence.possible_recurrence_flags;
  const critical = (data.reports.by_severity.critical ?? 0) + (data.reports.by_severity.high ?? 0);
  const unreviewed = data.reports.by_status.submitted ?? 0;
  const inProgress = data.accountability.by_status.in_progress ?? 0;

  const attention: Array<{ icon: string; color: string; text: string; to: string }> = [];
  if (unreviewed) attention.push({ icon: "camera", color: "#38bdf8", text: `${unreviewed} citizen report${unreviewed > 1 ? "s" : ""} not yet acknowledged`, to: "/dashboard?status=submitted" });
  if (openIssues) attention.push({ icon: "search", color: "#fb923c", text: `${openIssues} verified issue${openIssues > 1 ? "s" : ""} open, with no completed fix`, to: "/investigator" });
  if (flagged) attention.push({ icon: "brain", color: "#818cf8", text: `${flagged} possible recurrence flag${flagged > 1 ? "s" : ""} awaiting human review`, to: "/intelligence" });
  if (inProgress) attention.push({ icon: "shield", color: "#22d3ee", text: `${inProgress} project${inProgress > 1 ? "s" : ""} in progress, so inspections and updates are due`, to: "/accountability" });

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1400px] space-y-5 p-5">
        <PageHeader eyebrow="Command overview" title="Noakhali Paurashava, city picture">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="live-dot" />
            Live database counts · {last7} report{last7 === 1 ? "" : "s"} in the last 7 days
          </div>
        </PageHeader>

        {health?.staff_auth?.startsWith("DISABLED") ? (
          <Notice tone="warn">Staff login is disabled. Set STAFF_TOKEN in backend/.env before showing this to anyone else.</Notice>
        ) : null}
        {data.reports.demo > 0 ? (
          <Notice>
            {data.reports.demo} of {data.reports.total} reports are labelled <strong>DEMO data</strong> (synthetic, not real incidents).
          </Notice>
        ) : null}

        <section className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Kpi step={1} label="Reports" value={data.reports.total} sub={`${critical} critical or high`} to="/dashboard" icon="camera" color="#38bdf8" spark={spark} />
          <Kpi step={2} label="Verified issues" value={data.issues.total} sub={`${openIssues} open`} to="/investigator" icon="search" color="#fb923c" />
          <Kpi step={3} label="Recurrence" value={flagged} sub="Screening signals, unverified" to="/intelligence" icon="brain" color="#818cf8" />
          <Kpi step={4} label="Interventions" value={data.planner.interventions} sub="Proposed, not approved works" to="/planner" icon="wrench" color="#34d399" />
          <Kpi step={5} label="Projects" value={data.accountability.projects} sub={`${money(data.accountability.approved_budget_bdt)} approved`} to="/accountability" icon="shield" color="#22d3ee" />
        </section>

        <section className="grid gap-4 xl:grid-cols-3">
          <Panel title="Reports received" subtitle="Per day, last 30 days (UTC)" className="xl:col-span-2">
            <AreaChart data={data.timeline} />
          </Panel>
          <Panel title="Needs attention" subtitle="Where a person should look next">
            {attention.length ? (
              <ul className="space-y-2">
                {attention.map((a) => (
                  <li key={a.text}>
                    <Link
                      to={a.to}
                      className="group flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-950/50 p-2.5 text-xs text-slate-200 hover:border-sky-500/60"
                    >
                      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md" style={{ background: `${a.color}1f`, color: a.color }}>
                        <Icon name={a.icon} className="h-3.5 w-3.5" />
                      </span>
                      <span className="flex-1">{a.text}</span>
                      <Icon name="arrow" className="h-3.5 w-3.5 text-slate-600 group-hover:text-sky-300" />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-slate-500">Nothing is waiting on a person right now.</p>
            )}
          </Panel>
        </section>

        <section className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <Panel title="Priority matrix" subtitle="Reports by category and severity">
            <HeatMatrix cells={data.matrix} onCell={(category, severity) => navigate(`/dashboard?category=${category}&severity=${severity}`)} />
          </Panel>
          <Panel title="Severity mix" subtitle="As reported by citizens, not yet verified">
            <Donut
              centerLabel="reports"
              slices={SEVERITY_ORDER.filter((s) => data.reports.by_severity[s]).map((s) => ({
                label: titleCase(s),
                value: data.reports.by_severity[s],
                color: SEVERITY_COLOR[s],
              }))}
            />
            <h3 className="eyebrow mb-2 mt-5">By category</h3>
            <HBars rows={toSlices(data.reports.by_category, (_, i) => CHART_COLORS[i % CHART_COLORS.length], categoryLabel)} />
          </Panel>
          <Panel title="From report to repair" subtitle="How far reports travel through the pipeline">
            <Funnel stages={data.funnel} />
            <h3 className="eyebrow mb-2 mt-5">Report handling</h3>
            <HBars rows={toSlices(data.reports.by_status, (k) => STATUS_COLOR[k] ?? "#94a3b8")} />
          </Panel>
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          <Panel title="Issue status">
            <HBars rows={toSlices(data.issues.by_status, (k) => STATUS_COLOR[k] ?? "#94a3b8")} />
          </Panel>
          <Panel title="Intervention status">
            <HBars rows={toSlices(data.planner.by_status, (k) => STATUS_COLOR[k] ?? "#818cf8")} />
          </Panel>
          <Panel title="Project status">
            <HBars rows={toSlices(data.accountability.by_status, (k) => STATUS_COLOR[k] ?? "#22d3ee")} />
          </Panel>
        </section>

        <QualityPanel />

        <p className="pb-4 text-xs leading-relaxed text-slate-500">
          {data.note} A report is a citizen submission. An issue exists only after a staff member verifies it. Interventions are
          proposals and projects are approved works. Nothing here is an official municipal record unless it came from one.
          Audit log entries: {data.audit_entries}.
        </p>
      </div>
    </div>
  );
}
