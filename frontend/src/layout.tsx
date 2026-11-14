import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { apiFetch, getStaffName, getStaffToken, setStaffSession } from "./api";
import { AlertsBell, AskCity, ProblemToast } from "./insights";
import { Icon, PageBoundary } from "./ui";

type NavItem = { to: string; label: string; icon: string; step?: number; end?: boolean };

const PUBLIC_LINKS: NavItem[] = [
  { to: "/", label: "Report a problem", icon: "camera", end: true },
  { to: "/track", label: "Track a report", icon: "search" },
];
const MODULE_LINKS: NavItem[] = [
  { to: "/overview", label: "Command overview", icon: "grid" },
  { to: "/dashboard", label: "City Monitor", icon: "map", step: 1 },
  { to: "/live3d", label: "Live 3D City", icon: "map" },
  { to: "/investigator", label: "City Investigator", icon: "search", step: 2 },
  { to: "/intelligence", label: "City Intelligence", icon: "brain", step: 3 },
  { to: "/planner", label: "City Planner", icon: "wrench", step: 4 },
  { to: "/accountability", label: "Accountability", icon: "shield", step: 5 },
  { to: "/observatory", label: "Infrastructure Observatory", icon: "flame" },
  { to: "/simulation", label: "City Simulation", icon: "flask", step: 6 },
];
const SYSTEM_LINKS: NavItem[] = [{ to: "/admin", label: "Data & audit", icon: "database" }];

const ALL = [...PUBLIC_LINKS, ...MODULE_LINKS, ...SYSTEM_LINKS];

function titleFor(path: string): string {
  const hit = ALL.filter((i) => (i.end ? path === i.to : path.startsWith(i.to) && i.to !== "/")).sort((a, b) => b.to.length - a.to.length)[0];
  return hit?.label ?? "UrbanTwin";
}

const itemClass = ({ isActive }: { isActive: boolean }) =>
  `group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors ${
    isActive
      ? "bg-sky-500/15 font-medium text-sky-200 shadow-[inset_2px_0_0_#22d3ee]"
      : "text-slate-400 hover:bg-slate-800/70 hover:text-slate-100"
  }`;

function NavGroup({ title, items, onNavigate }: { title: string; items: NavItem[]; onNavigate: () => void }) {
  return (
    <div className="mb-5">
      <p className="eyebrow mb-1.5 px-3">{title}</p>
      <nav className="space-y-0.5">
        {items.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={itemClass} onClick={onNavigate}>
            <Icon name={item.icon} className="h-4 w-4 shrink-0" />
            <span className="flex-1 truncate">{item.label}</span>
            {item.step ? <span className="num text-[10px] text-slate-600 group-hover:text-slate-400">{item.step}</span> : null}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  return (
    <div className="hidden items-center gap-1.5 text-xs text-slate-400 lg:flex">
      <Icon name="clock" className="h-3.5 w-3.5" />
      <span className="num">
        {now.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })} ·{" "}
        {now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
      </span>
    </div>
  );
}

type Health = { status?: string; database?: string; staff_auth?: string };

function StatusChips() {
  const [health, setHealth] = useState<Health | null | "down">(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      apiFetch("/api/health", {}, { quiet: true })
        .then((r) => r.json())
        .then((h: Health) => alive && setHealth(h))
        .catch(() => alive && setHealth("down"));
    load();
    const id = window.setInterval(load, 60_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);
  const ok = health && health !== "down" && health.status === "ok" && health.database === "connected";
  const open = health && health !== "down" && health.staff_auth?.startsWith("DISABLED");
  return (
    <div className="hidden items-center gap-2 md:flex">
      <span
        className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] ${
          ok ? "border-emerald-500/40 text-emerald-300" : "border-amber-500/40 text-amber-300"
        }`}
        title="Backend and PostGIS connection"
      >
        <span className={ok ? "live-dot" : "h-2 w-2 rounded-full bg-amber-400"} />
        {health === null ? "Checking…" : ok ? "PostGIS connected" : "Backend offline"}
      </span>
      {open ? (
        <span className="rounded-full border border-amber-500/40 px-2.5 py-1 text-[11px] text-amber-300" title="STAFF_TOKEN is empty">
          Lab mode · no staff login
        </span>
      ) : null}
    </div>
  );
}

function StaffLogin() {
  const [signedIn, setSignedIn] = useState(Boolean(getStaffToken()));
  const [open, setOpen] = useState(false);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [token, setToken] = useState("");
  const [name, setName] = useState(getStaffName() || "");

  useEffect(() => {
    const onAuth = () => setSignedIn(Boolean(getStaffToken()));
    const onDenied = () => {
      setNeedsLogin(true);
      setOpen(true);
    };
    window.addEventListener("urbantwin-auth", onAuth);
    window.addEventListener("urbantwin-unauthorized", onDenied);
    return () => {
      window.removeEventListener("urbantwin-auth", onAuth);
      window.removeEventListener("urbantwin-unauthorized", onDenied);
    };
  }, []);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setStaffSession(token.trim(), name.trim() || "staff");
    setToken("");
    setNeedsLogin(false);
    setOpen(false);
    window.location.reload();
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs ${needsLogin ? "border-amber-500 text-amber-300" : "border-slate-700 text-slate-300 hover:border-sky-500"}`}
      >
        <Icon name="user" className="h-3.5 w-3.5" />
        {signedIn ? getStaffName() || "Signed in" : needsLogin ? "Login required" : "Staff login"}
      </button>
      {open ? (
        <form
          onSubmit={submit}
          className="glass absolute right-0 z-50 mt-2 w-72 space-y-2 p-3 text-xs"
        >
          <p className="text-slate-400">
            Staff pages need the token from <code>STAFF_TOKEN</code> in <code>backend/.env</code>. Citizens never need it.
          </p>
          <input
            className="w-full px-2 py-1.5"
            placeholder="Your name (for the audit log)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="w-full px-2 py-1.5"
            placeholder="Staff token"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
          <div className="flex gap-2">
            <button className="flex-1 rounded-md bg-sky-600 px-2 py-1.5 font-medium text-white hover:bg-sky-500" type="submit">
              Save
            </button>
            {signedIn ? (
              <button
                type="button"
                className="rounded-md border border-slate-600 px-2 py-1.5"
                onClick={() => {
                  setStaffSession("", "");
                  window.location.reload();
                }}
              >
                Sign out
              </button>
            ) : null}
          </div>
        </form>
      ) : null}
    </div>
  );
}

