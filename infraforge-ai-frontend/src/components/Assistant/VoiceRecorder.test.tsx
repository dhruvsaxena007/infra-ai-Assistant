import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { selectRecordingMimeType, VOICE_MAX_RECORDING_SECONDS } from "./VoiceRecorder";

describe("selectRecordingMimeType", () => {
  beforeEach(() => {
    vi.stubGlobal("MediaRecorder", {
      isTypeSupported: (mime: string) =>
        mime === "audio/webm;codecs=opus" || mime === "audio/mp4",
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("prefers opus webm when supported", () => {
    const { mimeType, extension } = selectRecordingMimeType();
    expect(mimeType).toBe("audio/webm;codecs=opus");
    expect(extension).toBe("webm");
  });

  it("falls back to mp4 for Safari-style support", () => {
    vi.stubGlobal("MediaRecorder", {
      isTypeSupported: (mime: string) => mime === "audio/mp4",
    });
    const { mimeType, extension } = selectRecordingMimeType();
    expect(mimeType).toBe("audio/mp4");
    expect(extension).toBe("m4a");
  });
});

describe("VOICE_MAX_RECORDING_SECONDS", () => {
  it("matches backend default", () => {
    expect(VOICE_MAX_RECORDING_SECONDS).toBe(120);
  });
});
