import { afterEach, expect, mock, test } from "bun:test";

mock.module("server-only", () => ({}));
const { backendFetch } = await import("./backend");
const { POST } = await import("../app/api/football/[...path]/route");
const originalFetch = globalThis.fetch;
const originalEnv = { BACKEND_URL: process.env.BACKEND_URL, NODE_ENV: process.env.NODE_ENV };

afterEach(() => {
  globalThis.fetch = originalFetch;
  for (const [key, value] of Object.entries(originalEnv)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
});

test("production rejects missing backend URL before fetching", async () => {
  Object.assign(process.env, { NODE_ENV: "production", BACKEND_URL: " " });
  globalThis.fetch = mock(() => { throw new Error("must not fetch"); }) as unknown as typeof fetch;
  await expect(backendFetch("health")).rejects.toThrow("BACKEND_URL");
  expect(globalThis.fetch).not.toHaveBeenCalled();
});

test("configured backend retains no-store, redirect rejection and POST body", async () => {
  process.env.BACKEND_URL = "https://example.invalid/";
  const fetchMock = mock(async () => Response.json({ ok: true }));
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  await backendFetch("lineups/optimize", "{}");
  expect(fetchMock).toHaveBeenCalledWith("https://example.invalid/api/v1/lineups/optimize",
    expect.objectContaining({ method: "POST", body: "{}", cache: "no-store", redirect: "error" }));
});

test("proxy preserves backend 413", async () => {
  process.env.BACKEND_URL = "https://example.invalid";
  globalThis.fetch = mock(async () => Response.json({ detail: "Lineup is too large" },
    { status: 413 })) as unknown as typeof fetch;
  const response = await POST(new Request("https://example.invalid/api/football/lineups/optimize", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  }), { params: Promise.resolve({ path: ["lineups", "optimize"] }) });
  expect(response.status).toBe(413);
  expect(await response.json()).toEqual({ error: "Lineup is too large" });
});