export default function Layout() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const staffArea = pathname !== "/" && !pathname.startsWith("/track");
  const close = () => setOpen(false);
  return (
    <div className="bg-grid flex h-full text-slate-100">
      {open ? <button aria-label="Close menu" className="fixed inset-0 z-30 bg-black/60 md:hidden" onClick={close} /> : null}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-60 shrink-0 flex-col border-r border-slate-800 bg-slate-950/95 px-3 py-4 backdrop-blur transition-transform md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Link to="/overview" onClick={close} className="mb-6 flex items-center gap-2.5 px-2">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-indigo-500 text-slate-950 shadow-lg shadow-cyan-500/20">
            <Icon name="layers" className="h-5 w-5" />
          </span>
          <span>
            <span className="block text-[15px] font-semibold leading-4 tracking-tight text-white">UrbanTwin</span>
            <span className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Noakhali Paurashava</span>
          </span>
        </Link>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <NavGroup title="Citizens" items={PUBLIC_LINKS} onNavigate={close} />
          <NavGroup title="Staff modules" items={MODULE_LINKS} onNavigate={close} />
          <NavGroup title="System" items={SYSTEM_LINKS} onNavigate={close} />
        </div>
        <p className="mt-3 rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 text-[10.5px] leading-snug text-slate-500">
          AI output and screening signals are candidates for human review, never findings or accusations.
        </p>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="relative z-40 flex items-center gap-3 border-b border-slate-800 bg-slate-950/70 px-4 py-2.5 backdrop-blur">
          <button
            type="button"
            className="rounded-lg border border-slate-700 p-1.5 text-slate-300 md:hidden"
            aria-label="Open menu"
            onClick={() => setOpen(true)}
          >
            <Icon name="menu" className="h-4 w-4" />
          </button>
          <div className="min-w-0">
            <p className="eyebrow">UrbanTwin</p>
            <h1 className="truncate text-sm font-semibold text-white">{titleFor(pathname)}</h1>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <Clock />
            <StatusChips />
            {staffArea ? <AskCity /> : null}
            {staffArea ? <AlertsBell /> : null}
            <StaffLogin />
          </div>
        </header>
        <ProblemToast />
        <main className="min-h-0 flex-1">
          <PageBoundary key={pathname}>
            <Outlet />
          </PageBoundary>
        </main>
      </div>
    </div>
  );
}
