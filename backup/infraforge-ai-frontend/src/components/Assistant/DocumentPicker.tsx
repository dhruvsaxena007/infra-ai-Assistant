import React, { useEffect, useRef } from "react";
import { FileText } from "lucide-react";

interface Props {
  disabled: boolean;
  /** Called when user picks a PDF or document — parent holds pending until send. */
  onPick: (file: File) => void;
  /** Increment to open the file picker from outside (e.g. suggestion chips). */
  openSignal?: number;
}

const ACCEPT = ".pdf,.doc,.docx,.txt,application/pdf,text/plain";

/** Opens native file picker for documents — no modal; attach then ask in chat. */
export default function DocumentPicker({ disabled, onPick, openSignal }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (openSignal) inputRef.current?.click();
  }, [openSignal]);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onPick(file);
    e.target.value = "";
  };

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={handleFile}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        title="Attach document"
        className="h-10 w-10 sm:h-11 sm:w-11 flex items-center justify-center rounded-xl bg-surface-container-high/80 border border-border-subtle text-on-surface-variant hover:text-primary hover:border-primary/40 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
      >
        <FileText className="w-4 h-4" />
      </button>
    </>
  );
}
