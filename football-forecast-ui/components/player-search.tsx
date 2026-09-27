"use client";
import { useId, useState } from "react";
import { useResource } from "@/lib/use-resource";
import type { Player } from "@/lib/types";

export function PlayerSearch({
  onSelect,
}: {
  onSelect: (player: Player) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const id = useId();
  const valid = query.replace(/[^\p{L}\p{N}]/gu, "").length >= 2;
  const result = useResource<{ results: Player[] }>(
    valid && open ? `players/search?q=${encodeURIComponent(query)}` : null,
    250,
  );
  const players = result.data?.results ?? [];
  const expanded = open && valid;
  function select(player: Player) {
    onSelect(player);
    setOpen(false);
    setQuery("");
    setActive(-1);
  }
  return (
    <div
      className="search"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        width="20"
        height="20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      >
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 4 4" />
      </svg>
      <input
        aria-label="Search NFL players"
        role="combobox"
        aria-expanded={expanded}
        aria-controls={expanded ? `${id}-results` : undefined}
        aria-autocomplete="list"
        autoComplete="off"
        aria-activedescendant={
          expanded && active >= 0 && players[active]
            ? `${id}-${active}`
            : undefined
        }
        placeholder="Search a player…"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setOpen(false);
            setActive(-1);
          }
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setActive((index) => Math.min(index + 1, players.length - 1));
          }
          if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((index) => Math.max(index - 1, 0));
          }
          if (event.key === "Enter" && players[active]) {
            event.preventDefault();
            select(players[active]);
          }
        }}
      />
      <span className="search-hint">RB / WR / TE</span>
      {expanded ? (
        <div className="search-popover">
          <div role="status" className="search-status">
            {result.loading
              ? "Searching players…"
              : result.error
                ? result.error
                : !players.length
                  ? "No players found. Try another name."
                  : "Select a player"}
          </div>
          {result.error ? (
            <button className="text-button" onClick={result.retry}>
              Try again
            </button>
          ) : null}
          <ul id={`${id}-results`} role="listbox" aria-label="Player results">
            {players.map((player, index) => (
              <li
                key={player.playerId}
                id={`${id}-${index}`}
                role="option"
                aria-selected={index === active}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setActive(index)}
                onClick={() => select(player)}
              >
                <span>{player.displayName}</span>
                <small>
                  {player.position} · {player.team ?? "Team unknown"}
                </small>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
