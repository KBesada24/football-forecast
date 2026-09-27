import "server-only";

export async function backendFetch(path: string, body?: string): Promise<Response> {
  const configured = process.env.BACKEND_URL?.trim();
  if (!configured && process.env.NODE_ENV === "production")
    throw new Error("BACKEND_URL must be configured in production.");
  const origin = configured || "http://127.0.0.1:8000";
  return fetch(`${origin.replace(/\/$/, "")}/api/v1/${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
    headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
    method: body ? "POST" : "GET",
    body,
    redirect: "error",
  });
}

export async function backendGet<T>(path: string): Promise<T> {
  const response = await backendFetch(path);
  if (!response.ok)
    throw new Error("The football data service is unavailable.");
  return response.json() as Promise<T>;
}
