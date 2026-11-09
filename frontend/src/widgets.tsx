import { useRef } from "react";

/** A value with a low-high range on a 0..max track. The tick marks the central estimate. */
export function RangeBar({
  low,
  central,
  high,
  max = 100,
  color = "#34d399",
  format = (v: number) => `${v}`,
}: {
  low: number | null;
  central: number | null;
  high: number | null;
  max?: number;
  color?: string;
  format?: (v: number) => string;
}) {
  if (low == null || central == null || high == null || max <= 0) return <p className="text-[11px] text-slate-500">No range available.</p>;
  const at = (v: number) => `${Math.min(Math.max((v / max) * 100, 0), 100)}%`;
  return (
    <div>
      <div className="relative h-2.5 rounded-full bg-slate-800">
        <div
          className="absolute top-0 h-full rounded-full opacity-40"
          style={{ left: at(low), width: `calc(${at(high)} - ${at(low)})`, background: color, minWidth: 3 }}
        />
        <div className="absolute -top-0.5 h-3.5 w-1 rounded-sm bg-white" style={{ left: `calc(${at(central)} - 2px)` }} />
      </div>
      <p className="num mt-1 text-[11px] text-slate-400">
        {format(central)} <span className="text-slate-600">best estimate</span> · plausible {format(low)} to {format(high)}
      </p>
    </div>
  );
}

export function CandidateBadge({ children = "Candidate scenario · not reviewed by staff" }: { children?: string }) {
  return (
    <span className="inline-block rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10.5px] font-medium text-amber-200">
      {children}
    </span>
  );
}

/** Draggable divider for a before/after swipe. `pos` is the percentage from the left. */
export function CompareHandle({ pos, onPos, left, right }: { pos: number; onPos: (p: number) => void; left: string; right: string }) {
  const track = useRef<HTMLDivElement | null>(null);
  const move = (clientX: number) => {
    const el = track.current?.parentElement;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    onPos(Math.min(Math.max(((clientX - rect.left) / rect.width) * 100, 3), 97));
  };
  return (
    <div ref={track} className="pointer-events-none absolute inset-0 z-20">
      <span className="glass absolute left-3 top-14 px-2 py-1 text-[11px] font-medium text-slate-200">{left}</span>
      <span className="glass absolute bottom-14 right-3 px-2 py-1 text-[11px] font-medium text-slate-200 md:bottom-auto md:right-auto md:top-14" style={{ left: `calc(${pos}% + 14px)` }}>
        {right}
      </span>
      <div className="absolute inset-y-0" style={{ left: `${pos}%` }}>
        <div className="absolute inset-y-0 -ml-px w-0.5 bg-white/90 shadow-[0_0_8px_rgba(0,0,0,0.6)]" />
        <div
          role="slider"
          aria-label="Before and after divider"
          aria-valuemin={3}
          aria-valuemax={97}
          aria-valuenow={Math.round(pos)}
          tabIndex={0}
          className="pointer-events-auto absolute top-1/2 -ml-[18px] grid h-9 w-9 -translate-y-1/2 cursor-ew-resize place-items-center rounded-full border-2 border-white bg-slate-900/90 text-xs text-white shadow-lg"
          style={{ touchAction: "none" }}
          onPointerDown={(e) => e.currentTarget.setPointerCapture(e.pointerId)}
          onPointerMove={(e) => {
            if (e.currentTarget.hasPointerCapture(e.pointerId)) move(e.clientX);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") onPos(Math.max(pos - 3, 3));
            if (e.key === "ArrowRight") onPos(Math.min(pos + 3, 97));
          }}
        >
          ⇄
        </div>
      </div>
    </div>
  );
}
