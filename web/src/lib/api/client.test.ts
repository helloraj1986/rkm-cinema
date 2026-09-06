import { describe, it, expect } from "vitest";
import { api, ApiError } from "./client";

describe("frozen /api client surface", () => {
  it("exposes the config/health/library contract methods", () => {
    expect(typeof api.getConfig).toBe("function");
    expect(typeof api.getHealth).toBe("function");
    expect(typeof api.getLibraryItems).toBe("function");
    expect(typeof api.getLibraryRecent).toBe("function"); // /api/library (Home row)
    expect(typeof api.getContinueWatching).toBe("function");
    expect(typeof api.getEpisodes).toBe("function");
    expect(typeof api.getItemDetail).toBe("function"); // Plex preplay (detail)
  });

  it("classifies non-2xx as ApiError with a status", () => {
    const err = new ApiError(404, "GET /api/x -> 404");
    expect(err.status).toBe(404);
    expect(err).toBeInstanceOf(Error);
  });
});