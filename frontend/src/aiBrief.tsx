import { useEffect, useState } from "react";
import { apiJson } from "./api";

type Brief = { status: string; warning: string; provider?: string; local?: boolean } & Record<string, string | string[] | boolean | undefined>;

/** Button + result box for an AI-written draft. The server labels the draft; this only shows it and never changes data. */
export function AiBrief({
  title,
  url,
  method = "GET",
  body,
  fields,
  resetKey,
}: {
  title: string;
  url: string;
  method?: "GET" | "POST";
  body?: unknown;
  fields: Array<[key: string, label: string]>;
  resetKey?: string;
}) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setBrief(null);
    setError("");
  }, [resetKey]);

  async function run() {
    setBusy(true);
    setError("");
    try {
      const init: RequestInit = method === "POST" ? { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) } : {};
      const res = await apiJson<{ brief: Brief }>(url, init);
      setBrief(res.brief);
    } catch (e) {
      setBrief(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 rounded-lg border border-slate-800 p-2.5 text-xs">
      <button type="button" onClick={() => void run()} disabled={busy} className="w-full rounded bg-violet-700 py-1.5 font-medium text-white hover:bg-violet-600 disabled:opacity-50">
        {busy ? "Writing…" : title}
      </button>
      {error ? <p className="mt-2 text-amber-300">{error}</p> : null}
      {brief ? (
        <div className="mt-2 space-y-2">
          <p className="text-[11px] text-amber-300">
            {brief.warning}
            {brief.provider ? ` (${brief.provider}${brief.local ? ", on this machine" : ""})` : ""}
          </p>
          {fields.map(([key, label]) => {
            const value = brief[key];
            if (!value || (Array.isArray(value) && !value.length)) return null;
            return (
              <div key={key}>
                <p className="font-semibold text-slate-200">{label}</p>
                {Array.isArray(value) ? (
                  <ul className="list-disc pl-4 text-slate-300">
                    {value.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-slate-300">{String(value)}</p>
                )}
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
