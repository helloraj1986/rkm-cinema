import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { api, ApiError, resetUnauthorizedCooldown, setUnauthorizedHandler } from "./client";

describe("frozen /api client surface", () => {
  it("exposes the config/health/library contract methods", () => {
    expect(typeof api.getConfig).toBe("function");
    expect(typeof api.getHealth).toBe("function");
    expect(typeof api.getLibraryItems).toBe("function");
    expect(typeof api.getLibraryRecent).toBe("function"); // /api/library (Home row)
    expect(typeof api.getContinueWatching).toBe("function");
    expect(typeof api.getEpisodes).toBe("function");
    expect(typeof api.getItemDetail).toBe("function"); // preplay detail
  });

  it("classifies non-2xx as ApiError with a status", () => {
    const err = new ApiError(404, "GET /api/x -> 404");
    expect(err.status).toBe(404);
    expect(err).toBeInstanceOf(Error);
  });
});

// ---------------------------------------------------------------- auth (Phase 1)
// The client owns exactly ONE auth rule — "a 401 on an APP call means the session is
// gone" — and these pin its edges: one sign-out per burst of failures, and the auth
// routes themselves exempt (a wrong password is the form's business, and `me()` saying
// 401 is the ordinary signed-out state).
describe("session plumbing", () => {
  let calls: { url: string; init: RequestInit }[];

  function stubFetch(status: number, body?: unknown) {
    calls = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: unknown, init: RequestInit = {}) => {
        calls.push({ url: String(input), init });
        return new Response(body === undefined ? null : JSON.stringify(body), {
          status,
          headers: { "content-type": "application/json" },
        });
      }),
    );
  }

  beforeEach(() => {
    resetUnauthorizedCooldown();
    setUnauthorizedHandler(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setUnauthorizedHandler(null);
  });

  it("sends the HttpOnly session cookie on every call", async () => {
    stubFetch(200, { user: { id: "uid-1", name: "Rajeev" }, expires: "" });
    await api.me();
    expect(calls[0].url).toBe("/api/auth/me");
    expect(calls[0].init.credentials).toBe("same-origin");
  });

  it("posts the credentials to the login route (and keeps them out of the URL)", async () => {
    stubFetch(200, { ok: true, user: { id: "uid-1", name: "Rajeev" }, expires: "" });
    await api.login("rajeev", "s3cret");
    expect(calls[0].url).toBe("/api/auth/login");
    expect(calls[0].init.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      username: "rajeev",
      password: "s3cret",
    });
  });

  it("does NOT sign the app out when the LOGIN route answers 401", async () => {
    // A wrong password must leave the form in charge; redirecting would lose the message.
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    stubFetch(401, { detail: "Incorrect username or password" });
    await expect(api.login("rajeev", "nope")).rejects.toThrow(ApiError);
    expect(handler).not.toHaveBeenCalled();
  });

  it("does NOT sign the app out when me() answers 401 (the signed-out answer)", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    stubFetch(401);
    await expect(api.me()).rejects.toThrow(ApiError);
    expect(handler).not.toHaveBeenCalled();
  });

  it("signs out ONCE for a burst of failed app calls", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    stubFetch(401, { detail: "Sign in to use this app" });
    await expect(api.getConfig()).rejects.toThrow(ApiError);
    await expect(api.getHealth()).rejects.toThrow(ApiError);
    await expect(api.getLibraryFolders()).rejects.toThrow(ApiError);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("fires again after the cooldown, so a later session can also expire", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    stubFetch(401);
    await expect(api.getConfig()).rejects.toThrow(ApiError);
    expect(handler).toHaveBeenCalledTimes(1);
    resetUnauthorizedCooldown();
    await expect(api.getConfig()).rejects.toThrow(ApiError);
    expect(handler).toHaveBeenCalledTimes(2);
  });

  it("leaves a non-401 failure alone (it is not a session problem)", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    stubFetch(500, { detail: "boom" });
    await expect(api.getConfig()).rejects.toThrow(ApiError);
    expect(handler).not.toHaveBeenCalled();
  });
});