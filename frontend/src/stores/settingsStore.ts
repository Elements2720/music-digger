import { create } from "zustand";
import { persist } from "zustand/middleware";

export type HarmonicMode = "strict" | "energy_boost";
export type TasteMode = "local" | "liked" | "both";
export type AccentTheme = "crimson" | "violet" | "amber" | "teal";
export type RowDensity = "compact" | "cozy" | "roomy";
export type M3u8PathMode = "file-url" | "relative";
export type PostDownload = "nothing" | "play" | "crate";

export interface TasteProfile {
  id: string;
  name: string;
  likedWeight: number;
  localWeight: number;
  defaultMode: TasteMode;
  defaultLimit: 20 | 30 | 50;
  bpmMin: number | null;
  bpmMax: number | null;
  genre: string | null;
}

export type MaxPerArtist = 0 | 1 | 2 | 3;

/** Upper bound of the per-artist cap offered in Settings (0 means unlimited). */
const MAX_PER_ARTIST: MaxPerArtist = 3;

export interface SettingsState {
  profiles: TasteProfile[];
  activeProfileId: string;

  maxPerArtist: MaxPerArtist;
  hideHeard: boolean;
  excludeLocal: boolean;

  defaultBpmTolerance: number;
  defaultHarmonic: boolean;
  harmonicMode: HarmonicMode;

  autoSkipIntro: boolean;
  introJumpPercent: number;
  autoMarkHeard: boolean;
  heardThresholdSec: number;
  autoplayNext: boolean;
  seekStepSec: number;
  keyboardShortcutsEnabled: boolean;

  accentTheme: AccentTheme;
  ambientGlow: boolean;
  rowDensity: RowDensity;
  defaultCrateOpen: boolean;

  m3u8PathMode: M3u8PathMode;
  m3u8PathPrefix: string;
  m3u8IncludeMetadata: boolean;
  postDownloadAction: PostDownload;

  update: (patch: Partial<SettingsState>) => void;
  addProfile: (name: string) => string;
  updateProfile: (id: string, patch: Partial<Omit<TasteProfile, "id">>) => void;
  deleteProfile: (id: string) => void;
  setActiveProfile: (id: string) => void;
  resetToDefaults: () => void;
  exportJson: () => string;
  importJson: (raw: string) => void;
}

export const PROFILE_LIMITS = [20, 30, 50] as const;

function profile(
  id: string,
  name: string,
  patch: Partial<TasteProfile> = {},
): TasteProfile {
  return {
    id,
    name,
    likedWeight: 2,
    localWeight: 1,
    defaultMode: "both",
    defaultLimit: 20,
    bpmMin: null,
    bpmMax: null,
    genre: null,
    ...patch,
  };
}

export const DEFAULT_PROFILES: TasteProfile[] = [
  profile("all-around", "All-Around"),
  profile("peak-time-techno", "Peak-Time Techno", {
    genre: "Techno",
    bpmMin: 132,
    bpmMax: 145,
    defaultLimit: 30,
  }),
  profile("warm-up-deep", "Warm-Up Deep", {
    genre: "Deep House",
    bpmMin: 118,
    bpmMax: 126,
    defaultMode: "local",
  }),
];

const DEFAULTS = {
  profiles: DEFAULT_PROFILES,
  activeProfileId: "all-around",
  maxPerArtist: 2 as const,
  hideHeard: false,
  excludeLocal: false,
  defaultBpmTolerance: 6,
  defaultHarmonic: true,
  harmonicMode: "strict" as const,
  autoSkipIntro: false,
  introJumpPercent: 8,
  autoMarkHeard: false,
  heardThresholdSec: 45,
  autoplayNext: true,
  seekStepSec: 5,
  keyboardShortcutsEnabled: true,
  accentTheme: "crimson" as const,
  ambientGlow: true,
  rowDensity: "cozy" as const,
  defaultCrateOpen: false,
  m3u8PathMode: "file-url" as const,
  m3u8PathPrefix: "/music",
  m3u8IncludeMetadata: true,
  postDownloadAction: "nothing" as const,
};

/** Keys that may be imported — anything else in a pasted JSON is ignored. */
const NUMERIC_KEYS = [
  "defaultBpmTolerance",
  "introJumpPercent",
  "heardThresholdSec",
  "seekStepSec",
] as const;
const BOOLEAN_KEYS = [
  "hideHeard",
  "excludeLocal",
  "defaultHarmonic",
  "autoSkipIntro",
  "autoMarkHeard",
  "autoplayNext",
  "keyboardShortcutsEnabled",
  "ambientGlow",
  "defaultCrateOpen",
  "m3u8IncludeMetadata",
] as const;
const ENUM_KEYS: Record<string, readonly string[]> = {
  accentTheme: ["crimson", "violet", "amber", "teal"],
  rowDensity: ["compact", "cozy", "roomy"],
  harmonicMode: ["strict", "energy_boost"],
  m3u8PathMode: ["file-url", "relative"],
  postDownloadAction: ["nothing", "play", "crate"],
};

