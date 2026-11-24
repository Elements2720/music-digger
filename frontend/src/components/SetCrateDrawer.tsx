import { X } from "lucide-react";
import { useCrateStore } from "../stores/crateStore";
import { usePlayerStore } from "../stores/playerStore";
import { api } from "../api/client";
import type { PlannedSet } from "../types/apiTypes";
import { useState } from "react";
import { Artwork, EmptyState } from "./ui";
import { fmtBpm } from "../lib/format";

function EnergyCurve({ bpms }: { bpms: number[] }) {
  if (bpms.length < 2) return null;
  const min = Math.min(...bpms);
  const max = Math.max(...bpms);
  const span = max - min || 1;
  const w = 260;
  const h = 36;
  const pts = bpms.map((b, i) => {
    const x = (i / (bpms.length - 1)) * w;
    const y = h - ((b - min) / span) * (h - 6) - 3;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
      <polyline
        points={pts.join(" ")}
        fill="none"
        stroke="var(--color-accent)"
        strokeWidth="1.5"
      />
    </svg>
  );
}

export function SetCrateDrawer() {
  const { tracks, open, setOpen, remove, clear, move } = useCrateStore();
  const play = usePlayerStore((s) => s.play);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  if (!open) return null;

  const bpms = tracks.map((t) => t.bpm ?? 0).filter((b) => b > 0);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const name = `Crate ${new Date().toISOString().slice(0, 16).replace("T", " ")}`;
      const created = await api.createPlannedSet({ name, track_ids: tracks.map((t) => t.id) });
      const updated = await api.updatePlannedSet(created.id, {
        track_ids: tracks.map((t) => t.id),
      });
      void updated;
      setMessage(`Saved "${name}" — export it from Set Builder`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/60"
        onClick={() => setOpen(false)}
        aria-hidden
      />
      <aside
        role="dialog"
        aria-label="Set Crate"
        data-testid="crate-drawer"
        className="fixed inset-y-0 right-0 z-50 flex w-[300px] max-w-[88vw] flex-col border-l border-line bg-panel"
      >
        <div className="panel-head">
          <span className="eyebrow">SET CRATE — {tracks.length}</span>
          <button
            type="button"
            className="btn btn-ghost !min-h-0 p-1.5"
            onClick={() => setOpen(false)}
            aria-label="Close Set Crate"
          >
            <X size={16} />
          </button>
        </div>

        {bpms.length >= 2 ? (
          <div className="border-b border-line px-3 py-2">
            <EnergyCurve bpms={bpms} />
            <p className="eyebrow mt-1">BPM ENERGY CURVE</p>
          </div>
        ) : null}

        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          {tracks.length === 0 ? (
            <EmptyState
              title="CRATE EMPTY"
              hint="Add tracks with the + Set action in any workspace. The crate is shared across every view."
            />
          ) : (
            tracks.map((t, i) => (
              <div
                key={t.id}
                draggable
                onDragStart={(e) => e.dataTransfer.setData("text/plain", t.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const id = e.dataTransfer.getData("text/plain");
                  if (id && id !== t.id) move(id, i);
                }}
                className="flex items-center gap-2 border-b border-line px-2 py-1.5"
              >
                <span className="font-num w-5 text-right text-[10px] text-ink-faint">
                  {i + 1}
                </span>
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => play(t, tracks)}
                >
                  <span className="block truncate text-xs text-heading">{t.title}</span>
                  <span className="block truncate text-[11px] text-ink-dim">
                    {t.artist}
                  </span>
                </button>
                <Artwork track={t} size={28} />
                <span className="font-num hidden text-[10px] text-ink-dim sm:block">
                  {t.bpm == null ? "—" : `${fmtBpm(t.bpm)}`}
                </span>
                <button
                  type="button"
                  className="btn btn-ghost !min-h-0 p-1 text-ink-faint"
                  onClick={() => remove(t.id)}
                  aria-label={`Remove ${t.title} from crate`}
                >
                  <X size={12} />
                </button>
              </div>
            ))
          )}
        </div>

        <div className="border-t border-line p-3">
          {message ? (
            <p className="mb-2 font-mono text-[11px] text-accent" role="status">
              {message}
            </p>
          ) : null}
          <div className="flex gap-2">
            <button
              type="button"
              className="btn btn-primary flex-1"
              disabled={tracks.length === 0 || saving}
              onClick={() => void save()}
            >
              {saving ? "SAVING…" : "SAVE AS SET"}
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={tracks.length === 0}
              onClick={clear}
            >
              CLEAR
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}

export type { PlannedSet };
