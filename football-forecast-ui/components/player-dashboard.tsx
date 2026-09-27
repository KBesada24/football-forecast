import type { Dashboard, Game } from "@/lib/types";
import { overviewData } from "@/lib/overview";

export const number = (value: number | null | undefined) =>
  value == null ? "—" : value.toFixed(1);
export function dateLabel(value: string | null | undefined) {
  return value
    ? new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "America/New_York",
      }).format(new Date(value))
    : "Not available";
}
const reasons: Record<string, string> = {
  unverified_roster: "The roster for this week is not available yet.",
  forecast_not_published: "This week’s forecast has not been published yet.",
  incomplete_stat_coverage:
    "Some recorded appearances are missing complete statistics.",
  insufficient_history:
    "There aren’t enough recorded games to project this player.",
  inactive_or_unverified_roster_status:
    "This player’s active roster status is not confirmed.",
  bye: "This player’s team has a bye this week.",
  unverified_schedule: "The matchup schedule is not available yet.",
};

function HistoryChart({ games }: { games: Game[] }) {
  if (!games.length)
    return (
      <p className="empty-inline">
        No completed game results are available through the selected week.
      </p>
    );
  const ordered = [...games].reverse();
  const max = Math.max(10, ...games.map((g) => g.fantasyPointsPpr));
  const min = Math.min(0, ...games.map((g) => g.fantasyPointsPpr));
  const range = max - min;
  return (
    <div
      className="history-chart"
      role="img"
      aria-label="Actual PPR by game, oldest to newest. Exact values are in the game log below."
    >
      {ordered.map((game, index) => (
        <div className="chart-column" key={game.gameId ?? index}>
          <span className="chart-value">{number(game.fantasyPointsPpr)}</span>
          <div className="bar-track">
            <span
              className="zero-line"
              style={{ bottom: `${(-min / range) * 100}%` }}
            />
            <div
              className={`bar ${game.completionStatus} ${game.fantasyPointsPpr < 0 ? "negative" : ""}`}
              style={{
                height: `${(Math.abs(game.fantasyPointsPpr) / range) * 100}%`,
                bottom: `${((Math.min(0, game.fantasyPointsPpr) - min) / range) * 100}%`,
                animationDelay: `${index * 30}ms`,
              }}
            />
          </div>
          <span className="chart-opponent">{game.opponent ?? "—"}</span>
          <span className="chart-week">
            {game.season} · W{game.week}
          </span>
        </div>
      ))}
    </div>
  );
}

