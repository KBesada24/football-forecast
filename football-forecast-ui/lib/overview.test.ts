import { test } from "node:test";
import assert from "node:assert/strict";
import { overviewData } from "./overview";
import type { Dashboard, Game } from "./types";

function game(
  week: number,
  points: number,
  status: Game["completionStatus"] = "unknown",
): Game {
  return {
    season: 2026,
    week,
    fantasyPointsPpr: points,
    completionStatus: status,
  } as Game;
}
function data(games: Game[], projection: number | null = null): Dashboard {
  return {
    projection: {
      matchup: { season: 2026, week: 6 },
      availability: projection == null ? "unavailable" : "available",
      forecast: { projectionPpr: projection },
    },
    recentHistory: { games },
  } as Dashboard;
}

test("actual results take precedence over a stored forecast, including zero", () => {
  const result = overviewData(data([game(6, 0), game(5, 20)], 12));
  assert.equal(result.mode, "actual");
  assert.equal(result.value, 0);
  assert.equal(result.average, 20);
});
test("published forecast remains the primary value before the game", () => {
  const result = overviewData(data([game(5, 20)], 12));
  assert.equal(result.mode, "forecast");
  assert.equal(result.value, 12);
});
test("unpublished weeks use descriptive history, excluding DNF, DNP and future games", () => {
  const result = overviewData(
    data([
      game(7, 100),
      game(5, 50, "dnf"),
      game(4, 0, "dnp"),
      game(3, 20),
      game(2, 0),
    ]),
  );
  assert.equal(result.mode, "history");
  assert.equal(result.value, 10);
  assert.equal(result.sampleSize, 2);
});
test("recent average uses at most four games, sorted newest first", () => {
  assert.equal(
    overviewData(
      data([game(1, 100), game(3, 10), game(5, 20), game(2, 0), game(4, 10)]),
    ).average,
    10,
  );
});
test("DNF actual remains visible but is not included in prior average", () => {
  const result = overviewData(data([game(6, 2, "dnf"), game(5, 10)]));
  assert.equal(result.value, 2);
  assert.equal(result.average, 10);
});
test("empty histories do not invent a score", () => {
  const result = overviewData(data([]));
  assert.equal(result.value, null);
  assert.equal(result.sampleSize, 0);
});
