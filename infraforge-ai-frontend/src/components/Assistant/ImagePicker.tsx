import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Camera, Upload } from "lucide-react";

export type ImageSource = "upload" | "camera";

export interface ImagePickerHandle {
  openMenu: () => void;
}

interface Props {
  disabled: boolean;
  onPick: (file: File, source: ImageSource) => void;
  openSignal?: number;
  /** Hide the standalone camera button — use with imperative openMenu(). */
  hideTrigger?: boolean;
}

const ImagePicker = forwardRef<ImagePickerHandle, Props>(function ImagePicker(
  { disabled, onPick, openSignal, hideTrigger = false },
  ref,
) {
  const [open, setOpen] = useState(false);

  useImperativeHandle(ref, () => ({
    openMenu: () => setOpen(true),
  }));

  useEffect(() => {
    if (openSignal) setOpen(true);
  }, [openSignal]);

  const wrapRef = useRef<HTMLDivElement>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const sourceRef = useRef<ImageSource>("upload");

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
    if (file) onPick(file, sourceRef.current);
    e.target.value = "";
    setOpen(false);
  };

  const openPicker = (source: ImageSource, inputRef: React.RefObject<HTMLInputElement | null>) => {
    sourceRef.current = source;
    inputRef.current?.click();
  };

  return (
    <div className={`relative ${hideTrigger ? "" : ""}`} ref={wrapRef}>
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

      {!hideTrigger && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={disabled}
          title="Search by image"
          className="h-11 w-11 flex items-center justify-center rounded-xl bg-surface-container-high border border-border-subtle text-on-surface-variant hover:text-primary hover:border-primary/40 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
        >
          <Camera className="w-4 h-4" />
        </button>
      )}

      {open && (
        <div className="absolute bottom-full left-0 mb-2 z-50 w-[min(16rem,calc(100vw-2rem))] chat-action-submenu overflow-hidden">
          <button
            type="button"
            onClick={() => openPicker("camera", cameraRef)}
            className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-xs text-on-surface hover:bg-surface-container-high cursor-pointer transition-colors"
          >
            <Camera className="w-4 h-4 text-primary" /> Take photo
          </button>
          <div className="h-px bg-border-subtle" />
          <button
            type="button"
            onClick={() => openPicker("upload", uploadRef)}
            className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-xs text-on-surface hover:bg-surface-container-high cursor-pointer transition-colors"
          >
            <Upload className="w-4 h-4 text-primary" /> Upload image
          </button>
        </div>
      )}
    </div>
  );
});

export default ImagePicker;
