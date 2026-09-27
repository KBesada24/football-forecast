import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_SLOTS, eligible, emptyDraft, fingerprint, parseDraft, parseSaved } from "./lineup";

describe("browser roster data", () => {
  test("starts with the complete ESPN slot configuration", () => {
    assert.deepEqual(emptyDraft().slots, DEFAULT_SLOTS);
    assert.equal(DEFAULT_SLOTS.length, 9);
    assert.equal(eligible("RB", "FLEX"), true);
    assert.equal(eligible("QB", "FLEX"), false);
    assert.equal(eligible("DST", "K"), false);
  });
  test("round-trips members and valid weekly preferences", () => {
    const roster = JSON.stringify({ version: 1, members: [{ id: "p", name: "Player", position: "WR" }], slots: DEFAULT_SLOTS });
    const parsed = parseDraft(roster, JSON.stringify({ excluded: [], locks: { 3: "p" } }));
    assert.deepEqual(parsed.locks, { 3: "p" });
    assert.deepEqual(parseDraft(roster, null).locks, {});
    assert.deepEqual(parseDraft(roster, JSON.stringify({ excluded: ["p"], locks: { 3: "p" } })).locks, {});
  });
  test("rejects corrupt or oversized roster data", () => {
    assert.throws(() => parseDraft("{", null));
    assert.throws(() => parseDraft(JSON.stringify({ version: 2 }), null));
    assert.throws(() => parseDraft(JSON.stringify({ version: 1, members: [], slots: ["SUPERFLEX"] }), null));
  });
  test("does not render malformed saved recommendations", () => {
    assert.equal(parseSaved(null), null);
    assert.equal(parseSaved('{"fingerprint":"test","result":{"total":99}}'), null);
  });
  test("rejects saved players missing roster status, reason, or weighted average", () => {
    const player = {
      id: "p", name: "Player", position: "WR", projection: 12.5, team: "BUF",
      matchup: { opponent: "BAL", kickoff: "2026-09-27T17:00:00Z", home: true },
      roster_week: 3, roster_status: "ACT", availability: "available", unavailable_reason: null,
      model_kind: "baseline",
      features: {
        average5: 11, weighted5: 12, sample: 5, last5: [],
        workload: { targets: 6, carries: 0, attempts: 0 },
        head_to_head: { sample: 0, average: null },
        defense: { sample: 4, relative: 1, missing_games: 0, average: 12, league_average: 11 },
      },
    };
    const saved = (p: object) => JSON.stringify({
      fingerprint: "f",
      result: {
        season: 2026, week: 3, total: 12.5, complete: false, snapshot_id: "s",
        generated_at: "g", data_as_of: "d", first_kickoff: "k", notice: "n",
        starters: [{ slot: "WR", index: 0, locked: false, player: p }], bench: [], missing_slots: [],
      },
    });
    assert.notEqual(parseSaved(saved(player)), null);
    const without = (key: string) => Object.fromEntries(Object.entries(player).filter(([k]) => k !== key));
    const noWeighted = { ...player, features: { ...player.features, weighted5: undefined } };
    for (const bad of [without("roster_status"), without("unavailable_reason"), noWeighted]) {
      assert.equal(parseSaved(saved(bad)), null);
    }
  });
  test("changes recommendation fingerprint on roster or rule changes", () => {
    const a = emptyDraft();
    assert.notEqual(fingerprint(a), fingerprint({ ...a, slots: ["QB"] }));
    assert.notEqual(fingerprint(a), fingerprint({ ...a, excluded: ["p"] }));
  });
});
