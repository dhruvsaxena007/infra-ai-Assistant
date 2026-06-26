import React, { useEffect, useId, useRef } from "react";
import { Camera, FileText, Plus } from "lucide-react";

interface Props {
  disabled: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImageAction: () => void;
  onDocumentAction: () => void;
}

/**
 * Plus / close toggle with premium action menu for image & document uploads.
 */
export default function ChatInputActionMenu({
  disabled,
  open,
  onOpenChange,
  onImageAction,
  onDocumentAction,
}: Props) {
  const menuId = useId();
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node;
      if (rootRef.current && !rootRef.current.contains(target)) {
        onOpenChange(false);
      }
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpenChange(false);
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onOpenChange]);

  const toggle = () => {
    if (disabled) return;
    onOpenChange(!open);
  };

  return (
    <div className="relative flex-shrink-0" ref={rootRef}>
      <button
        type="button"
        onClick={toggle}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={menuId}
        aria-label={open ? "Close actions menu" : "Open upload actions"}
        className={`chat-action-plus h-9 w-9 flex items-center justify-center rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container-highest/80 disabled:opacity-40 transition-colors focus-visible:ring-2 focus-visible:ring-primary/40 ${open ? "is-open text-primary" : ""}`}
      >
        <Plus
          className={`w-[18px] h-[18px] chat-plus-icon ${open ? "is-open" : ""}`}
          strokeWidth={2.25}
        />
      </button>

      <div
        id={menuId}
        role="menu"
        aria-hidden={!open}
        className={`chat-action-menu ${open ? "is-open" : ""}`}
      >
        <button
          type="button"
          role="menuitem"
          className="chat-action-menu-item"
          onClick={() => {
            onOpenChange(false);
            onImageAction();
          }}
        >
          <span className="chat-action-menu-icon">
            <Camera className="w-4 h-4 text-primary" />
          </span>
          <span className="min-w-0 text-left">
            <span className="block text-sm text-on-surface font-medium">Upload image</span>
            <span className="block text-[11px] text-on-surface-variant leading-snug mt-0.5">
              Search exact or similar machines from a photo
            </span>
          </span>
        </button>

        <div className="h-px bg-border-subtle/80 mx-2" role="separator" />

        <button
          type="button"
          role="menuitem"
          className="chat-action-menu-item"
          onClick={() => {
            onOpenChange(false);
            onDocumentAction();
          }}
        >
          <span className="chat-action-menu-icon">
            <FileText className="w-4 h-4 text-tertiary" />
          </span>
          <span className="min-w-0 text-left">
            <span className="block text-sm text-on-surface font-medium">Upload document</span>
            <span className="block text-[11px] text-on-surface-variant leading-snug mt-0.5">
              Manuals, specs &amp; technical PDFs for Q&amp;A
            </span>
          </span>
        </button>
      </div>
    </div>
  );
}
