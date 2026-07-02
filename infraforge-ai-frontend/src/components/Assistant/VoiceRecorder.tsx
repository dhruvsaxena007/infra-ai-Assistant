import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { Mic, Square, X } from "lucide-react";

/** Default max recording duration (seconds) — matches backend VOICE_MAX_DURATION_SECONDS. */
export const VOICE_MAX_RECORDING_SECONDS = 120;

const MIME_PRIORITY = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "audio/ogg",
] as const;

const WAVE_BAR_COUNT = 7;

export function selectRecordingMimeType(): { mimeType: string; extension: string } {
  if (typeof window === "undefined" || typeof MediaRecorder === "undefined") {
    return { mimeType: "audio/webm", extension: "webm" };
  }
  for (const candidate of MIME_PRIORITY) {
    if (MediaRecorder.isTypeSupported(candidate)) {
      if (candidate.startsWith("audio/mp4")) {
        return { mimeType: candidate, extension: "m4a" };
      }
      if (candidate.startsWith("audio/ogg")) {
        return { mimeType: candidate, extension: "ogg" };
      }
      return { mimeType: candidate, extension: "webm" };
    }
  }
  return { mimeType: "", extension: "webm" };
}

export interface VoiceRecorderHandle {
  start: () => void;
  cancel: () => void;
  stopAndSend: () => void;
}

interface Props {
  disabled: boolean;
  onRecorded: (file: File) => void;
  onError: (message: string) => void;
  onRecordingChange?: (recording: boolean) => void;
  startSignal?: number;
  maxDurationSeconds?: number;
  /** Compact mic button for inside the chat input bar. */
  variant?: "default" | "inline";
  /** When true, idle mic is hidden — parent triggers recording via ref.start(). */
  hideIdleButton?: boolean;
  className?: string;
}

/** Detect browser support for in-app recording. */
function isRecordingSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function" &&
    typeof window.MediaRecorder !== "undefined"
  );
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function defaultWaveLevels(): number[] {
  return Array.from({ length: WAVE_BAR_COUNT }, () => 0.25);
}

function VoiceWaveform({ levels, live }: { levels: number[]; live: boolean }) {
  return (
    <div
      className={`voice-waveform ${live ? "voice-waveform--live" : "voice-waveform--idle"}`}
      aria-hidden
    >
      {levels.map((level, i) => (
        <span
          key={i}
          className="voice-waveform-bar"
          style={
            live
              ? { height: `${6 + level * 20}px`, animationDelay: `${i * 0.05}s` }
              : { animationDelay: `${i * 0.1}s` }
          }
        />
      ))}
    </div>
  );
}

function useLiveAudioLevels(stream: MediaStream | null, active: boolean): number[] {
  const [levels, setLevels] = useState(defaultWaveLevels);

  useEffect(() => {
    if (!active || !stream) {
      setLevels(defaultWaveLevels());
      return;
    }

    let cancelled = false;
    let rafId = 0;
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;

    const ctx = new AudioCtx();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 64;
    analyser.smoothingTimeConstant = 0.82;
    const source = ctx.createMediaStreamSource(stream);
    source.connect(analyser);
    const buffer = new Uint8Array(analyser.frequencyBinCount);

    const tick = () => {
      if (cancelled) return;
      analyser.getByteFrequencyData(buffer);
      const step = Math.max(1, Math.floor(buffer.length / WAVE_BAR_COUNT));
      const next = Array.from({ length: WAVE_BAR_COUNT }, (_, i) => {
        let sum = 0;
        for (let j = 0; j < step; j += 1) {
          sum += buffer[i * step + j] ?? 0;
        }
        const avg = sum / step / 255;
        return Math.max(0.12, Math.min(1, avg * 2.2));
      });
      setLevels(next);
      rafId = window.requestAnimationFrame(tick);
    };

    void ctx.resume().then(() => {
      if (!cancelled) rafId = window.requestAnimationFrame(tick);
    });

    return () => {
      cancelled = true;
      window.cancelAnimationFrame(rafId);
      source.disconnect();
      void ctx.close();
    };
  }, [active, stream]);

  return levels;
}

/**
 * In-app voice recorder for POST /voice/chat.
 * Uses the MediaRecorder API; falls back to an audio file input when the
 * browser does not support recording.
 */
