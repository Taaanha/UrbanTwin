import { useEffect, useRef, useState } from "react";
import { apiJson } from "../api";

type ToolCall = { tool: string; args: Record<string, unknown>; result: unknown };
type Turn =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; warning: string; tools: ToolCall[]; sources: Array<{ title: string; url: string }>; search: { requested: boolean; used: boolean } };
type Reply = {
  answer: string;
  warning: string;
  tool_calls: ToolCall[];
  web_sources: Array<{ title: string; url: string }>;
  web_search: { requested: boolean; used: boolean };
};

const STARTERS = [
  "What should we prioritise this monsoon, and why?",
  "Which wards have the weakest data, and what should we collect first?",
  "If water rises 3 m, what is at risk and what would you check on site?",
  "We have BDT 300,000. How would you spend it, and what are the trade-offs?",
];

export default function Advisor() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [search, setSearch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const next: Turn[] = [...turns, { role: "user", content: q }];
    setTurns(next);
    setText("");
    setBusy(true);
    setError("");
    try {
      const res = await apiJson<Reply>("/api/advisor/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: next.map((t) => ({ role: t.role, content: t.content })), search }),
      });
      setTurns([...next, { role: "assistant", content: res.answer, warning: res.warning, tools: res.tool_calls, sources: res.web_sources, search: res.web_search }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-full min-h-0 max-w-3xl flex-col p-4 text-sm">
      <div className="mb-3">
        <p className="text-xs uppercase tracking-wide text-slate-500">Planning advisor</p>
        <p className="mt-1 text-xs text-amber-300">
          AI draft advice, not a decision. It reads the city's own data through read-only tools; every tool it used is listed under its answer so you can check the numbers.
        </p>
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-auto pr-1">
        {turns.length === 0 ? (
          <div className="flex flex-wrap gap-2">
            {STARTERS.map((s) => (
              <button key={s} className="rounded-full border border-slate-700 px-3 py-1.5 text-left text-xs text-slate-300 hover:border-sky-500" onClick={() => void send(s)}>
                {s}
              </button>
            ))}
          </div>
        ) : null}
        {turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="ml-auto max-w-[85%] rounded-lg bg-sky-900/50 px-3 py-2 text-slate-100">
              {t.content}
            </div>
          ) : (
            <div key={i} className="max-w-[95%] space-y-2 rounded-lg border border-slate-800 px-3 py-2.5">
              <p className="whitespace-pre-wrap text-slate-100">{t.content}</p>
              <p className="text-[11px] text-amber-300">{t.warning}</p>
              {t.search.requested && !t.search.used ? <p className="text-[11px] text-slate-500">Web search was on but returned nothing usable.</p> : null}
              {t.sources.length ? (
                <div className="text-[11px]">
                  <p className="font-semibold text-slate-300">Web sources (general background, not city data)</p>
                  <ul className="list-disc pl-4 text-slate-400">
                    {t.sources.map((s) => (
                      <li key={s.url}>
                        <a className="text-sky-300 underline" href={s.url} target="_blank" rel="noreferrer noopener">
                          {s.title}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {t.tools.length ? (
                <details className="text-[11px] text-slate-400">
                  <summary className="cursor-pointer text-slate-300">Data used ({t.tools.length} tool call{t.tools.length === 1 ? "" : "s"})</summary>
                  {t.tools.map((c, k) => (
                    <div key={k} className="mt-1.5">
                      <p className="font-mono text-sky-200">
                        {c.tool}({Object.keys(c.args).length ? JSON.stringify(c.args) : ""})
                      </p>
                      <pre className="max-h-48 overflow-auto rounded bg-slate-950 p-2 leading-snug">{JSON.stringify(c.result, null, 1)}</pre>
                    </div>
                  ))}
                </details>
              ) : null}
            </div>
          ),
        )}
        {busy ? <p className="text-xs text-slate-400">Reading the city data…</p> : null}
        {error ? <p className="rounded border border-amber-500/40 p-2 text-xs text-amber-200">{error}</p> : null}
        <div ref={end} />
      </div>
      <form
        className="mt-3 space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send(text);
        }}
      >
        <div className="flex gap-2">
          <textarea
            className="min-h-[2.5rem] flex-1 resize-none rounded bg-slate-900 p-2"
            rows={2}
            maxLength={2000}
            placeholder="Ask in English or Bangla…"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(text);
              }
            }}
          />
          <button className="rounded bg-sky-700 px-4 text-white hover:bg-sky-600 disabled:opacity-50" disabled={busy || !text.trim()}>
            Ask
          </button>
        </div>
        <div className="flex items-center justify-between text-[11px] text-slate-400">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={search} onChange={(e) => setSearch(e.target.checked)} />
            Add web background (Google search; shown separately, may be wrong)
          </label>
          {turns.length ? (
            <button type="button" className="text-slate-500 hover:text-slate-200" onClick={() => { setTurns([]); setError(""); }}>
              New conversation
            </button>
          ) : null}
        </div>
      </form>
    </div>
  );
}
