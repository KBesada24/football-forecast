"""Match canonical records only; never infer a team from a player's current roster."""

from collections import defaultdict
from typing import Any

from src.data.schema_validation import SourceSchemaError


class ScheduleIndex:
    def __init__(self, games: list[dict[str, Any]]) -> None:
        self.by_id = {game["game_id"]: game for game in games}
        self.by_team: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
        for game in games:
            for team in (game["home_team"], game["away_team"]):
                key = (game["season"], game["week"], game["game_type"], team)
                self.by_team[key].append(game)

    def match(self, row: dict[str, Any]) -> dict[str, Any] | None:
        game_id = row.get("game_id")
        if game_id:
            game = self.by_id.get(game_id)
            if game is None:
                return None
        else:
            key = (row["season"], row["week"], row["game_type"], row["team"])
            matches = self.by_team.get(key, [])
            if len(matches) > 1:
                raise SourceSchemaError(f"Ambiguous schedule match: {key}")
            if not matches:
                return None
            game = matches[0]
        if any(row[k] != game[k] for k in ("season", "week", "game_type")):
            raise SourceSchemaError(f"Game context disagrees with schedule: {game_id}")
        if row["team"] not in (game["home_team"], game["away_team"]):
            raise SourceSchemaError(f"Player team not in scheduled game: {game_id}")
        return game

    def context(self, row: dict[str, Any]) -> dict[str, Any]:
        game = self.match(row)
        if game is None:
            return dict(game_id=None, game_date=None, opponent_team=None, home_away=None)
        home = row["team"] == game["home_team"]
        opponent = game["away_team"] if home else game["home_team"]
        if row.get("opponent_team_source") not in (None, "", opponent):
            raise SourceSchemaError(f"Opponent disagrees with schedule: {game['game_id']}")
        return {
            "game_id": game["game_id"],
            "game_date": game["game_date"],
            "opponent_team": opponent,
            "home_away": (
                None
                if game["neutral_site"] is None
                else "neutral"
                if game["neutral_site"]
                else ("home" if home else "away")
            ),
        }
