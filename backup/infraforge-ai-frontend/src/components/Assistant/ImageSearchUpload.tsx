import React, { useRef, useState } from "react";
import { ImagePlus, SendHorizonal } from "lucide-react";

interface Props {
  disabled: boolean;
  onSend: (file: File) => void;
}

/** Image file upload for POST /image-search. */
export default function ImageSearchUpload({ disabled, onSend }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  const pick = (f: File | null) => {
    setFile(f);
    setPreview(f ? URL.createObjectURL(f) : null);
  };

  return (
    <div className="flex items-center gap-3">
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/jpg,image/webp"
        className="hidden"
        onChange={(e) => pick(e.target.files?.[0] ?? null)}
      />

      {preview ? (
        <img
          src={preview}
          alt="preview"
          className="w-11 h-11 rounded-xl object-cover border border-border-subtle"
        />
      ) : null}

      <button
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        className="flex items-center gap-2 px-4 py-3 rounded-xl bg-surface-container-high border border-border-subtle text-sm text-on-surface hover:border-primary/40 cursor-pointer disabled:opacity-40 transition-colors"
      >
        <ImagePlus className="w-4 h-4" />
        {file ? "Change image" : "Choose machine image"}
      </button>

      <div className="flex-1 text-xs text-on-surface-variant truncate">
        {file ? file.name : "Upload a .jpg / .png / .webp machine photo"}
      </div>

      <button
        onClick={() => {
          if (file && !disabled) onSend(file);
        }}
        disabled={disabled || !file}
        className="h-11 px-4 flex items-center gap-2 rounded-xl gradient-orange text-white shadow-lg disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer text-sm font-medium active:scale-95 transition-all"
      >
        <SendHorizonal className="w-4 h-4" /> Search
      </button>
    </div>
  );
}
