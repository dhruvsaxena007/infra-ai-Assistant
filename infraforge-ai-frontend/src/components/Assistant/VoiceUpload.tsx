import React, { useRef, useState } from "react";
import { Mic, Upload, SendHorizonal } from "lucide-react";

interface Props {
  disabled: boolean;
  onSend: (file: File) => void;
}

/** Audio file upload for POST /voice/chat. */
export default function VoiceUpload({ disabled, onSend }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);

  return (
    <div className="flex items-center gap-2">
      <input
        ref={inputRef}
        type="file"
        accept="audio/*"
        className="hidden"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <button
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        className="flex items-center gap-2 px-4 py-3 rounded-xl bg-surface-container-high border border-border-subtle text-sm text-on-surface hover:border-primary/40 cursor-pointer disabled:opacity-40 transition-colors"
      >
        <Upload className="w-4 h-4" />
        {file ? "Change audio" : "Choose audio file"}
      </button>

      <div className="flex-1 text-xs text-on-surface-variant truncate">
        {file ? (
          <span className="flex items-center gap-1.5">
            <Mic className="w-3.5 h-3.5 text-primary" /> {file.name}
          </span>
        ) : (
          "Upload a .mp3 / .wav / .m4a voice clip"
        )}
      </div>

      <button
        onClick={() => {
          if (file && !disabled) onSend(file);
        }}
        disabled={disabled || !file}
        className="h-11 px-4 flex items-center gap-2 rounded-xl gradient-orange text-white shadow-lg disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer text-sm font-medium active:scale-95 transition-all"
      >
        <SendHorizonal className="w-4 h-4" /> Send voice
      </button>
    </div>
  );
}
