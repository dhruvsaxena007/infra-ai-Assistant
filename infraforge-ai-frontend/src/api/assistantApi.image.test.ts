import { describe, expect, it } from "vitest";
import { IMAGE_SEARCH_MAX_BYTES } from "../api/assistantApi";

describe("image search constants", () => {
  it("max upload size is 8 MB", () => {
    expect(IMAGE_SEARCH_MAX_BYTES).toBe(8 * 1024 * 1024);
  });
});

describe("image clarification chips", () => {
  const CHIPS = new Set([
    "Exact same machine",
    "Similar machines",
    "Just identify this machine",
  ]);

  it("includes exact/similar/identify options", () => {
    expect(CHIPS.has("Exact same machine")).toBe(true);
    expect(CHIPS.has("Similar machines")).toBe(true);
    expect(CHIPS.has("Just identify this machine")).toBe(true);
  });
});
