import { useEffect, useMemo, useState } from "react";
import { Play, Square } from "lucide-react";
import { ErrorState, PanelHead } from "../components/ui";
import { useJobsStore } from "../stores/jobsStore";
import type { JobSnapshot } from "../types/apiTypes";

/** Param forms mirror job_manager.py validators exactly. */
interface FieldSpec {
  key: string;
  label: string;
  type: "number" | "text" | "checkbox" | "select";
  default_: string | number | boolean;
  options?: string[];
  hint?: string;
  placeholder?: string;
  required?: boolean;
  min?: number;
  max?: number;
}

interface JobSpec {
  kind: string;
  label: string;
  desc: string;
  fields: FieldSpec[];
}

const JOBS: JobSpec[] = [
  {
    kind: "index",
    label: "index — embed pending previews",
    desc: "Decode previews, extract BPM/key, embed with CLAP into LanceDB.",
    fields: [
      { key: "limit", label: "LIMIT (0 = ALL)", type: "number", default_: 0, min: 0 },
      {
        key: "batch_size",
        label: "GPU BATCH SIZE (MAX 48)",
        type: "number",
        default_: 48,
        min: 1,
        max: 48,
      },
      {
        key: "turbo",
        label: "TURBO MODE — 10 WORKERS · BATCH 48 · 24 DOWNLOADS",
        type: "checkbox",
        default_: false,
      },
      {
        key: "reindex",
        label: "REINDEX ALREADY-EMBEDDED TRACKS",
        type: "checkbox",
        default_: false,
      },
      {
        key: "retry_failed",
        label: "RETRY PREVIOUSLY FAILED TRACKS",
        type: "checkbox",
        default_: false,
      },
    ],
  },
  {
    kind: "import-local",
    label: "import-local — import a music folder",
    desc: "Import full local audio files from a folder.",
    fields: [
      {
        key: "folder_path",
        label: "FOLDER PATH",
        type: "text",
        default_: "",
        placeholder: "D:\\Music\\Techno or /home/user/music",
        required: true,
      },
      { key: "recursive", label: "INCLUDE SUBFOLDERS", type: "checkbox", default_: true },
      { key: "seed_artists", label: "SEED ARTISTS FOR DISCOVERY", type: "checkbox", default_: true },
      {
        key: "batch_size",
        label: "GPU BATCH SIZE (MAX 48)",
        type: "number",
        default_: 16,
        min: 1,
        max: 48,
      },
      { key: "reindex", label: "REINDEX EXISTING", type: "checkbox", default_: false },
    ],
  },
  {
    kind: "seed-crawl",
    label: "seed-crawl — crawl genre seeds",
    desc: "Crawl genre seeds from public charts into SQLite.",
    fields: [
      { key: "electronic_limit", label: "ELECTRONIC SEEDS", type: "number", default_: 1000, min: 0 },
      { key: "general_limit", label: "GENERAL SEEDS", type: "number", default_: 300, min: 0 },
      {
        key: "max_depth",
        label: "DEEZER RELATED-ARTIST DEPTH",
        type: "number",
        default_: 2,
        min: 0,
        max: 5,
      },
      {
        key: "use_local_seeds",
        label: "USE MY LOCAL LIBRARY ARTISTS AS ROOTS",
        type: "checkbox",
        default_: false,
      },
      {
        key: "use_liked_seeds",
        label: "USE MY LIKED ARTISTS AS PRIORITY ROOTS",
        type: "checkbox",
        default_: false,
      },
    ],
  },
  {
    kind: "seed-llm",
    label: "seed-llm — ask the local LLM for seeds",
    desc: "Ask the local LLM for artist seeds in a genre.",
    fields: [
      {
        key: "genre",
        label: "GENRE FOCUS (COMMA-SEPARATED)",
        type: "text",
        default_: "Melodic Techno & Afro House",
      },
      { key: "count", label: "ARTISTS TO REQUEST", type: "number", default_: 100, min: 1, max: 1000 },
    ],
  },
  {
    kind: "seed-itunes",
    label: "seed-itunes — expand via iTunes charts",
    desc: "Expand seeds via iTunes charts, rate limited to 18 req/min.",
    fields: [
      {
        key: "terms",
        label: "KEYWORDS / LABELS (BLANK = BUILT-IN TECHNO LIST)",
        type: "text",
        default_: "",
        placeholder: "hypnotic techno, Drumcode, PoleGroup…",
      },
      {
        key: "tracks_per_term",
        label: "TRACKS PER TERM (MAX 200)",
        type: "number",
        default_: 200,
        min: 1,
        max: 200,
      },
      {
        key: "min_year",
        label: "MINIMUM RELEASE YEAR (E.G. 2018)",
        type: "number",
        default_: "",
        min: 1900,
        max: 2100,
      },
      {
        key: "electronic_only",
        label: "ELECTRONIC ONLY (FILTER POP/ROCK/JAZZ)",
        type: "checkbox",
        default_: true,
      },
      { key: "expand_compilations", label: "EXPAND VA COMPILATIONS", type: "checkbox", default_: true },
      {
        key: "save_tracks",
        label: "SAVE TRACKS IMMEDIATELY (READY FOR INDEX)",
        type: "checkbox",
        default_: true,
      },
    ],
  },
  {
    kind: "fetch-metadata",
    label: "fetch-metadata — pull Deezer/iTunes metadata",
    desc: "Pull Deezer/iTunes metadata for pending seeds (rate limited).",
    fields: [
      { key: "artists_limit", label: "ARTISTS THIS RUN", type: "number", default_: 50, min: 1 },
      {
        key: "tracks_per_artist",
        label: "TRACKS PER ARTIST (MAX 200)",
        type: "number",
        default_: 200,
        min: 1,
        max: 200,
      },
      { key: "min_year", label: "MINIMUM RELEASE YEAR", type: "number", default_: "", min: 1900, max: 2100 },
      { key: "electronic_only", label: "ELECTRONIC ONLY", type: "checkbox", default_: false },
      { key: "retry_failed", label: "RETRY SEEDS MARKED FAILED", type: "checkbox", default_: false },
    ],
  },
  {
    kind: "fetch-artist",
    label: "fetch-artist — fetch one artist",
    desc: "Fetch a single artist's catalog into the index.",
    fields: [
      {
        key: "artist",
        label: "ARTIST NAME",
        type: "text",
        default_: "",
        placeholder: "e.g. Enrico Sangiuliano or Adam Beyer",
        required: true,
      },
      {
        key: "tracks_per_artist",
        label: "TRACKS TO FETCH (MAX 200)",
        type: "number",
        default_: 50,
        min: 1,
        max: 200,
      },
      { key: "min_year", label: "MINIMUM RELEASE YEAR", type: "number", default_: "", min: 1900, max: 2100 },
      { key: "electronic_only", label: "ELECTRONIC ONLY", type: "checkbox", default_: false },
      {
        key: "auto_index",
        label: "AUTO-INDEX EMBEDDINGS IMMEDIATELY",
        type: "checkbox",
        default_: true,
      },
      {
        key: "discover_related",
        label: "DISCOVER RELATED ARTISTS (DEEZER GRAPH)",
        type: "checkbox",
        default_: false,
      },
      { key: "related_limit", label: "RELATED ARTISTS LIMIT", type: "number", default_: 10, min: 1, max: 50 },
    ],
  },
  {
    kind: "analyze-set",
    label: "analyze-set — dissect a DJ set",
    desc: "Download a full DJ set, segment it and identify passages.",
    fields: [
      {
        key: "source",
        label: "SET URL OR LOCAL AUDIO FILE",
        type: "text",
        default_: "",
        placeholder: "https://youtube.com/watch?v=… or D:\\sets\\set.mp3",
        required: true,
      },
      { key: "shazam", label: "SHAZAM UNIDENTIFIED PASSAGES", type: "checkbox", default_: true },
      { key: "comments", label: "PARSE TRACKLIST FROM COMMENTS", type: "checkbox", default_: true },
      { key: "keep_audio", label: "KEEP DOWNLOADED AUDIO", type: "checkbox", default_: false },
      {
        key: "cookies_file",
        label: "COOKIES.TXT (OPTIONAL)",
        type: "text",
        default_: "",
        placeholder: "C:\\path\\cookies.txt",
      },
      {
        key: "cookies_from_browser",
        label: "COOKIES FROM BROWSER (OPTIONAL)",
        type: "text",
        default_: "",
        placeholder: "firefox, edge, chrome…",
      },
    ],
  },
  {
    kind: "download-tracks",
    label: "download-tracks — fetch previews for track ids",
    desc: "Download 30s previews for a list of track IDs.",
    fields: [
      {
        key: "track_ids",
        label: "TRACK IDS (COMMA-SEPARATED)",
        type: "text",
        default_: "",
        required: true,
      },
      { key: "skip_existing", label: "SKIP TRACKS ALREADY DOWNLOADED", type: "checkbox", default_: true },
    ],
  },
];

