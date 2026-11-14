import { useEffect, useState } from "react";
import { apiFetch, apiJson } from "../api";

type Item = {
  record_id: string;
  label: string;
  event_date: string | null;
  location: string | null;
  district: string | null;
  description: string;
  source_name: string | null;
  source_url: string | null;
  has_coordinates: boolean;
  coordinate_status: string | null;
  verification_status: string | null;
  notes: string | null;
};
type Register = {
  rules: string[];
  total: number;
  with_coordinates: number;
  summary_note: string | null;
  groups: Array<{ group: string; title: string; note: string; items: Item[] }>;
};

export default function FloodEvidence() {
  const [data, setData] = useState<Register | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      setData(await apiJson<Register>("/api/flood-evidence"));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void load();
  }, []);

  async function importCsv(file?: File) {
    setError("");
    setMessage("");
    const form = new FormData();
    if (file) form.append("file", file);
    const res = await apiFetch("/api/flood-evidence/import", { method: "POST", body: form });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      setError(typeof body.detail === "string" ? body.detail : `Import failed (${res.status}).`);
      return;
    }
    setMessage(`${body.source}: added ${body.added}, updated ${body.updated}${body.skipped_or_adjusted ? `, ${body.skipped_or_adjusted} row(s) skipped or adjusted: ${(body.problems as string[]).slice(0, 3).join(" ")}` : ""}`);
    await load();
  }

  return (
    <div className="mx-auto h-full max-w-4xl space-y-4 overflow-auto p-4 text-sm">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">Flood evidence register</p>
        <p className="mt-1 text-xs text-slate-400">
          A catalogue of what has been collected about flooding and waterlogging in Noakhali, and what each item can and cannot show. It is not a map layer.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <button className="rounded bg-sky-700 px-3 py-1.5 text-white hover:bg-sky-600" onClick={() => void importCsv()}>
          Load bundled November 2026 register
        </button>
        <label className="cursor-pointer rounded border border-slate-700 px-3 py-1.5 text-slate-300 hover:border-sky-500">
          Import another CSV…
          <input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void importCsv(f); }} />
        </label>
      </div>
      {message ? <p className="text-xs text-emerald-400">{message}</p> : null}
      {error ? <p className="rounded border border-amber-500/40 p-2 text-xs text-amber-200">{error}</p> : null}

      <ul className="list-disc space-y-0.5 pl-4 text-[11px] text-amber-300">
        {(data?.rules ?? []).map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>

      {data && data.total === 0 ? <p className="text-slate-400">The register is empty. Load the bundled register to start.</p> : null}
      {data?.summary_note ? <p className="rounded border border-slate-700 p-2 text-xs text-slate-300">{data.summary_note}</p> : null}
      {data ? (
        <p className="text-xs text-slate-400">
          {data.total} records · {data.with_coordinates} with supplied coordinates
        </p>
      ) : null}

      {data?.groups.map((g) => (
        <section key={g.group} className="space-y-2">
          <div>
            <h2 className="font-semibold text-slate-100">
              {g.title} ({g.items.length})
            </h2>
            <p className="text-[11px] text-slate-500">{g.note}</p>
          </div>
          {g.items.map((i) => (
            <article key={i.record_id} className="rounded-lg border border-slate-800 p-3 text-xs">
              <div className="flex flex-wrap items-center gap-x-2 text-slate-400">
                <span className="font-mono text-slate-200">{i.record_id}</span>
                <span>{i.label}</span>
                {i.event_date ? <span>· {i.event_date}</span> : null}
                {i.verification_status ? <span className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-300">{i.verification_status}</span> : null}
                <span className={`rounded px-1.5 py-0.5 ${i.has_coordinates ? "bg-emerald-900/50 text-emerald-200" : "bg-slate-800 text-slate-400"}`}>
                  {i.has_coordinates ? "has coordinates" : `no coordinates${i.coordinate_status ? ` (${i.coordinate_status})` : ""}`}
                </span>
              </div>
              <p className="mt-1 text-slate-100">{i.description}</p>
              {i.location ? <p className="mt-1 text-slate-400">Where: {i.location}</p> : null}
              {i.notes ? <p className="mt-1 text-slate-500">{i.notes}</p> : null}
              {i.source_url ? (
                <a className="mt-1 inline-block text-sky-300 underline" href={i.source_url} target="_blank" rel="noreferrer noopener">
                  {i.source_name ?? "Source"}
                </a>
              ) : i.source_name ? (
                <p className="mt-1 text-slate-500">Source: {i.source_name}</p>
              ) : null}
            </article>
          ))}
        </section>
      ))}
    </div>
  );
}
