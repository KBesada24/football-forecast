export type Slot = "QB" | "RB" | "WR" | "TE" | "FLEX" | "K" | "DST";
export const SLOT_TYPES: Slot[] = ["QB", "RB", "WR", "TE", "FLEX", "K", "DST"];
export const DEFAULT_SLOTS: Slot[] = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DST"];
export const slotLabel = (slot: string) => slot === "DST" ? "D/ST" : slot;
export const eligible = (position: string, slot: Slot) =>
  slot === "FLEX" ? ["RB", "WR", "TE"].includes(position) : position === slot;
export type Member = { id: string; name: string; position: string };
export type LineupPlayer = Member & {
  team: string | null;
  projection: number | null;
  matchup: { opponent: string; home: boolean; kickoff: string } | null;
  roster_week: number;
  roster_status: string;
  unavailable_reason: string | null;
  model_kind: string;
  availability: string;
  features: {
    average5: number | null; weighted5: number | null; sample: number;
    last5: { season: number; week: number; opponent: string; points: number }[];
    workload: { targets: number; carries: number; attempts: number };
    head_to_head: { average: number | null; sample: number };
    defense: { average: number | null; league_average: number | null; sample: number;
      missing_games: number; relative: number };
  };
};
export type WeekLineups = {
  status: "ready" | "locked" | "unavailable";
  season: number; week: number; snapshot_id?: string;
  generated_at?: string; data_as_of?: string; first_kickoff?: string;
  suggested_week: { season: number; week: number } | null;
  players: LineupPlayer[]; notice?: string; evaluation_note?: string;
  model_report?: Record<string, { deployed?: string; promoted: boolean;
    holdout_challenger?: { mae: number }; holdout_baselines?: { mean5: { mae: number } } }>;
};
export type Recommendation = {
  season: number; week: number; snapshot_id: string; generated_at: string;
  data_as_of: string; first_kickoff: string; total: number; complete: boolean;
  starters: { slot: Slot; index: number; player: LineupPlayer | null; locked: boolean }[];
  bench: { player: LineupPlayer; reason: string; gap: number | null }[];
  missing_slots: Slot[]; notice: string;
};
export type Draft = { members: Member[]; slots: Slot[]; excluded: string[]; locks: Record<string, string> };
export const emptyDraft = (): Draft => ({ members: [], slots: [...DEFAULT_SLOTS], excluded: [], locks: {} });

const object = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const member = (v: unknown): v is Member => object(v) && typeof v.id === "string" && v.id.length <= 64
  && typeof v.name === "string" && v.name.length <= 160 && typeof v.position === "string"
  && v.position !== "FLEX" && SLOT_TYPES.includes(v.position as Slot);
const numeric = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const nullableNumber = (v: unknown) => v === null || numeric(v);

export function parseDraft(raw: string | null, weekRaw: string | null): Draft {
  const fallback = emptyDraft();
  if (!raw) return fallback;
  const v: unknown = JSON.parse(raw);
  if (!object(v) || v.version !== 1 || !Array.isArray(v.members) || v.members.length > 30
    || !v.members.every(member) || new Set(v.members.map(m => m.id)).size !== v.members.length
    || !Array.isArray(v.slots) || v.slots.length < 1 || v.slots.length > 12
    || !v.slots.every(s => SLOT_TYPES.includes(s))) throw new Error("Saved roster is invalid");
  const draft = { ...fallback, members: v.members, slots: v.slots as Slot[] };
  if (!weekRaw) return draft;
  const w: unknown = JSON.parse(weekRaw);
  if (!object(w) || !Array.isArray(w.excluded) || !object(w.locks)) return draft;
  draft.excluded = w.excluded.filter((id): id is string => typeof id === "string" && draft.members.some(m => m.id === id));
  const used = new Set<string>();
  for (const [i, id] of Object.entries(w.locks)) {
    const m = draft.members.find(m => m.id === id);
    if (/^\d+$/.test(i) && m && !used.has(m.id) && !draft.excluded.includes(m.id)
        && draft.slots[Number(i)] && eligible(m.position, draft.slots[Number(i)])) {
      draft.locks[i] = m.id; used.add(m.id);
    }
  }
  return draft;
}

function validPlayer(p: unknown): p is LineupPlayer {
  if (!object(p) || !member(p)) return false;
  return validPlayerDetails(p);
}

function validPlayerDetails(p: Record<string, unknown>): boolean {
  if (!object(p.features)) return false;
  const f = p.features;
  return nullableNumber(p.projection) && (p.team === null || typeof p.team === "string")
    && (p.matchup === null || (object(p.matchup) && typeof p.matchup.opponent === "string"
      && typeof p.matchup.kickoff === "string" && typeof p.matchup.home === "boolean"))
    && numeric(p.roster_week) && typeof p.availability === "string" && typeof p.model_kind === "string"
    && typeof p.roster_status === "string" && (p.unavailable_reason === null || typeof p.unavailable_reason === "string")
    && nullableNumber(f.average5) && nullableNumber(f.weighted5) && numeric(f.sample)
    && Array.isArray(f.last5) && f.last5.length <= 5 && f.last5.every(g => object(g)
      && numeric(g.season) && numeric(g.week) && numeric(g.points) && typeof g.opponent === "string")
    && object(f.workload) && [f.workload.targets, f.workload.carries, f.workload.attempts].every(numeric)
    && object(f.head_to_head) && numeric(f.head_to_head.sample) && nullableNumber(f.head_to_head.average)
    && object(f.defense) && numeric(f.defense.sample) && numeric(f.defense.relative)
    && numeric(f.defense.missing_games) && nullableNumber(f.defense.average) && nullableNumber(f.defense.league_average);
}

export function parseSaved(raw: string | null): { fingerprint: string; result: Recommendation } | null {
  if (!raw) return null;
  const v: unknown = JSON.parse(raw);
  if (!object(v) || typeof v.fingerprint !== "string" || !object(v.result)) return null;
  const r = v.result;
  if (!numeric(r.season) || !numeric(r.week) || !numeric(r.total) || typeof r.complete !== "boolean"
    || ![r.snapshot_id, r.generated_at, r.data_as_of, r.first_kickoff, r.notice].every(s => typeof s === "string")
    || !Array.isArray(r.starters) || r.starters.length > 12 || !r.starters.every(s => object(s)
      && SLOT_TYPES.includes(s.slot as Slot) && numeric(s.index) && typeof s.locked === "boolean"
      && (s.player === null || validPlayer(s.player)))
    || !Array.isArray(r.bench) || r.bench.length > 30 || !r.bench.every(b => object(b)
      && validPlayer(b.player) && typeof b.reason === "string" && nullableNumber(b.gap))
    || !Array.isArray(r.missing_slots) || !r.missing_slots.every(s => SLOT_TYPES.includes(s))) return null;
  return v as { fingerprint: string; result: Recommendation };
}

export function fingerprint(draft: Draft) {
  return JSON.stringify({ roster: draft.members.map(m => m.id), slots: draft.slots,
    excluded: [...draft.excluded].sort(), locks: draft.locks });
}
