"use client";

import { useEffect, useRef, useState } from "react";
import { useResource } from "@/lib/use-resource";
import { DEFAULT_SLOTS, SLOT_TYPES, eligible, emptyDraft, fingerprint, parseDraft, parseSaved,
  slotLabel, type Draft, type LineupPlayer, type Recommendation, type WeekLineups } from "@/lib/lineup";

const ROSTER_KEY = "football-forecast:roster:v1";
const points = (value: number | null | undefined) => value == null ? "—" : value.toFixed(1);
const date = (value?: string) => value ? new Date(value).toLocaleString(undefined,
  { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—";

function PlayerContext({ player: p }: { player: LineupPlayer }) {
  const f = p.features;
  return <details className="lineup-explanation">
    <summary>Why this estimate</summary>
    <div className="explanation-content">
      <p>{p.model_kind === "ridge" ? "Matchup model · five-game form, workload, positional opponent context and past meetings."
        : "Five-game baseline · the richer model did not improve held-out accuracy for this position."}</p>
      <dl className="lineup-factors">
        <div><dt>Recent average</dt><dd>{points(f.average5)} <small>pts · {f.sample} / 5 appearances</small></dd></div>
        <div><dt>Past vs {p.matchup?.opponent ?? "opponent"}</dt><dd>{points(f.head_to_head.average)} <small>pts · {f.head_to_head.sample} meetings</small></dd></div>
        <div><dt>{p.position === "DST" ? "Opponent allows to D/ST" : `Defense allows to ${slotLabel(p.position)}`}</dt>
          <dd>{points(f.defense.average)} <small>pts / game · {f.defense.sample} games</small></dd></div>
        <div><dt>League comparison</dt><dd>{points(f.defense.league_average)} <small>pts / position / game</small></dd></div>
      </dl>
      {f.last5.length ? <p className="last-five">{f.last5.map(g =>
        <span key={`${g.season}:${g.week}`}>{g.season} W{g.week} · {g.opponent}<strong>{points(g.points)}</strong></span>)}</p> : null}
      {["RB", "WR", "TE", "QB"].includes(p.position) ? <p>Recent workload: {points(f.workload.targets)} targets, {points(f.workload.carries)} carries{p.position === "QB" ? `, ${points(f.workload.attempts)} pass attempts` : ""} per appearance.</p> : null}
      <p>{f.defense.sample ? "Opponent context is shrunk toward the league average; no extra bonus is added on top of the model." : "No reliable opponent sample; neutral context is used."}
        {f.defense.missing_games ? ` ${f.defense.missing_games} incomplete defensive samples excluded.` : ""}</p>
      <p>{f.sample < 5 ? "Limited player history. " : ""}Reported DNF/DNP games are excluded from player history; unknown completion is included.</p>
      <p>{p.availability}{p.position !== "DST" ? `. Team assignment from Week ${p.roster_week} roster.` : "."}</p>
    </div>
  </details>;
}

function LineupResult({ result, stale, frozen }: { result: Recommendation; stale: boolean; frozen: boolean }) {
  return <section className="lineup-result" aria-label="Recommended lineup">
    <div className="lineup-total">
      <div><div className="eyebrow">{frozen ? "SAVED PREGAME LINEUP" : stale ? "PREVIOUS RECOMMENDATION" : "RECOMMENDED STARTERS"}</div>
        <h3>{result.complete ? "Your starting lineup" : "Your lineup needs a few more players"}</h3>
        <p>{result.complete ? "Highest projected total within your slots and preferences." : `Unfilled: ${result.missing_slots.map(slotLabel).join(", ")}. Add eligible players to complete it.`}</p></div>
      <div className="lineup-total-number">{points(result.total)}<span>{result.complete ? "projected pts" : "partial total"}</span></div>
    </div>
    {stale ? <p className="lineup-notice">Your roster, settings, or weekly data changed. This is the previous recommendation{frozen ? "; this week is locked." : " — recommend again to update it."}</p> : null}
    <div className="lineup-table">
      <div className="lineup-table-header"><span>Slot</span><span>Starter / matchup</span><span>Proj.</span></div>
      {result.starters.map(s => <div className="lineup-starter" key={s.index}>
        <span className="slot-tag">{slotLabel(s.slot)}</span>
        <div>{s.player ? <><strong>{s.player.name}</strong><p className="lineup-subline">{s.player.team} · {s.player.matchup?.home ? "vs" : "@"} {s.player.matchup?.opponent} · {date(s.player.matchup?.kickoff)}{s.locked ? " · Locked by you" : ""}</p></>
          : <><strong>Open slot</strong><p className="lineup-subline">Add an eligible {slotLabel(s.slot)} to your roster.</p></>}</div>
        <strong className="lineup-points">{points(s.player?.projection)}</strong>
        {s.player ? <div className="starter-context"><PlayerContext player={s.player} /></div> : null}
      </div>)}
    </div>
    {result.bench.length ? <section className="lineup-bench"><h3>Bench & close calls</h3>
      {result.bench.map(b => <div className="bench-row" key={b.player.id}>
        <div><strong>{b.player.name}</strong><p>{slotLabel(b.player.position)} · {b.reason}
          {b.gap !== null ? ` · ${points(b.gap)} pts behind the closest eligible starter` : ""}</p>
          {b.gap !== null && b.gap >= 0 && b.gap <= 2 ? <p className="close-call">Close call — a small estimate gap, not a confident separation.</p> : null}</div>
        <span>{points(b.player.projection)}</span>
      </div>)}</section> : null}
    <p className="lineup-footnote">Saved {date(result.generated_at)} · Data retrieved {date(result.data_as_of)}. Estimates, not guaranteed scores. Nothing is submitted to ESPN.</p>
  </section>;
}

export function MyTeam({ season, week, onWeek }: { season: number; week: number; onWeek: (season: number, week: number) => void }) {
  const resource = useResource<WeekLineups>(`lineups/week?season=${season}&week=${week}`);
  const data = resource.data;
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [ready, setReady] = useState(false);
  const [storageNote, setStorageNote] = useState("");
  const [saved, setSaved] = useState<ReturnType<typeof parseSaved>>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [clock, setClock] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const weekKey = `football-forecast:week:v1:${season}:${week}`;
  const resultKey = `${weekKey}:result`;
  const frozen = data?.status === "locked" || Boolean(data?.first_kickoff && clock >= Date.parse(data.first_kickoff));
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        setDraft(parseDraft(localStorage.getItem(ROSTER_KEY), localStorage.getItem(weekKey)));
        setSaved(parseSaved(localStorage.getItem(resultKey)));
      } catch { setStorageNote("Saved data could not be read. Your changes will stay in this tab if browser storage is unavailable."); }
      setReady(true); setClock(Date.now());
    }, 0);
    const interval = setInterval(() => setClock(Date.now()), 15_000);
    return () => { clearTimeout(timer); clearInterval(interval); controller.current?.abort(); };
  }, [weekKey, resultKey]);
  useEffect(() => {
    if (!ready) return;
    try {
      localStorage.setItem(ROSTER_KEY, JSON.stringify({ version: 1, members: draft.members, slots: draft.slots }));
      localStorage.setItem(weekKey, JSON.stringify({ excluded: draft.excluded, locks: draft.locks }));
    } catch {
      // Keep the in-memory roster usable even with storage blocked or full.
      const timer = setTimeout(() => setStorageNote("Browser storage is unavailable. Keep this tab open; changes may not survive a reload."), 0);
      return () => clearTimeout(timer);
    }
  }, [draft, ready, weekKey]);
  function update(next: Draft) { setDraft(next); setError(""); }
  async function recommend() {
    if (!data?.snapshot_id || frozen) return;
    const signature = fingerprint(draft);
    const requestDraft = draft;
    controller.current?.abort();
    const active = new AbortController(); controller.current = active;
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/football/lineups/optimize", { method: "POST", signal: active.signal,
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ season, week,
          snapshot_id: data.snapshot_id, roster: requestDraft.members.map(m => m.id), slots: requestDraft.slots,
          excluded: requestDraft.excluded, locks: requestDraft.locks }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error ?? "Could not recommend a lineup.");
      if (!active.signal.aborted) {
        const next = { fingerprint: signature, result: body as Recommendation };
        setSaved(next);
        try { localStorage.setItem(resultKey, JSON.stringify(next)); }
        catch { setStorageNote("Recommendation is visible but could not be saved to this browser."); }
      }
    } catch (e) { if (!active.signal.aborted) setError(e instanceof Error ? e.message : "Please try again."); }
    finally { if (!active.signal.aborted) setBusy(false); }
  }
  const playerMap = new Map(data?.players.map(p => [p.id, p]) ?? []);
  const members = new Set(draft.members.map(m => m.id));
  const matches = (data?.players ?? []).filter(p => !members.has(p.id)
    && (filter === "ALL" || p.position === filter)
    && `${p.name} ${p.team ?? ""}`.toLowerCase().includes(query.toLowerCase().trim()))
    .sort((a, b) => (b.projection ?? -Infinity) - (a.projection ?? -Infinity)).slice(0, 8);
  const signature = fingerprint(draft);
  const stale = Boolean(saved && (saved.fingerprint !== signature || (data?.snapshot_id && saved.result.snapshot_id !== data.snapshot_id)));

  return <section className="my-team">
    <div className="section-heading"><div><div className="eyebrow">WEEK {week} / MY TEAM</div><h2>Set your starting lineup.</h2></div><span className="team-scoring">ESPN · Full-PPR</span></div>
    <p className="muted">Your players. Your starting slots. The highest projected total for the week ahead.</p>
    {resource.loading ? <p role="status">Loading weekly projections…</p> : resource.error ? <p role="alert">{resource.error} <button className="text-action" onClick={resource.retry}>Retry</button></p> : null}
    {data?.status === "unavailable" ? <div className="lineup-notice">No pregame snapshot was prepared for this week.
      {data.suggested_week ? <button className="text-action" onClick={() => onWeek(data.suggested_week!.season, data.suggested_week!.week)}>Open {data.suggested_week.season} Week {data.suggested_week.week} →</button> : null}</div> : null}
    {frozen ? <p className="lineup-notice">This week has started. Your saved pregame recommendation stays here; recomputing with in-game results is disabled.</p> : null}
    {storageNote ? <p className="lineup-notice" role="status">{storageNote}</p> : null}
    <div className="team-layout">
      <aside className="roster-editor" aria-label="Your roster">
        <div className="roster-heading"><h3>Your roster</h3><span>{draft.members.length} / 30</span></div>
        <p className="lineup-footnote">Add your starters and bench. Saved only in this browser, on this website address.</p>
        <label className="roster-search-label">Find a player or defense<input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search name or team…" disabled={!ready || !data?.players.length} /></label>
        <div className="roster-filters" aria-label="Roster search position">{["ALL", "QB", "RB", "WR", "TE", "K", "DST"].map(p =>
          <button key={p} aria-pressed={filter === p} onClick={() => setFilter(p)}>{slotLabel(p)}</button>)}</div>
        {data?.players.length ? <div className="roster-search-results" aria-label="Players to add">
          {matches.length ? matches.map(p => <button key={p.id} disabled={draft.members.length >= 30 || !ready}
            onClick={() => { update({ ...draft, members: [...draft.members, { id: p.id, name: p.name, position: p.position }] }); setQuery(""); }}>
            <span><strong>{p.name}</strong><small>{slotLabel(p.position)} · {p.team ?? "Team unknown"} · {p.projection === null ? "No estimate" : `${points(p.projection)} pts`}</small></span><span aria-hidden="true">+</span>
          </button>) : <p>No matching players. Try a name, team, or another position.</p>}
        </div> : null}
        <div className="roster-members">{draft.members.length ? draft.members.map(m => {
          const p = playerMap.get(m.id); const lock = Object.entries(draft.locks).find(([, id]) => id === m.id)?.[0] ?? "";
          return <div className="roster-member" key={m.id}><div className="member-title"><div><strong>{m.name}</strong><small>{slotLabel(m.position)} · {p?.team ?? "—"} · {points(p?.projection)} pts</small></div>
            <button className="text-action" aria-label={`Remove ${m.name}`} onClick={() => update({ ...draft, members: draft.members.filter(v => v.id !== m.id), excluded: draft.excluded.filter(id => id !== m.id), locks: Object.fromEntries(Object.entries(draft.locks).filter(([, id]) => id !== m.id)) })}>Remove</button></div>
            {p?.unavailable_reason || !p ? <p className="member-warning">{p?.unavailable_reason ?? "Not in this week's dataset"}</p> : null}
            <div className="member-controls"><label><input type="checkbox" checked={draft.excluded.includes(m.id)} onChange={e => update({ ...draft,
              excluded: e.target.checked ? [...draft.excluded, m.id] : draft.excluded.filter(id => id !== m.id),
              locks: Object.fromEntries(Object.entries(draft.locks).filter(([, id]) => id !== m.id)) })} /> Sit out</label>
              <label className="lock-label"><span className="sr-only">Lock {m.name} into a slot</span><select value={lock} disabled={!p || p.projection === null || draft.excluded.includes(m.id)} onChange={e => {
                const locks = Object.fromEntries(Object.entries(draft.locks).filter(([, id]) => id !== m.id));
                if (e.target.value !== "") locks[e.target.value] = m.id;
                update({ ...draft, locks });
              }}><option value="">Auto-select slot</option>{draft.slots.map((s, i) => eligible(m.position, s) ? <option key={i} value={String(i)} disabled={Boolean(draft.locks[i] && draft.locks[i] !== m.id)}>Lock {slotLabel(s)} · {i + 1}</option> : null)}</select></label>
            </div></div>;
        }) : <div className="roster-empty"><span>01</span><p>Add your fantasy team above.<br />Include the bench so we can compare your options.</p></div>}</div>
        <details className="slot-settings"><summary>Starting slots <span>{draft.slots.length} starters</span></summary>
          <p>FLEX accepts RB, WR or TE. Up to 12 starters; no Superflex or IDP.</p>
          <div className="slot-counts">{SLOT_TYPES.map(s => <label key={s}>{slotLabel(s)}<select aria-label={`${slotLabel(s)} starting slots`} value={draft.slots.filter(v => v === s).length} onChange={e => {
            const next = SLOT_TYPES.flatMap(type => Array.from({ length: type === s ? Number(e.target.value) : draft.slots.filter(v => v === type).length }, () => type));
            if (next.length < 1 || next.length > 12) { setError("Choose between 1 and 12 starting slots."); return; }
            update({ ...draft, slots: next, locks: {} });
          }}>{[0, 1, 2, 3, 4].map(n => <option key={n} value={n}>{n}</option>)}</select></label>)}</div>
          <button className="text-action" onClick={() => update({ ...draft, slots: [...DEFAULT_SLOTS], locks: {} })}>Reset ESPN starting slots</button>
          <p>Changing slots clears manual slot locks.</p>
        </details>
        <button className="primary-button recommend-button" disabled={!ready || busy || !draft.members.length || data?.status !== "ready" || frozen}
          onClick={recommend}>{busy ? "Choosing your lineup…" : "Recommend lineup"}<span aria-hidden="true">↗</span></button>
        {error ? <p className="lineup-error" role="alert">{error}</p> : null}
      </aside>
      <div className="lineup-workspace">
        {saved ? <LineupResult result={saved.result} stale={stale} frozen={frozen} /> : <div className="lineup-intro">
          <div className="eyebrow">YOUR WEEK, OPTIMIZED</div><h3>A place for every starter.</h3>
          <p>Add your roster, then compare every eligible combination — including whether an RB, WR, or TE gives you the strongest FLEX.</p>
          <div className="empty-slots">{draft.slots.map((s, i) => <div key={i}><span>{slotLabel(s)}</span><i /><small>Open</small></div>)}</div>
          <p className="lineup-footnote">Only your players are considered. No ESPN login or account connection required.</p>
        </div>}
        <div className="lineup-caveat"><strong>Before you set your team</strong><p>Projections assume the player participates in their usual role. Check injuries, starting status, and late roster changes yourself. Use “Sit out” to exclude anyone. Tuesday updates do not monitor game-day news.</p></div>
        <details className="lineup-method"><summary>Scoring, data & model checks</summary>
          <p>ESPN full-PPR preset: 1 per reception; 4 per passing TD; 6 per rushing/receiving TD; two-point conversions, return TDs and lost fumbles included. K: 3/4/5/6 for field goals under 40 / 40–49 / 50–59 / 60+ yards, 1 per PAT, −1 per missed FG. D/ST includes points-allowed and yards-allowed tiers. Custom league scoring is not supported yet.</p>
          <p>Last five eligible appearances across 2024–2026, not five calendar weeks. Defense context uses position totals per game, not per-player averages. Missing context is neutral; missing recent player scoring data means no projection. No invented injury probability or confidence interval.</p>
          <p>{data?.evaluation_note}</p>
          {data?.model_report ? <div className="model-table"><div><strong>Position</strong><strong>Model used</strong><strong>Test MAE</strong></div>{Object.entries(data.model_report).map(([pos, r]) => <div key={pos}><span>{slotLabel(pos)}</span><span>{r.promoted ? "Matchup model" : "5-game baseline"}</span><span>{points(r.promoted ? r.holdout_challenger?.mae : r.holdout_baselines?.mean5.mae)} pts</span></div>)}</div> : null}
          <p>Snapshot {date(data?.generated_at)} · Source retrieved {date(data?.data_as_of)}. Updated offline; never retrained by clicking Recommend.</p>
        </details>
      </div>
    </div>
  </section>;
}
