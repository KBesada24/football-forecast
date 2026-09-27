"use client";
import { useState } from "react";
import Link from "next/link";
import type { Context, Dashboard, Player, Rankings } from "@/lib/types";
import { useResource } from "@/lib/use-resource";
import { PlayerSearch } from "./player-search";
import { dateLabel, PlayerDashboard } from "./player-dashboard";
import { RankingsList } from "./rankings-list";
import { MyTeam } from "./my-team";

function Message({
  title,
  children,
  retry,
}: {
  title: string;
  children: React.ReactNode;
  retry?: () => void;
}) {
  return (
    <div className="empty-state" role="status">
      <div className="empty-mark" aria-hidden="true">
        —
      </div>
      <h2>{title}</h2>
      <p>{children}</p>
      {retry ? (
        <button className="primary-button" onClick={retry}>
          Try again <span>↗</span>
        </button>
      ) : null}
    </div>
  );
}

export function ForecastApp({
  context,
  initialPlayer,
}: {
  context: Context | null;
  initialPlayer: Player | null;
}) {
  const [selected, setSelected] = useState(initialPlayer);
  const [season, setSeason] = useState(
    context?.default_season ?? context?.available_seasons.at(-1) ?? 2026,
  );
  const [week, setWeek] = useState(context?.default_week ?? 1);
  const [view, setView] = useState<"player" | "rankings" | "team">("player");
  const [position, setPosition] = useState("WR");
  const dashboard = useResource<Dashboard>(
    context && selected && view === "player"
      ? `players/${encodeURIComponent(selected.playerId)}/dashboard?season=${season}&week=${week}&include_selected_week=true`
      : null,
  );
  const rankings = useResource<Rankings>(
    context && view === "rankings"
      ? `rankings?season=${season}&week=${week}&position=${position}`
      : null,
  );
  function choosePlayer(player: Player) {
    setSelected(player);
    setView("player");
  }
  return (
    <>
      <a className="skip-link" href="#workspace">
        Skip to forecasts
      </a>
      <header className="site-header">
        <Link className="brand" href="/" aria-label="Football Forecast home">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          football<span className="brand-light">forecast</span>
          <span className="beta">PREVIEW</span>
        </Link>
        <span className="header-note">A clearer view of game week.</span>
        <a className="header-link" href="#data-notes">
          Data notes <span>↗</span>
        </a>
      </header>
      <main id="workspace" className="workspace">
        <div className="workspace-heading">
          <div>
            <div className="eyebrow">THE WEEKLY WORKSPACE</div>
            <h1>Game week, in focus.</h1>
            <p>Player projections and the history behind them.</p>
          </div>
          <div className="season-selectors">
            <label>
              Season
              <select
                value={season}
                disabled={!context?.available_seasons.length}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setSeason(next);
                  const weeks =
                    context?.available_weeks_by_season[String(next)] ?? [];
                  setWeek(weeks.includes(week) ? week : (weeks[0] ?? 1));
                }}
              >
                {(context?.available_seasons ?? [season]).map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Game week
              <select
                value={week}
                disabled={!context}
                onChange={(event) => setWeek(Number(event.target.value))}
              >
                {(
                  context?.available_weeks_by_season[String(season)] ?? [week]
                ).map((value) => (
                  <option key={value} value={value}>
                    Week {String(value).padStart(2, "0")}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <div className="toolbar">
          <nav aria-label="Workspace views">
            <button
              className={view === "player" ? "active" : ""}
              aria-pressed={view === "player"}
              onClick={() => setView("player")}
            >
              Player explorer
            </button>
            <button
              className={view === "rankings" ? "active" : ""}
              aria-pressed={view === "rankings"}
              onClick={() => setView("rankings")}
            >
              Best matchups
            </button>
            <button className={view === "team" ? "active" : ""}
              aria-pressed={view === "team"} onClick={() => setView("team")}>My team</button>
          </nav>
          {view !== "team" ? <PlayerSearch onSelect={choosePlayer} /> : <span className="team-toolbar-note">Full lineup · QB through D/ST</span>}
        </div>
        {!context ? (
          <Message
            title="The data service is offline"
            retry={() => window.location.reload()}
          >
            Your workspace is ready. Start the backend and try again to load
            real players and game history.
          </Message>
        ) : view === "team" ? <MyTeam key={`${season}:${week}`} season={season} week={week}
          onWeek={(nextSeason, nextWeek) => { setSeason(nextSeason); setWeek(nextWeek); }} /> : view === "player" ? (
          <>
            {dashboard.loading ? (
              <div className="loading-state" role="status" aria-live="polite">
                <span className="loading-line" />
                <p>
                  Loading {selected?.displayName} · Week {week}…
                </p>
              </div>
            ) : dashboard.error ? (
              <Message
                title="Couldn’t load this player"
                retry={dashboard.retry}
              >
                {dashboard.error}
              </Message>
            ) : dashboard.data ? (
              <PlayerDashboard data={dashboard.data} />
            ) : (
              <Message title="Start with a player">
                Search a running back, wide receiver, or tight end to explore
                their next matchup.
              </Message>
            )}
          </>
        ) : (
          <section className="rankings-section">
            <div className="section-heading">
              <div>
                <div className="eyebrow">WEEK {week} / BEST MATCHUPS</div>
                <h2>Best matchups</h2>
              </div>
              <div className="position-filter" aria-label="Position filter">
                {["RB", "WR", "TE"].map((value) => (
                  <button
                    key={value}
                    aria-pressed={position === value}
                    className={position === value ? "selected" : ""}
                    onClick={() => setPosition(value)}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
            <p className="muted">
              {rankings.data?.status === "actual"
                ? "Actual full-PPR results, ranked within position. These are recorded performances, not pregame predictions."
                : "A 50/50 blend of baseline-points and opponent-favorability percentiles, within position. Preliminary estimates use the latest available data and assume participation."}
            </p>
            {rankings.loading ? (
              <div className="loading-state" role="status">
                Loading matchups…
              </div>
            ) : rankings.error ? (
              <Message title="Couldn’t load matchups" retry={rankings.retry}>
                {rankings.error}
              </Message>
            ) : !rankings.data?.results.length ? (
              <Message
                title={
                  rankings.data?.status === "actual"
                    ? "No completed results yet"
                    : "No matchup estimates available yet"
                }
              >
                {rankings.data?.status === "actual"
                  ? "Results will appear as completed-game statistics are imported. Try an earlier week or another position."
                  : "Try the next upcoming week or another position. Estimates need player history and opponent data; past weeks show recorded results."}
              </Message>
            ) : (
              <RankingsList data={rankings.data} onSelect={choosePlayer} />
            )}
          </section>
        )}
        <footer id="data-notes">
          <div>
            <span className="footer-brand">footballforecast</span>
            <p>Full-PPR · Regular season · Complete lineups in My team</p>
          </div>
          <div>
            <p>Data retrieved {dateLabel(context?.latest_data_as_of)}</p>
            <p>2024–2026 coverage · Forecasts assume participation.</p>
          </div>
          <div>
            <span className="footer-status">
              <i />
              {context ? "Data loaded" : "Data connection unavailable"}
            </span>
            <p>Development preview · No live injury monitoring</p>
          </div>
        </footer>
      </main>
    </>
  );
}
