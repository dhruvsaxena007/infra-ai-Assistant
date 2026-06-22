import React, { useEffect, useRef, useState } from "react";
import { Camera, Upload } from "lucide-react";

export type ImageSource = "upload" | "camera";

interface Props {
  disabled: boolean;
  /**
   * Called with the chosen image and where it came from. The image is NOT
   * uploaded here — the parent stores it as a pending image until the user
   * presses send.
   */
  onPick: (file: File, source: ImageSource) => void;
  /** Increment to open the image menu from outside (e.g. suggestion chips). */
  openSignal?: number;
}

/**
 * Image entry point. Opens a small menu with "Take photo" (camera capture on
 * mobile) and "Upload image" (file picker). Uses hidden file inputs.
 */
export default function ImagePicker({ disabled, onPick, openSignal }: Props) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (openSignal) setOpen(true);
  }, [openSignal]);
  const wrapRef = useRef<HTMLDivElement>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const sourceRef = useRef<ImageSource>("upload");

  // Close the menu when clicking outside.
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // If the user cancels the picker there is no file — do nothing (no error).
    if (file) onPick(file, sourceRef.current);
    e.target.value = "";
    setOpen(false);
  };

  const openPicker = (source: ImageSource, ref: React.RefObject<HTMLInputElement>) => {
    sourceRef.current = source;
    ref.current?.click();
  };

  return (
    <div className="relative" ref={wrapRef}>
      <input
        ref={uploadRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFile}
      />
      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={handleFile}
      />

      <button
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        title="Search by image"
        className="h-11 w-11 flex items-center justify-center rounded-xl bg-surface-container-high border border-border-subtle text-on-surface-variant hover:text-primary hover:border-primary/40 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
      >
        <Camera className="w-4 h-4" />
      </button>

      {open && (
        <div className="absolute bottom-12 right-0 z-50 w-44 bg-surface-container-highest border border-border-subtle rounded-xl shadow-2xl overflow-hidden message-enter">
          <button
            onClick={() => openPicker("camera", cameraRef)}
            className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-xs text-on-surface hover:bg-surface-container-high cursor-pointer transition-colors"
          >
            <Camera className="w-4 h-4 text-primary" /> Take photo
          </button>
          <div className="h-px bg-border-subtle" />
          <button
            onClick={() => openPicker("upload", uploadRef)}
            className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-xs text-on-surface hover:bg-surface-container-high cursor-pointer transition-colors"
          >
            <Upload className="w-4 h-4 text-primary" /> Upload image
          </button>
        </div>
      )}
    </div>
  );
}
