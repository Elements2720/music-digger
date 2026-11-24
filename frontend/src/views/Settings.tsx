import { useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Check,
  Download,
  Music4,
  Plus,
  RotateCcw,
  Trash2,
  Upload,
} from "lucide-react";
import {
  PROFILE_LIMITS,
  useActiveProfile,
  useSettingsStore,
} from "../stores/settingsStore";
import type {
  AccentTheme,
  HarmonicMode,
  RowDensity,
  TasteMode,
} from "../stores/settingsStore";

/* ------------------------------------------------------------------ bits */

function Section({
  index,
  title,
  blurb,
  children,
}: {
  index: string;
  title: string;
  blurb: string;
  children: ReactNode;
}) {
  return (
    <section className="grid gap-5 border-t border-line py-7 first:border-t-0 lg:grid-cols-[260px_minmax(0,1fr)] lg:gap-10">
      <header className="lg:pt-1">
        <p className="eyebrow text-accent">{index}</p>
        <h2 className="mt-2 text-xl text-heading">{title}</h2>
        <p className="mt-2 max-w-[38ch] text-[13px] leading-relaxed text-ink-dim">
          {blurb}
        </p>
      </header>
      <div className="grid gap-5">{children}</div>
    </section>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-6">
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-ink">{label}</p>
        {hint ? (
          <p className="mt-0.5 text-[12px] leading-snug text-ink-faint">{hint}</p>
        ) : null}
      </div>
      <div className="flex min-h-11 items-center justify-start sm:justify-end">
        {children}
      </div>
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative h-7 w-12 shrink-0 rounded-pill border transition-colors duration-150 ${
        checked
          ? "border-accent/60 bg-accent/90"
          : "border-line bg-white/10 hover:bg-white/15"
      }`}
    >
      <span
        className={`absolute top-1/2 h-5 w-5 -translate-y-1/2 rounded-full bg-white shadow-sm transition-all duration-150 ${
          checked ? "left-[26px]" : "left-1"
        }`}
      />
    </button>
  );
}

function Chips<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (next: T) => void;
  label: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={String(option.value)}
          type="button"
          aria-pressed={option.value === value}
          data-on={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function Slider({
  value,
  min,
  max,
  step,
  onChange,
  label,
}: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (next: number) => void;
  label: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-11 w-[168px] accent-[var(--color-accent)]"
      />
      <span className="w-10 text-right font-mono text-[12px] tabular-nums text-ink-dim">
        {value}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ view */

export function SettingsView() {
  const settings = useSettingsStore();
  const active = useActiveProfile();
  const [newName, setNewName] = useState("");
  const [confirmReset, setConfirmReset] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importOk, setImportOk] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const exportSettings = () => {
    const blob = new Blob([settings.exportJson()], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "digdeeper-settings.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setImportError(null);
    setImportOk("Settings exported.");
  };

  const importFile = async (file: File) => {
    setImportError(null);
    setImportOk(null);
    try {
      settings.importJson(await file.text());
      setImportOk(`Imported ${file.name}.`);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Import failed.");
    }
  };

  return (
    <div className="mx-auto w-full max-w-[1100px] px-4 pb-16 pt-6 sm:px-6 lg:pt-8">
      <header className="mb-2">
        <p className="eyebrow text-accent">SETTINGS</p>
        <h1 className="mt-2 text-[28px] leading-[1.1] text-heading sm:text-[34px]">
          Tune the desk.
        </h1>
        <p className="mt-3 max-w-[58ch] text-[13px] leading-relaxed text-ink-dim">
          Taste weighting, discovery filters, audition behaviour and export paths.
          Everything is stored on this machine — the catalog never leaves it.
        </p>
      </header>

      <div className="mt-6 rounded-card border border-line bg-panel/70 p-4 backdrop-blur-sm sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="h-8 w-8 rounded-console bg-accent" aria-hidden />
            <div>
              <p className="text-[13px] font-medium text-ink">
                Active profile: {active?.name ?? "None"}
              </p>
              <p className="font-mono text-[11px] tabular-nums text-ink-faint">
                LIKED {active?.likedWeight.toFixed(1) ?? "2.0"} · LOCAL{" "}
                {active?.localWeight.toFixed(1) ?? "1.0"} · {active?.defaultMode ?? "both"}{" "}
                · {active?.defaultLimit ?? 20}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-ghost" onClick={exportSettings}>
              <Download size={14} /> Export JSON
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => fileRef.current?.click()}
            >
              <Upload size={14} /> Import JSON
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void importFile(file);
                event.target.value = "";
              }}
            />
            <button
              type="button"
              className={`btn ${confirmReset ? "btn-danger" : "btn-ghost"}`}
              onClick={() => {
                if (confirmReset) {
                  settings.resetToDefaults();
                  setConfirmReset(false);
                  setImportError(null);
                  setImportOk("Settings reset to defaults.");
                } else {
                  setConfirmReset(true);
                  window.setTimeout(() => setConfirmReset(false), 4000);
                }
              }}
            >
              <RotateCcw size={14} /> {confirmReset ? "Confirm reset" : "Reset"}
            </button>
          </div>
        </div>
        {importError ? (
          <p role="alert" className="mt-3 text-[12px] text-danger">
            {importError}
          </p>
        ) : null}
        {importOk ? (
          <p className="mt-3 flex items-center gap-1.5 text-[12px] text-ok">
            <Check size={13} /> {importOk}
          </p>
        ) : null}
      </div>

      <div className="mt-4">
        <Section
          index="01 / TASTE"
          title="Taste profiles"
          blurb="A profile is a saved weighting of what you like against what you already own. Switch profiles from here or from the pill in Dig → For You."
        >
          <div className="flex flex-wrap gap-2">
            {settings.profiles.map((p) => {
              const on = p.id === settings.activeProfileId;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => settings.setActiveProfile(p.id)}
                  aria-pressed={on}
                  className={`min-h-11 rounded-pill border px-4 text-[13px] transition-colors ${
                    on
                      ? "border-accent/70 bg-accent/15 text-heading"
                      : "border-line bg-white/[0.03] text-ink-dim hover:bg-white/[0.07] hover:text-heading"
                  }`}
                >
                  {p.name}
                </button>
              );
            })}
          </div>

          <div className="rounded-card border border-line bg-panel/60 p-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <label className="grid gap-1.5">
                <span className="eyebrow">PROFILE NAME</span>
                <input
                  className="input h-10 w-full min-w-[200px] sm:w-[260px]"
                  value={active?.name ?? ""}
                  onChange={(event) =>
                    active && settings.updateProfile(active.id, { name: event.target.value })
                  }
                />
              </label>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={settings.profiles.length <= 1}
                onClick={() => active && settings.deleteProfile(active.id)}
              >
                <Trash2 size={14} /> Delete profile
              </button>
            </div>

            <div className="mt-4 grid gap-4">
              <Field
                label="Liked weight"
                hint="How hard your liked tracks pull the ranking (0–4)."
              >
                <Slider
                  label="Liked weight"
                  value={active?.likedWeight ?? 2}
                  min={0}
                  max={4}
                  step={0.5}
                  onChange={(v) => active && settings.updateProfile(active.id, { likedWeight: v })}
                />
              </Field>
              <Field
                label="Local weight"
                hint="How hard tracks you already own pull the ranking (0–4)."
              >
                <Slider
                  label="Local weight"
                  value={active?.localWeight ?? 1}
                  min={0}
                  max={4}
                  step={0.5}
                  onChange={(v) => active && settings.updateProfile(active.id, { localWeight: v })}
                />
              </Field>
              <Field label="Seed source" hint="Which tracks feed For You by default.">
                <Chips<TasteMode>
                  label="Seed source"
                  value={active?.defaultMode ?? "both"}
                  options={[
                    { value: "both", label: "Both" },
                    { value: "liked", label: "Liked" },
                    { value: "local", label: "Local" },
                  ]}
                  onChange={(v) => active && settings.updateProfile(active.id, { defaultMode: v })}
                />
              </Field>
              <Field label="Result count" hint="How many For You picks to load.">
                <Chips<20 | 30 | 50>
                  label="Result count"
                  value={(active?.defaultLimit ?? 20) as 20 | 30 | 50}
                  options={PROFILE_LIMITS.map((n) => ({
                    value: n as 20 | 30 | 50,
                    label: String(n),
                  }))}
                  onChange={(v) => active && settings.updateProfile(active.id, { defaultLimit: v })}
                />
              </Field>
              <Field label="BPM window" hint="Optional floor and ceiling applied to For You.">
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    inputMode="numeric"
                    aria-label="Minimum BPM"
                    placeholder="min"
                    className="input h-10 w-[86px] tabular-nums"
                    value={active?.bpmMin ?? ""}
                    onChange={(event) =>
                      active &&
                      settings.updateProfile(active.id, {
                        bpmMin: event.target.value === "" ? null : Number(event.target.value),
                      })
                    }
                  />
                  <span className="text-ink-faint">–</span>
                  <input
                    type="number"
                    inputMode="numeric"
                    aria-label="Maximum BPM"
                    placeholder="max"
                    className="input h-10 w-[86px] tabular-nums"
                    value={active?.bpmMax ?? ""}
                    onChange={(event) =>
                      active &&
                      settings.updateProfile(active.id, {
                        bpmMax: event.target.value === "" ? null : Number(event.target.value),
                      })
                    }
                  />
                </div>
              </Field>
              <Field label="Genre lock" hint="Leave empty to span every genre in the catalog.">
                <input
                  className="input h-10 w-full sm:w-[240px]"
                  aria-label="Genre"
                  placeholder="e.g. Melodic Techno"
                  value={active?.genre ?? ""}
                  onChange={(event) =>
                    active &&
                    settings.updateProfile(active.id, {
                      genre: event.target.value.trim() || null,
                    })
                  }
                />
              </Field>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-4">
              <input
                className="input h-10 min-w-[180px] flex-1"
                aria-label="New profile name"
                placeholder="New profile name"
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
              />
              <button
                type="button"
                className="btn btn-primary"
                disabled={!newName.trim()}
                onClick={() => {
                  const id = settings.addProfile(newName);
                  settings.setActiveProfile(id);
                  setNewName("");
                }}
              >
                <Plus size={14} /> Add profile
              </button>
            </div>
          </div>
        </Section>

        <Section
          index="02 / DISCOVERY"
          title="Anti-repetition"
          blurb="Keep a digging session from stacking the same artist or re-surfacing what you have already heard."
        >
          <Field label="Max tracks per artist" hint="0 leaves the ranking uncapped.">
            <Chips<0 | 1 | 2 | 3>
              label="Max tracks per artist"
              value={settings.maxPerArtist}
              options={[0, 1, 2, 3].map((n) => ({ value: n as 0 | 1 | 2 | 3, label: n === 0 ? "Off" : String(n) }))}
              onChange={(v) => settings.update({ maxPerArtist: v })}
            />
          </Field>
          <Field label="Hide heard tracks" hint="Drop anything already marked heard from discovery.">
            <Toggle
              label="Hide heard tracks"
              checked={settings.hideHeard}
              onChange={(v) => settings.update({ hideHeard: v })}
            />
          </Field>
          <Field label="Exclude local tracks" hint="Surface strictly new music you do not own yet.">
            <Toggle
              label="Exclude local tracks"
              checked={settings.excludeLocal}
              onChange={(v) => settings.update({ excludeLocal: v })}
            />
          </Field>
        </Section>

        <Section
          index="03 / DIGGING"
          title="Harmonic rules"
          blurb="Defaults for every new Dig search, and how far the harmonic filter reaches."
        >
          <Field label="Default BPM tolerance" hint="± BPM applied when a search opens.">
            <Slider
              label="Default BPM tolerance"
              value={settings.defaultBpmTolerance}
              min={2}
              max={10}
              step={1}
              onChange={(v) => settings.update({ defaultBpmTolerance: v })}
            />
          </Field>
          <Field label="Harmonic filter on by default">
            <Toggle
              label="Harmonic filter on by default"
              checked={settings.defaultHarmonic}
              onChange={(v) => settings.update({ defaultHarmonic: v })}
            />
          </Field>
          <Field
            label="Harmonic reach"
            hint="Strict keeps same key, relative and ±1. Energy boost also allows one lift step."
          >
            <Chips<HarmonicMode>
              label="Harmonic reach"
              value={settings.harmonicMode}
              options={[
                { value: "strict", label: "Strict" },
                { value: "energy_boost", label: "Energy boost" },
              ]}
              onChange={(v) => settings.update({ harmonicMode: v })}
            />
          </Field>
        </Section>

        <Section
          index="04 / AUDIO"
          title="Auditioning"
          blurb="How the deck behaves the moment a track starts playing."
        >
          <Field label="Skip intro automatically" hint="Jump the opening bars on the first play.">
            <Toggle
              label="Skip intro automatically"
              checked={settings.autoSkipIntro}
              onChange={(v) => settings.update({ autoSkipIntro: v })}
            />
          </Field>
          <Field label="Intro jump" hint="How far into the track the skip lands.">
            <Slider
              label="Intro jump percent"
              value={settings.introJumpPercent}
              min={2}
              max={20}
              step={1}
              onChange={(v) => settings.update({ introJumpPercent: v })}
            />
          </Field>
          <Field label="Mark heard automatically" hint="After a listen past the threshold.">
            <Toggle
              label="Mark heard automatically"
              checked={settings.autoMarkHeard}
              onChange={(v) => settings.update({ autoMarkHeard: v })}
            />
          </Field>
          <Field label="Heard threshold" hint="Seconds of playback before a track counts as heard.">
            <Slider
              label="Heard threshold seconds"
              value={settings.heardThresholdSec}
              min={15}
              max={120}
              step={5}
              onChange={(v) => settings.update({ heardThresholdSec: v })}
            />
          </Field>
          <Field label="Autoplay next" hint="Roll into the next track in the queue when one ends.">
            <Toggle
              label="Autoplay next"
              checked={settings.autoplayNext}
              onChange={(v) => settings.update({ autoplayNext: v })}
            />
          </Field>
          <Field label="Seek step" hint="Seconds moved by the arrow keys.">
            <Slider
              label="Seek step seconds"
              value={settings.seekStepSec}
              min={2}
              max={15}
              step={1}
              onChange={(v) => settings.update({ seekStepSec: v })}
            />
          </Field>
          <Field label="Keyboard shortcuts" hint="Space to play, M to mute, arrows to seek.">
            <Toggle
              label="Keyboard shortcuts"
              checked={settings.keyboardShortcutsEnabled}
              onChange={(v) => settings.update({ keyboardShortcutsEnabled: v })}
            />
          </Field>
        </Section>

        <Section
          index="05 / APPEARANCE"
          title="Desk finish"
          blurb="Accent colour, the ambient wash behind the canvas, and how tight track rows sit."
        >
          <Field label="Accent" hint="Applies instantly across every workspace.">
            <div className="flex gap-2" role="group" aria-label="Accent colour">
              {(
                [
                  ["crimson", "#fa233b"],
                  ["violet", "#8b5cf6"],
                  ["amber", "#f5b942"],
                  ["teal", "#2fcfb0"],
                ] as [AccentTheme, string][]
              ).map(([key, hex]) => (
                <button
                  key={key}
                  type="button"
                  aria-label={key}
                  aria-pressed={settings.accentTheme === key}
                  onClick={() => settings.update({ accentTheme: key })}
                  className={`h-11 w-11 rounded-pill border-2 transition-transform ${
                    settings.accentTheme === key
                      ? "border-white"
                      : "border-white/20 hover:scale-105"
                  }`}
                  style={{ backgroundColor: hex }}
                />
              ))}
            </div>
          </Field>
          <Field label="Ambient glow" hint="The crimson wash at the top of the canvas.">
            <Toggle
              label="Ambient glow"
              checked={settings.ambientGlow}
              onChange={(v) => settings.update({ ambientGlow: v })}
            />
          </Field>
          <Field label="Row density" hint="Compact fits more tracks per screen.">
            <Chips<RowDensity>
              label="Row density"
              value={settings.rowDensity}
              options={[
                { value: "compact", label: "Compact" },
                { value: "cozy", label: "Cozy" },
                { value: "roomy", label: "Roomy" },
              ]}
              onChange={(v) => settings.update({ rowDensity: v })}
            />
          </Field>
          <Field label="Open Set Crate on load" hint="Keep the crate drawer ready while digging.">
            <Toggle
              label="Open Set Crate on load"
              checked={settings.defaultCrateOpen}
              onChange={(v) => settings.update({ defaultCrateOpen: v })}
            />
          </Field>
        </Section>

        <Section
          index="06 / EXPORT"
          title="Playlist files"
          blurb="Both Set Builder and the Set Crate drawer write .m3u8 files with these rules."
        >
          <Field label="Path style" hint="File URLs work in most players; relative paths travel with the folder.">
            <Chips<"file-url" | "relative">
              label="Path style"
              value={settings.m3u8PathMode}
              options={[
                { value: "file-url", label: "file://" },
                { value: "relative", label: "Relative" },
              ]}
              onChange={(v) => settings.update({ m3u8PathMode: v })}
            />
          </Field>
          <Field label="Path prefix" hint="Prepended when relative paths are used.">
            <input
              className="input h-10 w-full font-mono text-[12px] sm:w-[220px]"
              aria-label="Path prefix"
              value={settings.m3u8PathPrefix}
              onChange={(event) => settings.update({ m3u8PathPrefix: event.target.value })}
            />
          </Field>
          <Field label="Include metadata tags" hint="Writes #EXTINF duration and artist — title lines.">
            <Toggle
              label="Include metadata tags"
              checked={settings.m3u8IncludeMetadata}
              onChange={(v) => settings.update({ m3u8IncludeMetadata: v })}
            />
          </Field>
          <Field label="After download" hint="What to do once the file is written.">
            <Chips<"nothing" | "play" | "crate">
              label="After download"
              value={settings.postDownloadAction}
              options={[
                { value: "nothing", label: "Nothing" },
                { value: "play", label: "Play" },
                { value: "crate", label: "Open crate" },
              ]}
              onChange={(v) => settings.update({ postDownloadAction: v })}
            />
          </Field>
        </Section>
      </div>

      <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
        <p className="flex items-center gap-2 text-[12px] text-ink-faint">
          <Music4 size={14} /> Stored locally · exported as plain JSON
        </p>
        <p className="font-mono text-[11px] text-ink-faint">
          {settings.profiles.length} PROFILE{settings.profiles.length === 1 ? "" : "S"}
        </p>
      </footer>
    </div>
  );
}
