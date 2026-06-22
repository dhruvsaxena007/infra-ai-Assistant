import React from "react";

interface Props {
  label?: string;
}

/** Lightweight typing indicator — CSS only, no heavy motion. */
export default function LoadingIndicator({ label = "Thinking" }: Props) {
  return (
    <div className="flex items-center gap-2.5 min-w-[120px]" aria-live="polite">
      <div className="flex items-center gap-1 h-4" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="thinking-dot w-1.5 h-1.5 rounded-full bg-primary"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
      <span className="text-xs text-on-surface-variant font-medium">
        {label}…
      </span>
    </div>
  );
}
