import React, { useEffect, useRef, useState } from "react";
import { Mic, Square, X } from "lucide-react";

interface Props {
  disabled: boolean;
  /** Called with the recorded audio when the user stops (and doesn't cancel). */
  onRecorded: (file: File) => void;
  /** Surface a human-readable error to the parent (shown in ErrorBanner). */
  onError: (message: string) => void;
  /** Notify the parent when recording starts/stops so it can adjust the bar. */
  onRecordingChange?: (recording: boolean) => void;
  /** Increment to start recording from outside (e.g. suggestion chips). */
  startSignal?: number;
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

/**
 * In-app voice recorder for POST /voice/chat.
 * Uses the MediaRecorder API; falls back to an audio file input when the
 * browser does not support recording.
 */
export default function VoiceRecorder({
  disabled,
  onRecorded,
  onError,
  onRecordingChange,
  startSignal,
}: Props) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const discardRef = useRef(false);
  const fallbackRef = useRef<HTMLInputElement>(null);

  const supported = isRecordingSupported();

  // Clean up tracks/timers if the component unmounts mid-recording.
  useEffect(() => {
    return () => {
      stopTracks();
      clearTimer();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stopTracks = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
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

  const startRecording = async () => {
    if (disabled || recording) return;

    if (!supported) {
      onError(
        "Voice recording is not supported in this browser. Please upload an audio file.",
      );
      fallbackRef.current?.click();
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      discardRef.current = false;

      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;

      recorder.ondataavailable = (e: BlobEvent) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        clearTimer();
        stopTracks();
        setRecordingState(false);

        if (discardRef.current) return;

        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (blob.size === 0) {
          onError("No audio was captured. Please try recording again.");
          return;
        }
        const file = new File([blob], "voice-message.webm", { type: "audio/webm" });
        onRecorded(file);
      };

      recorder.start();
      setRecordingState(true);
      setSeconds(0);
      timerRef.current = window.setInterval(
        () => setSeconds((prev) => prev + 1),
        1000,
      );
    } catch (err) {
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

  useEffect(() => {
    if (startSignal && !disabled && !recording) {
      void startRecording();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startSignal]);

  // Recording UI takes over the bar.
  if (recording) {
    return (
      <div className="flex-1 flex items-center gap-3 bg-surface-container-high border border-error/40 rounded-xl px-4 py-3">
        <span className="relative flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-error opacity-75" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-error" />
        </span>
        <span className="text-sm text-on-surface font-medium">Recording</span>
        <span className="text-xs font-mono text-on-surface-variant">{formatTime(seconds)}</span>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => stopRecording(true)}
            title="Cancel recording"
            className="h-9 w-9 flex items-center justify-center rounded-lg bg-surface-container-highest border border-border-subtle text-on-surface-variant hover:text-on-surface cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
          <button
            onClick={() => stopRecording(false)}
            title="Stop and send"
            className="h-9 px-3 flex items-center gap-1.5 rounded-lg bg-error text-on-error font-medium text-xs cursor-pointer active:scale-95 transition-transform"
          >
            <Square className="w-3.5 h-3.5 fill-current" /> Stop &amp; send
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      <input
        ref={fallbackRef}
        type="file"
        accept="audio/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onRecorded(f);
          e.target.value = "";
        }}
      />
      <button
        onClick={startRecording}
        disabled={disabled}
        title={supported ? "Record voice" : "Upload audio file"}
        className="h-11 w-11 flex items-center justify-center rounded-xl bg-surface-container-high border border-border-subtle text-on-surface-variant hover:text-primary hover:border-primary/40 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
      >
        <Mic className="w-4 h-4" />
      </button>
    </>
  );
}
