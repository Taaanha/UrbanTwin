import { useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { getStaffName, getStaffToken, setStaffSession } from "./api";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `whitespace-nowrap rounded px-3 py-1.5 text-sm ${isActive ? "bg-slate-800 text-white" : "text-slate-300 hover:text-white"}`;

const STAFF_LINKS: Array<[string, string]> = [
  ["/overview", "Overview"],
  ["/dashboard", "City Map & Monitor"],
  ["/investigator", "Investigator"],
  ["/intelligence", "Intelligence"],
  ["/planner", "Planner"],
  ["/accountability", "Accountability"],
  ["/simulation", "Simulation"],
  ["/admin", "Data & Audit"],
];

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
        className={`rounded border px-2 py-1 text-xs ${needsLogin ? "border-amber-500 text-amber-300" : "border-slate-700 text-slate-300"}`}
      >
        {signedIn ? `Staff: ${getStaffName() || "signed in"}` : needsLogin ? "Staff login required" : "Staff login"}
      </button>
      {open ? (
        <form
          onSubmit={submit}
          className="absolute right-0 z-50 mt-2 w-64 space-y-2 rounded border border-slate-700 bg-slate-900 p-3 text-xs shadow-xl"
        >
          <p className="text-slate-400">
            Staff pages need the token from <code>STAFF_TOKEN</code> in <code>backend/.env</code>. Citizens never need it.
          </p>
          <input
            className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1"
            placeholder="Your name (for the audit log)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1"
            placeholder="Staff token"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
          <div className="flex gap-2">
            <button className="flex-1 rounded bg-sky-700 px-2 py-1 text-white" type="submit">
              Save
            </button>
            {signedIn ? (
              <button
                type="button"
                className="rounded border border-slate-600 px-2 py-1"
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
  return (
    <div className="flex h-full flex-col bg-slate-950 text-slate-100">
      <header className="flex items-center justify-between gap-3 border-b border-slate-800 px-4 py-2">
        <Link to="/" className="text-sm font-semibold tracking-wide">
          UrbanTwin
        </Link>
        <nav className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
          <NavLink to="/" className={linkClass} end>
            Citizen report
          </NavLink>
          <NavLink to="/track" className={linkClass}>
            Track
          </NavLink>
          <span className="mx-1 self-center text-slate-700">|</span>
          {STAFF_LINKS.map(([to, label]) => (
            <NavLink key={to} to={to} className={linkClass}>
              {label}
            </NavLink>
          ))}
        </nav>
        <StaffLogin />
      </header>
      <div className="min-h-0 flex-1">
        <Outlet />
      </div>
    </div>
  );
}
