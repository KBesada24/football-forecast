export type Player = {
  playerId: string;
  displayName: string;
  position: string;
  team: string | null;
  headshotUrl: string | null;
  active?: boolean | null;
};
export type Context = {
  available_seasons: number[];
  available_weeks_by_season: Record<string, number[]>;
  default_season: number | null;
  default_week: number | null;
  latest_data_as_of: string | null;
  publication_status: string;
};
export type Projection = {
  availability: "available" | "unavailable" | "insufficient_history";
  player: Player;
  matchup: {
    season: number;
    week: number;
    opponent: string | null;
    homeAway: string | null;
    gameDateTime: string | null;
    status: string;
  };
  forecast: {
    projectionPpr: number | null;
    baselineProjectionPpr: number | null;
    recentPprAverage4: number | null;
    gamesPlayedPrior: number;
    eligibleGamesPrior: number;
    modelName: string | null;
    modelVersion: string | null;
    batchId: string | null;
    generatedAt: string | null;
    dataAsOf: string | null;
    cutoff: string | null;
    historyQuality: string;
    unavailableReason: string | null;
  };
  ranking: {
    positionRank: number | null;
    combinedScore: number | null;
    opponentPprPerAppearance: number | null;
    opponentGames: number;
    opponentAppearances: number;
    opponentMissingStatAppearances?: number;
    unavailableReason: string | null;
  };
  caveats: string[];
};
export type Game = {
  gameId: string | null;
  season: number;
  week: number;
  opponent: string | null;
  team: string | null;
  homeAway: string | null;
  fantasyPointsPpr: number;
  targets: number | null;
  receptions: number | null;
  carries: number | null;
  rushingYards: number | null;
  receivingYards: number | null;
  touchdowns: number;
  completionStatus: "finished" | "dnf" | "dnp" | "unknown";
};
export type Dashboard = {
  projection: Projection;
  recentHistory: {
    games: Game[];
    dataAsOf: string | null;
    includesSelectedWeek: boolean;
  };
  versusOpponent: {
    opponent: string | null;
    gamesCount: number;
    eligibleGamesCount: number;
    missingStatGames: number;
    summary: { averagePpr: number | null };
    caveat: string;
    games: Game[];
  };
};
export type Rankings = {
  status: "published" | "pending" | "preliminary" | "actual";
  dataAsOf: string | null;
  generatedAt: string | null;
  completedGames: number;
  totalGames: number;
  candidateCount: number;
  excludedCount: number;
  caveats: string[];
  results: (Projection & {
    actualPpr: number | null;
    completionStatus: Game["completionStatus"] | null;
  })[];
};
