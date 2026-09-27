import { ForecastApp } from "@/components/forecast-app";
import { backendGet } from "@/lib/backend";
import type { Context, Player } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [context, suggestions] = await Promise.allSettled([
    backendGet<Context>("meta/current-context"),
    backendGet<{ results: Player[] }>("players/search?q=Justin%20Jefferson"),
  ]);
  return (
    <ForecastApp
      context={context.status === "fulfilled" ? context.value : null}
      initialPlayer={
        suggestions.status === "fulfilled"
          ? (suggestions.value.results[0] ?? null)
          : null
      }
    />
  );
}