function sanitizeProfile(value: unknown): TasteProfile | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  if (typeof raw.id !== "string" || typeof raw.name !== "string") return null;
  const num = (v: unknown, fallback: number) =>
    typeof v === "number" && Number.isFinite(v) ? v : fallback;
  const opt = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  const mode = raw.defaultMode;
  const limit = raw.defaultLimit;
  return {
    id: raw.id,
    name: raw.name.slice(0, 40),
    likedWeight: Math.min(4, Math.max(0, num(raw.likedWeight, 2))),
    localWeight: Math.min(4, Math.max(0, num(raw.localWeight, 1))),
    defaultMode: mode === "local" || mode === "liked" ? mode : "both",
    defaultLimit: limit === 30 || limit === 50 ? limit : 20,
    bpmMin: opt(raw.bpmMin),
    bpmMax: opt(raw.bpmMax),
    genre: typeof raw.genre === "string" && raw.genre.trim() ? raw.genre.trim() : null,
  };
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      ...DEFAULTS,

      update: (patch) => set(patch),

      addProfile: (name) => {
        const id = `custom-${Date.now().toString(36)}`;
        const created = profile(id, name.trim().slice(0, 40) || "Untitled profile");
        set((state) => ({ profiles: [...state.profiles, created] }));
        return id;
      },

      updateProfile: (id, patch) =>
        set((state) => ({
          profiles: state.profiles.map((p) => (p.id === id ? { ...p, ...patch } : p)),
        })),

      deleteProfile: (id) =>
        set((state) => {
          if (state.profiles.length <= 1) return state;
          const profiles = state.profiles.filter((p) => p.id !== id);
          const activeProfileId =
            state.activeProfileId === id ? profiles[0].id : state.activeProfileId;
          return { profiles, activeProfileId };
        }),

      setActiveProfile: (id) =>
        set((state) =>
          state.profiles.some((p) => p.id === id) ? { activeProfileId: id } : state,
        ),

      resetToDefaults: () =>
        set({
          ...DEFAULTS,
          profiles: DEFAULT_PROFILES.map((p) => ({ ...p })),
        }),

      exportJson: () => {
        const s = get();
        const settings = {
          profiles: s.profiles,
          activeProfileId: s.activeProfileId,
          maxPerArtist: s.maxPerArtist,
          hideHeard: s.hideHeard,
          excludeLocal: s.excludeLocal,
          defaultBpmTolerance: s.defaultBpmTolerance,
          defaultHarmonic: s.defaultHarmonic,
          harmonicMode: s.harmonicMode,
          autoSkipIntro: s.autoSkipIntro,
          introJumpPercent: s.introJumpPercent,
          autoMarkHeard: s.autoMarkHeard,
          heardThresholdSec: s.heardThresholdSec,
          autoplayNext: s.autoplayNext,
          seekStepSec: s.seekStepSec,
          keyboardShortcutsEnabled: s.keyboardShortcutsEnabled,
          accentTheme: s.accentTheme,
          ambientGlow: s.ambientGlow,
          rowDensity: s.rowDensity,
          defaultCrateOpen: s.defaultCrateOpen,
          m3u8PathMode: s.m3u8PathMode,
          m3u8PathPrefix: s.m3u8PathPrefix,
          m3u8IncludeMetadata: s.m3u8IncludeMetadata,
          postDownloadAction: s.postDownloadAction,
        };
        return JSON.stringify({ app: "digdeeper", version: 1, settings }, null, 2);
      },

      importJson: (raw) => {
        let parsed: unknown;
        try {
          parsed = JSON.parse(raw);
        } catch {
          throw new Error("That file is not valid JSON.");
        }
        const root = parsed as Record<string, unknown> | null;
        const incoming =
          root && typeof root === "object" && "settings" in root
            ? (root.settings as Record<string, unknown>)
            : root;
        if (!incoming || typeof incoming !== "object") {
          throw new Error("No settings object found in that file.");
        }
        const next: Partial<SettingsState> = {};
        for (const key of NUMERIC_KEYS) {
          const v = incoming[key];
          if (typeof v === "number" && Number.isFinite(v)) {
            (next as Record<string, unknown>)[key] = v;
          }
        }
        for (const key of BOOLEAN_KEYS) {
          const v = incoming[key];
          if (typeof v === "boolean") (next as Record<string, unknown>)[key] = v;
        }
        for (const [key, allowed] of Object.entries(ENUM_KEYS)) {
          const v = incoming[key];
          if (typeof v === "string" && allowed.includes(v)) {
            (next as Record<string, unknown>)[key] = v;
          }
        }
        const maxPerArtist = incoming.maxPerArtist;
        if (
          typeof maxPerArtist === "number" &&
          Number.isInteger(maxPerArtist) &&
          maxPerArtist >= 0 &&
          maxPerArtist <= MAX_PER_ARTIST
        ) {
          next.maxPerArtist = maxPerArtist as SettingsState["maxPerArtist"];
        }
        if (typeof incoming.m3u8PathPrefix === "string") {
          next.m3u8PathPrefix = incoming.m3u8PathPrefix.slice(0, 80);
        }
        if (Array.isArray(incoming.profiles)) {
          const profiles = incoming.profiles
            .map(sanitizeProfile)
            .filter((p): p is TasteProfile => p !== null);
          if (profiles.length) {
            next.profiles = profiles;
            const active = incoming.activeProfileId;
            next.activeProfileId =
              typeof active === "string" && profiles.some((p) => p.id === active)
                ? active
                : profiles[0].id;
          }
        }
        if (Object.keys(next).length === 0) {
          throw new Error("No recognised DigDeeper settings in that file.");
        }
        set(next);
      },
    }),
    {
      name: "digdeeper.settings.v1",
      version: 1,
      partialize: (state) => {
        const {
          update,
          addProfile,
          updateProfile,
          deleteProfile,
          setActiveProfile,
          resetToDefaults,
          exportJson,
          importJson,
          ...rest
        } = state;
        void update;
        void addProfile;
        void updateProfile;
        void deleteProfile;
        void setActiveProfile;
        void resetToDefaults;
        void exportJson;
        void importJson;
        return rest;
      },
    },
  ),
);

/** The profile that currently drives For You and Dig. */
export function useActiveProfile(): TasteProfile {
  return useSettingsStore(
    (s) => s.profiles.find((p) => p.id === s.activeProfileId) ?? s.profiles[0],
  );
}
