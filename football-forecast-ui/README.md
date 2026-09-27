# Football Forecast UI

A responsive Next.js player explorer connected to the Python/Postgres backend.
Warm off-white surfaces, one deep-green accent, compact sections, and lightweight
CSS motion keep this first version easy to refine. No chart or UI framework added.

## Best matchups

RB/WR/TE filters now display imported actual-result leaderboards for past/started
weeks and prepared preliminary estimates for the next upcoming week. Published
forecasts take precedence over preliminary estimates before the week starts.
Each view labels its data type and timestamp; actuals report completed-game coverage,
while preliminary rows show opponent samples and partial-coverage warnings. Player
rows open the existing explorer. The cream/green layout is unchanged and opponent
context remains visible on mobile.

## Run locally

Start Postgres and the API using `../backend/README.md`, then run here:

```bash
bun install --frozen-lockfile
bun run dev --hostname 127.0.0.1 --port 3000
```

Open <http://localhost:3000>. The server defaults to the backend at
`http://127.0.0.1:8000`. Override with the server-only `BACKEND_URL` environment
variable if needed; do not put database credentials or ngrok tokens in frontend code.

## Share through ngrok

Use a production build for a public preview so development tools are not exposed:

```bash
bun run build
bun run start --hostname 127.0.0.1 --port 3000
```

In a separate terminal with ngrok already authenticated:

```bash
ngrok http http://127.0.0.1:3000 --inspect=false
```

Open the HTTPS URL printed by ngrok. Its free-plan interstitial may require
clicking **Visit Site** once. This is a public, unauthenticated, read-only preview,
not a production deployment. Keep the frontend, backend, Postgres, and tunnel
running. Stop ngrok with Ctrl+C when finished; temporary URLs may change on restart.

Only the frontend is tunneled. Browser requests go to `/api/football/...` on the
same origin, which forwards an explicit allowlist of GET endpoints to FastAPI.
There are no browser calls to localhost, exposed database credentials, arbitrary
proxy destinations, API docs forwarding, or write methods. Fetches are uncached
and backend timeouts return a readable error with retry.

The current preview runs as transient user services (not enabled at boot):
`football-forecast-api`, `football-forecast-ui`, and `football-forecast-tunnel`.
They remain running independently of the chat command session. To stop this preview:

```bash
systemctl --user stop football-forecast-tunnel football-forecast-ui football-forecast-api
```

After editing UI code, rebuild and restart `football-forecast-ui`; for rapid local
iteration, stop that service and use `bun run dev` instead. Keep public tunnels on
the production build unless deliberately testing the development server.

## First-version features

- Real player search with debounce, canceled stale requests, keyboard selection,
  loading, empty results, and failure states.
- Season/week selection, player projection, matchup, and snapshot context.
- Actual PPR bars and scrollable game logs through the selected week; reported DNF
  notes appear when relevant. The blanket Unverified column has been removed.
- Opponent context and per-position best-matchup rankings when published.
- Scoring/methodology disclosure, timestamps, and mobile layout.
- No fabricated forecasts: unpublished snapshots display unavailable/pending.

Initial selection is the real Justin Jefferson record if found in the backend.
Search to select another player. A previous early exit is not treated as next-week
ineligibility. The API remains responsible for all forecast/scoring calculations.
Completion reports are no longer a prerequisite for player averages: recorded
appearances count except reported DNFs/DNPs. Unreported early exits may remain.
Forecast inputs still exclude target-week outcomes; the inclusive game log is
only a display of completed actuals, never a source for pregame predictions.

## Verification

```bash
bun run lint
bun run build
```

Browser checks covered real search and keyboard selection, eight-game history,
week switching, pending rankings, desktop/mobile overflow, public proxy access,
failed-request recovery with retry, and rejected non-allowlisted routes and write
methods. These are smoke checks,
not yet a checked-in automated end-to-end test suite.
