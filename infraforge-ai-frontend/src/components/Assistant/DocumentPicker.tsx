import React, { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { FileText } from "lucide-react";

export interface DocumentPickerHandle {
  openPicker: () => void;
}

interface Props {
  disabled: boolean;
  onPick: (file: File) => void;
  openSignal?: number;
  hideTrigger?: boolean;
}

const ACCEPT = ".pdf,.doc,.docx,.txt,application/pdf,text/plain";

const DocumentPicker = forwardRef<DocumentPickerHandle, Props>(function DocumentPicker(
  { disabled, onPick, openSignal, hideTrigger = false },
  ref,
) {
  const inputRef = useRef<HTMLInputElement>(null);

  useImperativeHandle(ref, () => ({
    openPicker: () => inputRef.current?.click(),
  }));

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
      {!hideTrigger && (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={disabled}
          title="Attach document"
          className="h-10 w-10 sm:h-11 sm:w-11 flex items-center justify-center rounded-xl bg-surface-container-high/80 border border-border-subtle text-on-surface-variant hover:text-primary hover:border-primary/40 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
        >
          <FileText className="w-4 h-4" />
        </button>
      )}
    </>
  );
});

export default DocumentPicker;
