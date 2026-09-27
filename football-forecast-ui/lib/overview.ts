import type { Dashboard } from "./types";

// Descriptive UI context only; this never creates or publishes a forecast.
export function overviewData(data: Dashboard) {
  const { matchup, forecast, availability } = data.projection;
  const games = data.recentHistory.games;
  const actual = games.find(
    (game) => game.season === matchup.season && game.week === matchup.week,
  );
  const prior = games
    .filter(
      (game) =>
        (game.season < matchup.season ||
          (game.season === matchup.season && game.week < matchup.week)) &&
        game.completionStatus !== "dnf" &&
        game.completionStatus !== "dnp",
    )
    .toSorted((a, b) => b.season - a.season || b.week - a.week)
    .slice(0, 4);
  const average = prior.length
    ? prior.reduce((sum, game) => sum + game.fantasyPointsPpr, 0) / prior.length
    : null;
  const hasForecast =
    availability === "available" && forecast.projectionPpr != null;
  const mode = actual ? "actual" : hasForecast ? "forecast" : "history";
  return {
    actual,
    mode,
    average,
    sampleSize: prior.length,
    value: actual
      ? actual.fantasyPointsPpr
      : hasForecast
        ? forecast.projectionPpr
        : average,
  };
}