const VoiceRecorder = forwardRef<VoiceRecorderHandle, Props>(function VoiceRecorder(
  {
    disabled,
    onRecorded,
    onError,
    onRecordingChange,
    startSignal,
    maxDurationSeconds = VOICE_MAX_RECORDING_SECONDS,
    variant = "default",
    hideIdleButton = false,
    className = "",
  },
  ref,
) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [activeStream, setActiveStream] = useState<MediaStream | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const discardRef = useRef(false);
  const fallbackRef = useRef<HTMLInputElement>(null);
  const mimeRef = useRef(selectRecordingMimeType());
  const busyRef = useRef(false);
  const startingRef = useRef(false);

  const supported = isRecordingSupported();
  const waveLevels = useLiveAudioLevels(activeStream, recording);

  const stopTracks = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setActiveStream(null);
  };

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const setRecordingState = (value: boolean) => {
    setRecording(value);
    onRecordingChange?.(value);
  };

  const stopRecording = (discard: boolean) => {
    discardRef.current = discard;
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    } else {
      clearTimer();
      stopTracks();
      setRecordingState(false);
    }
  };

  const startRecording = async () => {
    if (disabled || recording || busyRef.current || startingRef.current) return;

    if (!supported) {
      onError(
        "Voice recording is not supported in this browser. Please upload an audio file.",
      );
      fallbackRef.current?.click();
      return;
    }

    startingRef.current = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      setActiveStream(stream);
      chunksRef.current = [];
      discardRef.current = false;
      mimeRef.current = selectRecordingMimeType();
      const { mimeType } = mimeRef.current;

      const options = mimeType ? { mimeType } : undefined;
      const recorder = new MediaRecorder(stream, options);
      recorderRef.current = recorder;

      recorder.ondataavailable = (e: BlobEvent) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        clearTimer();
        stopTracks();
        setRecordingState(false);
        startingRef.current = false;

        if (discardRef.current) return;

        const { mimeType: blobType, extension } = mimeRef.current;
        const type = blobType || chunksRef.current[0]?.type || "audio/webm";
        const blob = new Blob(chunksRef.current, { type });
        if (blob.size === 0) {
          onError("No audio was captured. Please try recording again.");
          return;
        }
        const file = new File([blob], `voice-message.${extension}`, { type });
        busyRef.current = true;
        onRecorded(file);
        busyRef.current = false;
      };

      recorder.onerror = () => {
        startingRef.current = false;
        onError("Recording failed. Please try again.");
        stopRecording(true);
      };

      // Timesliced capture improves reliability across browsers.
      recorder.start(250);
      setRecordingState(true);
      setSeconds(0);
      timerRef.current = window.setInterval(() => {
        setSeconds((prev) => {
          const next = prev + 1;
          if (next >= maxDurationSeconds) {
            stopRecording(false);
          }
          return next;
        });
      }, 1000);
    } catch (err) {
      startingRef.current = false;
      stopTracks();
      const name = (err as DOMException)?.name;
      if (name === "NotAllowedError" || name === "SecurityError") {
        onError("Microphone permission denied. Please allow mic access and try again.");
      } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
        onError("No microphone was found on this device.");
      } else {
        onError("Could not start voice recording. Please try again or upload an audio file.");
      }
    }
  };

  const startRecordingRef = useRef(startRecording);
  startRecordingRef.current = startRecording;
  const stopRecordingRef = useRef(stopRecording);
  stopRecordingRef.current = stopRecording;

  useImperativeHandle(ref, () => ({
    start: () => {
      void startRecordingRef.current();
    },
    cancel: () => stopRecordingRef.current(true),
    stopAndSend: () => stopRecordingRef.current(false),
  }));

  // Clean up tracks/timers if the component unmounts mid-recording.
  useEffect(() => {
    return () => {
      discardRef.current = true;
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch {
          /* ignore */
        }
      }
      clearTimer();
      stopTracks();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (startSignal && !disabled && !recording && !startingRef.current) {
      void startRecording();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startSignal]);

  if (recording) {
    return (
      <div
        className={`voice-recording-bar flex items-center gap-2 sm:gap-3 bg-surface-container-high border border-primary/40 rounded-xl px-3 sm:px-4 py-2.5 ${className}`}
        role="status"
        aria-live="polite"
        aria-label="Recording voice message"
      >
        <VoiceWaveform levels={waveLevels} live />
        <div className="min-w-0 flex-1">
          <span className="text-sm text-on-surface font-medium block leading-tight">
            Listening…
          </span>
          <span className="text-[11px] font-mono text-primary/80">
            {formatTime(seconds)} / {formatTime(maxDurationSeconds)}
          </span>
        </div>
        <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={() => stopRecording(true)}
            title="Cancel recording"
            aria-label="Cancel recording"
            className="h-9 w-9 flex items-center justify-center rounded-lg bg-surface-container-highest border border-border-subtle text-on-surface-variant hover:text-on-surface cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => stopRecording(false)}
            title="Stop and send"
            aria-label="Stop and send voice message"
            className="h-9 px-3 flex items-center gap-1.5 rounded-lg gradient-orange text-on-primary font-medium text-xs cursor-pointer active:scale-95 transition-transform"
          >
            <Square className="w-3.5 h-3.5 fill-current" /> Stop
          </button>
        </div>
      </div>
    );
  }

  const micButtonClass =
    variant === "inline"
      ? "h-9 w-9 flex items-center justify-center rounded-lg text-on-surface-variant hover:text-primary hover:bg-surface-container-highest/80 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors focus-visible:ring-2 focus-visible:ring-primary/40 flex-shrink-0"
      : "h-11 w-11 flex items-center justify-center rounded-xl bg-surface-container-high border border-border-subtle text-on-surface-variant hover:text-primary hover:border-primary/40 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors";

  if (hideIdleButton) {
    return (
      <input
        ref={fallbackRef}
        type="file"
        accept="audio/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) {
            if (f.size === 0) {
              onError("The selected audio file is empty.");
            } else {
              onRecorded(f);
            }
          }
          e.target.value = "";
        }}
      />
    );
  }

  return (
    <div className={className}>
      <input
        ref={fallbackRef}
        type="file"
        accept="audio/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) {
            if (f.size === 0) {
              onError("The selected audio file is empty.");
            } else {
              onRecorded(f);
            }
          }
          e.target.value = "";
        }}
      />
      <button
        type="button"
        onClick={() => void startRecording()}
        disabled={disabled}
        title={supported ? "Record voice" : "Upload audio file"}
        aria-label={supported ? "Record voice message" : "Upload audio file"}
        className={micButtonClass}
      >
        <Mic className="w-4 h-4" />
      </button>
    </div>
  );
});

export default VoiceRecorder;
