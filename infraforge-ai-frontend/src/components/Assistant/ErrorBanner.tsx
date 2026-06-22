import React from "react";
import { AlertTriangle, X } from "lucide-react";

interface Props {
  message: string;
  onDismiss?: () => void;
}

/** Inline error banner for backend `success:false` responses and network errors. */
export default function ErrorBanner({ message, onDismiss }: Props) {
  return (
    <div className="bg-error-container/30 border border-error/30 text-on-error-container rounded-xl px-3 py-2.5 flex items-start gap-2.5 text-xs message-enter max-w-full">
      <AlertTriangle className="w-4 h-4 text-error flex-shrink-0 mt-0.5" />
      <span className="flex-1 leading-relaxed">{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="text-on-surface-variant hover:text-on-surface cursor-pointer"
          aria-label="Dismiss error"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
