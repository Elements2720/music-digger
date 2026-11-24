import { useEffect, useState } from "react";
import { Play, Square } from "lucide-react";
import { api } from "../api/client";
import { ErrorState, PanelHead } from "../components/ui";
import { useJobsStore } from "../stores/jobsStore";

/** Param forms mirror job_manager.py validators exactly. */
interface FieldSpec {
  key: string;
  label: string;
  type: "number" | "text" | "checkbox" | "select";
  default_: string | number | boolean;
  options?: string[];
  hint?: string;
}

const JOBS: { kind: string; label: string; desc: string; fields: FieldSpec[] }[] = [
  {
    kind: "seed-crawl",
    label: "SEED CRAWL",
    desc: "Crawl genre seeds from public charts into SQLite.",
    fields: [
      { key: "electronic_limit", label: "ELECTRONIC LIMIT", type: "number", default_: 1000 },
      { key: "general_limit", label: "GENERAL LIMIT", type: "number", default_: 300 },
    ],
  },
  {
    kind: "seed-llm",
    label: "SEED LLM",
    desc: "Ask the local LLM for artist seeds in a genre.",
    fields: [
      { key: "genre", label: "GENRE", type: "text", default_: "Melodic Techno & Afro House" },
      { key: "count", label: "COUNT", type: "number", default_: 100 },
    ],
  },
  {
    kind: "seed-itunes",
    label: "SEED ITUNES",
    desc: "Expand seeds via iTunes charts.",
    fields: [
      { key: "terms", label: "TERMS (comma separated)", type: "text", default_: "techno" },
      { key: "tracks_per_term", label: "TRACKS PER TERM", type: "number", default_: 50 },
      { key: "retry_failed", label: "RETRY FAILED", type: "checkbox", default_: false },
    ],
  },
  {
    kind: "fetch-metadata",
    label: "FETCH METADATA",
    desc: "Pull Deezer/iTunes metadata for pending seeds (rate limited).",
    fields: [
      { key: "artists_limit", label: "ARTISTS LIMIT", type: "number", default_: 50 },
      { key: "retry_failed", label: "RETRY FAILED", type: "checkbox", default_: false },
    ],
  },
  {
    kind: "download-tracks",
    label: "DOWNLOAD PREVIEWS",
    desc: "Download 30s previews for indexed tracks.",
    fields: [
      { key: "limit", label: "LIMIT", type: "number", default_: 200 },
      { key: "retry_failed", label: "RETRY FAILED", type: "checkbox", default_: false },
    ],
  },
  {
    kind: "fetch-artist",
    label: "FETCH ARTIST",
    desc: "Fetch a single artist's catalog into the index.",
    fields: [{ key: "artist", label: "ARTIST", type: "text", default_: "" }],
  },
  {
    kind: "index",
    label: "INDEX / EMBED",
    desc: "Decode previews, extract BPM/key, embed with CLAP into LanceDB.",
    fields: [
      { key: "limit", label: "LIMIT", type: "number", default_: 500 },
      { key: "batch_size", label: "BATCH SIZE", type: "number", default_: 16 },
      { key: "track_ids", label: "TRACK IDS (comma separated, optional)", type: "text", default_: "" },
      { key: "reindex", label: "REINDEX ALL", type: "checkbox", default_: false },
    ],
  },
  {
    kind: "import-local",
    label: "IMPORT LOCAL",
    desc: "Import full local audio files from a folder.",
    fields: [
      { key: "folder_path", label: "FOLDER PATH", type: "text", default_: "" },
      { key: "genre", label: "GENRE (optional)", type: "text", default_: "" },
    ],
  },
  {
    kind: "analyze-set",
    label: "ANALYZE DJ SET",
    desc: "Download a full DJ set, segment it and identify passages.",
    fields: [
      { key: "source", label: "SOURCE URL OR FILE", type: "text", default_: "" },
      { key: "keep_audio", label: "KEEP AUDIO", type: "checkbox", default_: false },
    ],
  },
];

function JobCard({
  spec,
}: {
  spec: (typeof JOBS)[number];
}) {
  const { start, active, job, cancel } = useJobsStore();
  const [values, setValues] = useState<Record<string, string | number | boolean>>(() =>
    Object.fromEntries(spec.fields.map((f) => [f.key, f.default_])),
  );
  const [error, setError] = useState<string | null>(null);
  const isThis = job?.kind === spec.kind && active;

  const submit = async () => {
    setError(null);
    const params: Record<string, unknown> = {};
    for (const f of spec.fields) {
      const v = values[f.key];
      if (f.type === "number") {
        const n = Number(v);
        if (Number.isFinite(n) && (n !== 0 || f.default_ !== 0)) params[f.key] = n;
      } else if (f.type === "checkbox") {
        params[f.key] = Boolean(v);
      } else {
        const s = String(v).trim();
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
    }
  };

  return (
    <div className="panel p-4" data-job={spec.kind}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs font-semibold uppercase tracking-[0.12em] text-heading">
          {spec.label}
        </span>
        {isThis ? (
          <span className="pill pill-active font-num">RUNNING</span>
        ) : null}
      </div>
      <p className="mt-1 text-xs text-ink-faint">{spec.desc}</p>

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {spec.fields.map((f) => (
          <label key={f.key} className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim">
            {f.label}
            {f.type === "checkbox" ? (
              <input
                type="checkbox"
                checked={Boolean(values[f.key])}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.checked }))}
                className="h-4 w-4 accent-accent"
              />
            ) : (
              <input
                type={f.type === "number" ? "number" : "text"}
                className="input"
                value={String(values[f.key] ?? "")}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
              />
            )}
          </label>
        ))}
      </div>

      {isThis && job ? (
        <div className="mt-3">
          <div className="h-1.5 w-full rounded bg-fill">
            <div
              className="h-full rounded bg-accent transition-all"
              style={{
                width: job.total ? `${Math.min(100, (job.processed / job.total) * 100)}%` : "10%",
              }}
            />
          </div>
          <p className="font-num mt-1 text-[11px] text-ink-dim" data-testid={`progress-${spec.kind}`}>
            {job.stage} {job.total ? `${job.processed}/${job.total}` : job.processed}
            {job.failed ? ` · ${job.failed} failed` : ""}
          </p>
        </div>
      ) : null}

      {error ? (
        <p className="mt-2 font-mono text-[11px] text-danger">{error}</p>
      ) : null}
      {!active && job?.kind === spec.kind && job.error ? (
        <p className="mt-2 font-mono text-[11px] text-danger">{job.error}</p>
      ) : null}

      <div className="mt-3 flex gap-2">
        <button
          type="button"
          className="btn btn-primary flex-1"
          onClick={() => void submit()}
          disabled={active}
        >
          <Play size={13} /> RUN
        </button>
        {isThis ? (
          <button type="button" className="btn btn-danger" onClick={() => void cancel()}>
            <Square size={13} /> CANCEL
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function PipelineView() {
  const job = useJobsStore((s) => s.job);
  const active = useJobsStore((s) => s.active);
  const logLines = useJobsStore((s) => s.logLines);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.currentJob().catch((err: unknown) => err instanceof Error && setError(err.message));
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-[-0.02em] text-heading">Pipeline</h1>
        <p className="mt-1 text-sm text-ink-dim">
          All 9 jobs — every stage streams live over SSE. One job runs at a time.
        </p>
      </div>

      {error ? <ErrorState message={error} /> : null}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {JOBS.map((spec) => (
          <JobCard key={spec.kind} spec={spec} />
        ))}
      </div>

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
