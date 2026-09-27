import { backendFetch } from "@/lib/backend";

// Explicit read-only allowlist: no arbitrary proxy destinations or admin endpoints.
const allowed =
  /^(meta\/current-context|players\/search|rankings|lineups\/week|players\/[A-Za-z0-9_-]+\/(dashboard|projection|history|vs-opponent))$/;

export async function GET(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const resource = path.join("/");
  if (!allowed.test(resource))
    return Response.json({ error: "Not found" }, { status: 404 });
  try {
    const query = new URL(request.url).search;
    const response = await backendFetch(resource + query);
    if (!response.ok) {
      return Response.json(
        {
          error:
            response.status === 404
              ? "Player not found."
              : response.status === 422
                ? "Please check the search, season, and week."
                : "Football data is temporarily unavailable. Please try again.",
        },
        {
          status: [404, 422].includes(response.status) ? response.status : 503,
        },
      );
    }
    return Response.json(await response.json(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json(
      { error: "Cannot reach the football data service. Please try again." },
      { status: 503 },
    );
  }
}

// Only this bounded, read-only calculation may accept a POST. No roster is stored server-side.
export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (path.join("/") !== "lineups/optimize")
    return Response.json({ error: "Not found" }, { status: 404 });
  try {
    if (!request.headers.get("content-type")?.includes("application/json"))
      return Response.json({ error: "Expected JSON" }, { status: 415 });
    const reader = request.body?.getReader();
    if (!reader) return Response.json({ error: "Missing lineup" }, { status: 400 });
    const chunks: Uint8Array[] = [];
    let size = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 16_384) {
        await reader.cancel();
        return Response.json({ error: "Lineup is too large" }, { status: 413 });
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    const body = new TextDecoder().decode(bytes);
    JSON.parse(body);
    const response = await backendFetch("lineups/optimize", body);
    const data = await response.json();
    if (!response.ok) return Response.json({ error:
      [409, 413, 422].includes(response.status) && typeof data.detail === "string"
        ? data.detail : "Please check your roster and starting slots, then retry."
    }, { status: [409, 413, 422].includes(response.status) ? response.status : 503 });
    return Response.json(data, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Unable to recommend a lineup. Please retry." }, { status: 503 });
  }
}