function GameLog({ games }: { games: Game[] }) {
  const hasDnf = games.some((game) => game.completionStatus === "dnf");
  return (
    <div
      className="table-scroll"
      tabIndex={0}
      role="region"
      aria-label="Scrollable game log"
    >
      <table>
        <caption className="sr-only">
          Completed game statistics through the selected week
        </caption>
        <thead>
          <tr>
            <th scope="col">Week</th>
            <th scope="col">Matchup</th>
            <th scope="col">PPR</th>
            <th scope="col">Targets</th>
            <th scope="col">Rec.</th>
            <th scope="col">Carries</th>
            <th scope="col">Rush yds</th>
            <th scope="col">Rec. yds</th>
            <th scope="col">TD</th>
            {hasDnf ? <th scope="col">Notes</th> : null}
          </tr>
        </thead>
        <tbody>
          {games.map((game, index) => (
            <tr key={game.gameId ?? index}>
              <td>
                {game.season}{" "}
                <span className="muted">
                  / {String(game.week).padStart(2, "0")}
                </span>
              </td>
              <td>
                {game.team ?? "—"}{" "}
                <span className="muted">
                  {game.homeAway === "away" ? "@" : "vs"}
                </span>{" "}
                {game.opponent ?? "—"}
              </td>
              <td className="score-cell">{number(game.fantasyPointsPpr)}</td>
              <td>{game.targets ?? "—"}</td>
              <td>{game.receptions ?? "—"}</td>
              <td>{game.carries ?? "—"}</td>
              <td>{game.rushingYards ?? "—"}</td>
              <td>{game.receivingYards ?? "—"}</td>
              <td>{game.touchdowns}</td>
              {hasDnf ? (
                <td>
                  {game.completionStatus === "dnf"
                    ? "DNF · excluded from averages"
                    : "—"}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PlayerDashboard({ data }: { data: Dashboard }) {
  const { player, matchup, forecast, ranking, caveats } = data.projection;
  const games = data.recentHistory.games;
  const overview = overviewData(data);
  const showForecast = overview.mode === "forecast";
  const opponentAverage = data.versusOpponent.summary.averagePpr;
  return (
    <div className="player-dashboard reveal">
      <section className="player-heading" aria-labelledby="player-name">
        <div className="player-identity">
          <div className="player-monogram" aria-hidden="true">
            {player.displayName
              .split(" ")
              .map((part) => part[0])
              .slice(0, 2)
              .join("")}
          </div>
          <div>
            <div className="eyebrow">
              {player.position} <span> / </span>{" "}
              {player.team ?? "Team unavailable"}
            </div>
            <h2 id="player-name">{player.displayName}</h2>
          </div>
        </div>
        <div className="matchup">
          <span className="eyebrow">WEEK {matchup.week} MATCHUP</span>
          <strong>
            {matchup.opponent
              ? `${matchup.homeAway === "away" ? "@" : "vs"} ${matchup.opponent}`
              : matchup.status === "bye"
                ? "Bye week"
                : "Awaiting roster"}
          </strong>
          <span>
            {matchup.gameDateTime
              ? dateLabel(matchup.gameDateTime)
              : "Matchup not yet available"}
          </span>
        </div>
      </section>
      <section className="overview" aria-label="Player overview">
        <div className="projection-block">
          <span className="eyebrow">
            {overview.mode === "actual"
              ? `WEEK ${matchup.week} · ACTUAL FULL-PPR`
              : showForecast
                ? "PROJECTED FULL-PPR"
                : "RECENT AVERAGE · FULL-PPR"}
          </span>
          <div
            className={`projection-value${overview.value == null ? " no-score" : ""}`}
          >
            {overview.value == null ? "No history yet" : number(overview.value)}
            {overview.value != null ? <span>pts</span> : null}
          </div>
          <span className="status-pill">
            <i />
            {overview.mode === "actual"
              ? "Recorded result"
              : showForecast
                ? "Baseline estimate"
                : "Historical context · not a projection"}
          </span>
          <p>
            {overview.actual
              ? `${overview.actual.receptions ?? "—"} receptions · ${overview.actual.receivingYards ?? "—"} receiving yds · ${overview.actual.rushingYards ?? "—"} rushing yds · ${overview.actual.touchdowns} TD.${overview.actual.completionStatus === "dnf" ? " DNF — excluded from averages." : ""}`
              : showForecast
                ? "Trailing-four eligible-game baseline. Assumes this player participates."
                : overview.sampleSize
                  ? `Average of ${overview.sampleSize} eligible appearances in the recent game log before Week ${matchup.week}. No forecast has been published.`
                  : (reasons[forecast.unavailableReason ?? ""] ??
                    "Select a player or week with recorded appearances.")}
          </p>
        </div>
        <div className="context-block">
          <div className="section-label">
            THE CONTEXT <span>01 / OVERVIEW</span>
          </div>
          <div className="context-metrics">
            <div>
              <span>
                {showForecast
                  ? "Recent eligible average"
                  : "Prior-game average"}
              </span>
              <strong>
                {number(
                  showForecast ? forecast.recentPprAverage4 : overview.average,
                )}
                <small> PPR</small>
              </strong>
              <p>
                {showForecast
                  ? "Up to 4 eligible appearances"
                  : `${overview.sampleSize} eligible games in the recent log · before Week ${matchup.week}`}
              </p>
            </div>
            <div>
              <span>
                {showForecast && ranking.positionRank != null
                  ? "Matchup rank"
                  : opponentAverage != null
                    ? `Previously vs ${data.versusOpponent.opponent}`
                    : "Prior appearances"}
              </span>
              <strong>
                {showForecast && ranking.positionRank != null
                  ? `#${ranking.positionRank}`
                  : opponentAverage != null
                    ? number(opponentAverage)
                    : overview.sampleSize}
                <small>
                  {" "}
                  {showForecast && ranking.positionRank != null
                    ? player.position
                    : opponentAverage != null
                      ? "PPR"
                      : "games"}
                </small>
              </strong>
              <p>
                {showForecast && ranking.positionRank != null
                  ? "Points + opponent favorability"
                  : opponentAverage != null
                    ? `${data.versusOpponent.eligibleGamesCount} eligible games · historical average`
                    : "Eligible games in the recent log"}
              </p>
            </div>
          </div>
          <p className="context-note">
            {overview.actual
              ? `Week ${matchup.week} results are shown above. Prior-game averages exclude this result; they are historical context, not a pregame forecast.`
              : forecast.batchId
                ? `${forecast.eligibleGamesPrior} eligible games from ${forecast.gamesPlayedPrior} prior appearances. ${forecast.historyQuality === "limited" ? "Limited player history." : ""}`
                : "Historical averages are shown while the forecast is pending. Reported DNFs are excluded from averages."}
          </p>
          {ranking.opponentPprPerAppearance != null ? (
            <p className="context-note">
              Opponent allowed {number(ranking.opponentPprPerAppearance)} PPR
              per {player.position} appearance across {ranking.opponentGames}{" "}
              games ({ranking.opponentAppearances} appearances). Descriptive
              context, not a predicted matchup boost.
            </p>
          ) : null}
          <div className="publication-line">
            <span>{showForecast ? "Forecast snapshot" : "Stats updated"}</span>
            <span>
              {dateLabel(
                showForecast
                  ? forecast.generatedAt
                  : data.recentHistory.dataAsOf,
              )}
            </span>
          </div>
        </div>
      </section>
      <section className="history-section" aria-labelledby="history-heading">
        <div className="section-heading">
          <div>
            <div className="eyebrow">02 / RECENT FORM</div>
            <h3 id="history-heading">
              The last {games.length || "recorded"} games
            </h3>
          </div>
          <span className="quiet-label">
            Through Week {matchup.week} · oldest to newest
          </span>
        </div>
        <HistoryChart games={games} />
        <div className="chart-legend">
          <span>
            <i className="legend-dot" />
            Actual points
          </span>
          <span>
            DNF scores stay in the log, but are excluded from player averages.
          </span>
        </div>
        {games.length ? <GameLog games={games} /> : null}
        <p className="source-note">
          Source: nflverse via nflreadpy · Retrieved{" "}
          {dateLabel(data.recentHistory.dataAsOf)}. Completed games only,
          including the selected week when available.
        </p>
      </section>
      <section className="opponent-section" aria-labelledby="opponent-heading">
        <div>
          <div className="eyebrow">03 / OPPONENT HISTORY</div>
          <h3 id="opponent-heading">
            {data.versusOpponent.opponent
              ? `Previously against ${data.versusOpponent.opponent}`
              : "Opponent context"}
          </h3>
          <p>{data.versusOpponent.caveat}</p>
        </div>
        <div className="opponent-stat">
          <strong>{number(data.versusOpponent.summary.averagePpr)}</strong>
          <span>Eligible average PPR</span>
          <small>
            {data.versusOpponent.eligibleGamesCount} eligible /{" "}
            {data.versusOpponent.gamesCount} recorded games
          </small>
        </div>
      </section>
      <details className="methodology">
        <summary>
          Scoring, methodology & data notes <span>+</span>
        </summary>
        <div>
          <p>
            Full-PPR: 1 point per reception, 0.1 per rushing/receiving yard, 6
            per rushing/receiving touchdown, 0.04 per passing yard, 4 per
            passing touchdown, −2 per interception and lost fumble. No two-point
            conversions or return touchdowns.
          </p>
          <p>
            Recorded appearances count in player averages unless a DNF or
            nonparticipation is reported. Genuine zero-point appearances count.
            Completion reports are not required, so unreported early exits may
            remain in averages. Forecast inputs always exclude the target week,
            even when its actual results are shown below.
          </p>
          {caveats.map((caveat) => (
            <p key={caveat}>{caveat}</p>
          ))}
          <p>
            Model: {forecast.modelName ?? "No published model"} · Version:{" "}
            {forecast.modelVersion ?? "—"}. Tuesday refresh is planned for 8 am
            Eastern; automatic scheduling is not yet deployed.
          </p>
          {forecast.batchId ? (
            <p className="mono">
              Batch: {forecast.batchId} · Cutoff: {forecast.cutoff}
            </p>
          ) : null}
        </div>
      </details>
    </div>
  );
}
