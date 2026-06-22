import { describe, expect, it } from "vitest";
import {
  buildProgressiveRevealSchedule,
  buildProgressiveRevealSteps,
  tokenizeProgressiveText,
} from "./tokenizeProgressiveText";
import {
  RESPONSE_ANIMATION_CONFIG,
  baseWordDelayForTextLength,
  punctuationPauseAfterWordChunk,
  scaleScheduleToDurationWindow,
} from "./progressiveResponseConfig";

describe("tokenizeProgressiveText", () => {
  it("preserves spaces and line breaks", () => {
    const tokens = tokenizeProgressiveText("Hello world.\nSecond line.");
    expect(tokens.map((t) => t.text).join("")).toBe("Hello world.\nSecond line.");
  });

  it("identifies words vs whitespace", () => {
    const tokens = tokenizeProgressiveText("Hi there");
    expect(tokens.filter((t) => t.isWord)).toHaveLength(2);
    expect(tokens.some((t) => t.text === " ")).toBe(true);
  });
});

describe("buildProgressiveRevealSteps", () => {
  it("ends with the full backend text", () => {
    const full = "Excavator options in Jaipur are listed below.";
    const steps = buildProgressiveRevealSteps(full);
    expect(steps[steps.length - 1]).toBe(full);
  });

  it("reveals one word per step for multi-word text", () => {
    const full = "Hello world from InfraForge";
    const steps = buildProgressiveRevealSteps(full);
    expect(steps.length).toBe(5);
    expect(steps[0]).toBe("");
    expect(steps[1]).toBe("Hello");
    expect(steps[4]).toBe(full);
  });

  it("adds progressively longer cumulative text", () => {
    const full = "word ".repeat(10).trim();
    const steps = buildProgressiveRevealSteps(full);
    expect(steps.length).toBe(11);
    for (let i = 1; i < steps.length; i += 1) {
      expect(steps[i].length).toBeGreaterThan(steps[i - 1].length);
    }
  });
});

describe("buildProgressiveRevealSchedule", () => {
  it("uses initial delay before the first word", () => {
    const schedule = buildProgressiveRevealSchedule("Hello there");
    expect(schedule[1].delayBeforeMs).toBeGreaterThanOrEqual(
      RESPONSE_ANIMATION_CONFIG.initialDelay,
    );
  });

  it("adds sentence pause before the next word after a period", () => {
    const schedule = buildProgressiveRevealSchedule("Done. Next");
    const nextStep = schedule.find((s) => s.text === "Done. Next");
    expect(nextStep?.delayBeforeMs).toBeGreaterThanOrEqual(
      baseWordDelayForTextLength("Done. Next".length) +
        punctuationPauseAfterWordChunk("Done. "),
    );
  });

  it("scales short responses to minimum duration", () => {
    const schedule = buildProgressiveRevealSchedule("Hi");
    const total = schedule.slice(1).reduce((sum, s) => sum + s.delayBeforeMs, 0);
    expect(total).toBeGreaterThanOrEqual(RESPONSE_ANIMATION_CONFIG.minimumDuration - 50);
  });

  it("caps long responses at maximum duration", () => {
    const long = "word ".repeat(200).trim();
    const schedule = buildProgressiveRevealSchedule(long);
    const total = schedule.slice(1).reduce((sum, s) => sum + s.delayBeforeMs, 0);
    expect(total).toBeLessThanOrEqual(RESPONSE_ANIMATION_CONFIG.maximumDuration + 50);
  });

  it("uses faster per-word delay for long text", () => {
    const shortDelay = baseWordDelayForTextLength(40);
    const longDelay = baseWordDelayForTextLength(1200);
    expect(longDelay).toBeLessThan(shortDelay);
    expect(longDelay).toBeGreaterThanOrEqual(50);
    expect(shortDelay).toBeLessThanOrEqual(130);
  });
});

describe("progressive config", () => {
  it("exposes centralized animation config", () => {
    expect(RESPONSE_ANIMATION_CONFIG.normalWordDelay).toBe(100);
    expect(RESPONSE_ANIMATION_CONFIG.shapeMorphDuration).toBe(700);
  });

  it("scales schedules within duration window", () => {
    const scaled = scaleScheduleToDurationWindow([
      { text: "", delayBeforeMs: 0 },
      { text: "Hi", delayBeforeMs: 50 },
    ]);
    expect(scaled[1].delayBeforeMs).toBeGreaterThan(50);
  });
});
