import { useEffect, useState } from "react";
import { apiJson } from "../api";

type Source = {
  layer: string;
  source: string;
  license: string;
  crs: string;
  acquired_at: string | null;
  processing_steps: string;
  limitations: string;
  is_demo: boolean;
};
type AuditRow = {
  id: number;
  at: string | null;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string;
  note: string | null;
};

export default function Admin() {
  const [sources, setSources] = useState<Source[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    apiJson<{ items: Source[] }>("/api/data-sources").then((b) => setSources(b.items)).catch((e: Error) => setError(e.message));
    apiJson<{ items: AuditRow[] }>("/api/audit?limit=100").then((b) => setAudit(b.items)).catch(() => undefined);
  }, []);

  return (
    <div className="h-full space-y-6 overflow-y-auto p-5 text-sm">
      {error ? <p className="text-amber-300">{error}</p> : null}
      <section>
        <h1 className="mb-2 text-lg font-semibold">Data management · dataset register</h1>
        <p className="mb-3 text-xs text-slate-400">
          Source, licence, CRS, processing and known limitations for every loaded layer. Rows marked DEMO are synthetic.
        </p>
        <div className="overflow-x-auto rounded border border-slate-800">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900 text-slate-400">
              <tr>
                <th className="p-2">Layer</th>
                <th className="p-2">Source</th>
                <th className="p-2">Licence</th>
                <th className="p-2">CRS</th>
                <th className="p-2">Acquired</th>
                <th className="p-2">Limitations</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((row) => (
                <tr key={row.layer} className="border-t border-slate-800 align-top">
                  <td className="p-2 font-mono">
                    {row.layer} {row.is_demo ? <span className="ml-1 rounded bg-sky-900 px-1 text-sky-200">DEMO</span> : null}
                  </td>
                  <td className="p-2">{row.source}</td>
                  <td className="p-2">{row.license}</td>
                  <td className="p-2">{row.crs}</td>
                  <td className="p-2">{row.acquired_at?.slice(0, 10)}</td>
                  <td className="p-2 text-slate-400">{row.limitations}</td>
                </tr>
              ))}
              {!sources.length ? (
                <tr>
                  <td className="p-3 text-slate-500" colSpan={6}>
                    No datasets registered. Run the OSM import script.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <h2 className="mb-2 text-lg font-semibold">Audit log (latest 100)</h2>
        <div className="overflow-x-auto rounded border border-slate-800">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900 text-slate-400">
              <tr>
                <th className="p-2">When</th>
                <th className="p-2">Who</th>
                <th className="p-2">Action</th>
                <th className="p-2">Entity</th>
                <th className="p-2">Note</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((row) => (
                <tr key={row.id} className="border-t border-slate-800">
                  <td className="p-2">{row.at?.replace("T", " ").slice(0, 19)}</td>
                  <td className="p-2">{row.actor}</td>
                  <td className="p-2 font-mono">{row.action}</td>
                  <td className="p-2">
                    {row.entity_type} {row.entity_id}
                  </td>
                  <td className="p-2 text-slate-400">{row.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
