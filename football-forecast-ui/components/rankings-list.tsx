import type { Player, Rankings } from "@/lib/types";
import { dateLabel, number } from "./player-dashboard";

export function RankingsList({
  data,
  onSelect,
}: {
  data: Rankings;
  onSelect: (player: Player) => void;
}) {
  const actual = data.status === "actual";
  return (
    <>
      <div className="rankings-meta" role="status">
        <span className="eyebrow">
          {actual
            ? "Actual results"
            : data.status === "preliminary"
              ? "Preliminary estimates"
              : "Published forecast"}
        </span>
        <span>
          {data.results.length} players · Data updated{" "}
          {dateLabel(data.dataAsOf)}
          {actual
            ? ` · ${data.completedGames} / ${data.totalGames} games completed in imported data`
            : ""}
        </span>
      </div>
      <div className="ranking-list">
        {data.results.map((row) => (
          <button
            key={row.player.playerId}
            className={`ranking-row${actual ? "" : " matchup-ranking-row"}`}
            onClick={() => onSelect(row.player)}
            aria-label={`View ${row.player.displayName}, rank ${row.ranking.positionRank}`}
          >
            <span className="rank-number">{row.ranking.positionRank}</span>
            <span className="rank-player">
              <strong>{row.player.displayName}</strong>
              <small>
                {row.player.team} · {row.player.position} ·{" "}
                {row.matchup.homeAway === "away"
                  ? "@"
                  : row.matchup.homeAway === "neutral"
                    ? "vs (neutral)"
                    : "vs"}{" "}
                {row.matchup.opponent}
              </small>
            </span>
            <span className="rank-points">
              <strong>
                {number(actual ? row.actualPpr : row.forecast.projectionPpr)}
              </strong>
              <small>
                {actual
                  ? "Actual PPR"
                  : data.status === "preliminary"
                    ? "Estimated PPR"
                    : "Projected PPR"}
              </small>
            </span>
            {actual ? (
              <span className="rank-detail">
                <strong>
                  {row.completionStatus === "dnf" ? "DNF" : "Recorded"}
                </strong>
                <small>
                  {row.completionStatus === "dnf"
                    ? "Actual score retained"
                    : "Completed game"}
                </small>
              </span>
            ) : (
              <>
                <span className="rank-detail">
                  <strong>
                    {number(row.ranking.opponentPprPerAppearance)}
                  </strong>
                  <small>Opp. PPR / appearance</small>
                  <small>
                    {row.ranking.opponentGames} games ·{" "}
                    {row.ranking.opponentAppearances} appearances
                    {row.ranking.unavailableReason ===
                    "partial_opponent_coverage"
                      ? " · Partial coverage"
                      : ""}
                  </small>
                </span>
                <span className="rank-blend">
                  <strong>{number(row.ranking.combinedScore)}</strong>
                  <small>Blend / 100</small>
                </span>
              </>
            )}
            <span className="rank-arrow" aria-hidden="true">
              ↗
            </span>
          </button>
        ))}
      </div>
      <details className="methodology">
        <summary>
          Ranking methodology & coverage <span>+</span>
        </summary>
        <div>
          {data.caveats.map((note) => (
            <p key={note}>{note}</p>
          ))}
          {data.status === "preliminary" ? (
            <p>
              {data.excludedCount} of {data.candidateCount} candidates across
              all positions were omitted because of missing history, coverage,
              or an eligible matchup. Estimates assume participation; latest
              known active status is not a game-day guarantee.
            </p>
          ) : null}
          <p>
            Up to 100 players per position are shown. Tied scores share a rank.
          </p>
        </div>
      </details>
    </>
  );
}