function memoryLabel(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${(value / 1024).toFixed(1)} GB free`;
}

function formatValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function lastResultText(job: JobSnapshot | null): string | null {
  if (!job) return null;
  if (job.status === "cancelled") return "Job cancelled.";
  if (job.status === "error") return job.error ?? "Job failed.";
  if (!job.result || Object.keys(job.result).length === 0) return null;
  return null;
}

export function PipelineView() {
  const job = useJobsStore((s) => s.job);
  const active = useJobsStore((s) => s.active);
  const speed = useJobsStore((s) => s.speed);
  const memory = useJobsStore((s) => s.memory);
  const logLines = useJobsStore((s) => s.logLines);
  const jobError = useJobsStore((s) => s.error);
  const start = useJobsStore((s) => s.start);
  const cancel = useJobsStore((s) => s.cancel);
  const refresh = useJobsStore((s) => s.refresh);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState("index");
  const [values, setValues] = useState<Record<string, string | number | boolean>>({});
  const [starting, setStarting] = useState(false);

  const spec = JOBS.find((j) => j.kind === kind) ?? JOBS[0];

  useEffect(() => {
    refresh().catch((err: unknown) => err instanceof Error && setError(err.message));
  }, [refresh]);

  useEffect(() => {
    setValues(Object.fromEntries(spec.fields.map((f) => [f.key, f.default_])));
  }, [spec]);

  const missingRequired = spec.fields.some(
    (f) => f.required && !String(values[f.key] ?? "").trim(),
  );

  const submit = async () => {
    setError(null);
    setStarting(true);
    const params: Record<string, unknown> = {};
    for (const f of spec.fields) {
      const v = values[f.key];
      if (f.type === "number") {
        if (String(v ?? "").trim() === "") continue;
        const n = Number(v);
        if (Number.isFinite(n)) params[f.key] = n;
      } else if (f.type === "checkbox") {
        params[f.key] = Boolean(v);
      } else {
        const s = String(v ?? "").trim();
        if (s) {
          params[f.key] =
            f.key === "track_ids" || f.key === "terms"
              ? s.split(",").map((x) => x.trim()).filter(Boolean)
              : s;
        }
      }
    }
    try {
      await start(spec.kind, params);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start job");
    } finally {
      setStarting(false);
    }
  };

  const resultEntries = useMemo(
    () => (job?.result ? Object.entries(job.result) : []),
    [job],
  );
  const resultNote = lastResultText(job);
  const progressPct = job?.total
    ? Math.min(100, (job.processed / (job.total || 1)) * 100)
    : job
      ? 6
      : 0;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-[-0.02em] text-heading">Pipeline</h1>
        <p className="mt-1 text-sm text-ink-dim">
          All 9 jobs — same flags as the CLI. One job runs at a time, progress streams over SSE.
        </p>
      </div>

      {error || jobError ? (
        <ErrorState
          message={error ?? jobError ?? ""}
          onRetry={() => {
            setError(null);
            void refresh();
          }}
        />
      ) : null}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <section className="panel self-start" aria-label="Launch a job">
          <PanelHead
            title="LAUNCH A JOB"
            right={
              <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-ink-faint">
                same flags as the CLI
              </span>
            }
          />
          <div className="flex flex-col gap-3 p-3.5">
            <label className="flex flex-col gap-1 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">
              JOB
              <select
                className="input !min-h-0 py-2 text-xs"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                aria-label="Job kind"
              >
                {JOBS.map((j) => (
                  <option key={j.kind} value={j.kind}>
                    {j.label}
                  </option>
                ))}
              </select>
            </label>
            <p className="text-[11px] leading-relaxed text-ink-faint">{spec.desc}</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {spec.fields.map((f) => (
                <label
                  key={f.key}
                  className={`flex min-w-0 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-dim ${
                    f.type === "checkbox"
                      ? "flex-row items-center gap-2 sm:col-span-2"
                      : "flex-col gap-1"
                  }`}
                >
                  {f.type === "checkbox" ? (
                    <>
                      <input
                        type="checkbox"
                        checked={Boolean(values[f.key])}
                        onChange={(e) =>
                          setValues((v) => ({ ...v, [f.key]: e.target.checked }))
                        }
                        className="h-4 w-4 shrink-0 accent-accent"
                      />
                      <span className="break-words leading-tight">{f.label}</span>
                    </>
                  ) : (
                    <>
                      <span className="break-words leading-tight">
                        {f.label}
                        {f.required ? " *" : ""}
                      </span>
                      <input
                        type={f.type === "number" ? "number" : "text"}
                        className="input !min-h-0 py-2 text-xs"
                        placeholder={f.placeholder}
                        min={f.min}
                        max={f.max}
                        value={String(values[f.key] ?? "")}
                        onChange={(e) =>
                          setValues((v) => ({ ...v, [f.key]: e.target.value }))
                        }
                      />
                    </>
                  )}
                </label>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="btn btn-primary !min-h-0 py-2 font-mono text-[10px]"
                onClick={() => void submit()}
                disabled={active || starting || missingRequired}
              >
                <Play size={13} /> {starting ? "STARTING…" : "START JOB"}
              </button>
              {missingRequired ? (
                <span className="font-mono text-[9px] uppercase text-ink-faint">
                  fill the required field first
                </span>
              ) : null}
              {active && job ? (
                <span className="font-mono text-[9px] uppercase text-ink-faint">
                  {job.kind} is running — cancel it to launch another
                </span>
              ) : null}
            </div>
          </div>
        </section>

        <section className="panel self-start" aria-label="Live progress">
          <div className="panel-head">
            <span className="flex min-w-0 items-center gap-2">
              <span className="eyebrow">LIVE PROGRESS</span>
              {job ? (
                <span className="pill font-num uppercase text-accent" data-testid="job-kind">
                  {job.kind}
                </span>
              ) : null}
              {job ? (
                <span
                  className={`pill font-mono text-[9px] uppercase ${
                    active ? "pill-active" : "text-ink-faint"
                  }`}
                >
                  {job.status}
                </span>
              ) : null}
            </span>
            <button
              type="button"
              className="btn btn-ghost !min-h-7 px-2.5 py-1 font-mono text-[9px]"
              onClick={() => void cancel()}
              disabled={!active}
            >
              <Square size={10} /> CANCEL
            </button>
          </div>
          <div className="p-3.5">
            <div className="h-1.5 w-full overflow-hidden rounded bg-fill">
              <div
                className="h-full rounded bg-accent transition-all"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-3">
              <div>
                <p className="eyebrow !text-[8px]">STAGE</p>
                <p className="mt-1 break-words text-xs text-heading" data-testid="job-stage">
                  {job?.stage || "idle"}
                </p>
              </div>
              <div>
                <p className="eyebrow !text-[8px]">DONE / TOTAL</p>
                <p className="font-num mt-1 text-xs text-heading" data-testid="job-progress">
                  {job ? job.processed : 0}
                  {job?.total ? ` / ${job.total}` : ""}
                </p>
              </div>
              <div>
                <p className="eyebrow !text-[8px]">FAILED</p>
                <p className="font-num mt-1 text-xs text-heading" data-testid="job-failed">
                  {job?.failed ?? 0}
                </p>
              </div>
              <div>
                <p className="eyebrow !text-[8px]">SPEED</p>
                <p className="font-num mt-1 text-xs text-heading" data-testid="job-speed">
                  {speed != null ? `${speed.toFixed(2)} tracks/s` : "—"}
                </p>
              </div>
              <div>
                <p className="eyebrow !text-[8px]">VRAM FREE</p>
                <p className="font-num mt-1 text-xs text-heading" data-testid="job-vram">
                  {memoryLabel(memory?.vram_free_mb)}
                </p>
              </div>
              <div>
                <p className="eyebrow !text-[8px]">RAM FREE</p>
                <p className="font-num mt-1 text-xs text-heading" data-testid="job-ram">
                  {memoryLabel(memory?.ram_free_mb)}
                </p>
              </div>
            </div>
            {job?.message ? (
              <p className="font-num mt-3 truncate text-[10px] text-ink-faint">{job.message}</p>
            ) : null}
          </div>
        </section>
      </div>

      <section className="panel" aria-label="Last result">
        <PanelHead
          title="LAST RESULT"
          right={
            <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">
              {job ? `${job.status}${job.finished_at ? " · finished" : ""}` : "no runs yet"}
            </span>
          }
        />
        <div className="min-h-[92px] p-3.5">
          {resultNote ? (
            <p className="text-sm text-ink-dim" data-testid="last-result">
              {resultNote}
            </p>
          ) : resultEntries.length === 0 ? (
            <p className="text-sm text-ink-faint" data-testid="last-result">
              No result yet — launch a job to see its summary here.
            </p>
          ) : (
            <dl
              className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4"
              data-testid="last-result"
            >
              {resultEntries.map(([key, value]) => (
                <div key={key} className="min-w-0">
                  <dt className="eyebrow !text-[8px]">{key.replace(/_/g, " ")}</dt>
                  <dd className="font-num mt-0.5 truncate text-xs text-heading">
                    {formatValue(value)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </section>

      <section className="panel">
        <PanelHead
          title="LIVE LOG"
          right={
            <span className="pill font-num">
              {active ? "STREAMING" : job ? `LAST: ${job.status.toUpperCase()}` : "IDLE"}
            </span>
          }
        />
        <pre
          className="scroll-thin max-h-64 overflow-auto p-3 font-mono text-[11px] leading-relaxed text-ink-dim"
          data-testid="job-log"
        >
          {logLines.length === 0
            ? job?.message
              ? `${job.message}\n`
              : "No job output yet.\n"
            : logLines.join("\n") + "\n"}
        </pre>
      </section>
    </div>
  );
}
