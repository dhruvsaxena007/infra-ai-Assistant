import React, { memo } from "react";
import { Bot, User, Sparkles, Info } from "lucide-react";
import type { ChatMessage } from "../../types";

interface Props {
  message: ChatMessage;
  onSuggestionClick?: (text: string) => void;
  onRaiseSupportRequest?: (issueType?: string) => void;
}

function MessageBubble({ message, onSuggestionClick, onRaiseSupportRequest }: Props) {
  const isUser = message.role === "user";

  return (
    <div
      className={`flex gap-2.5 message-enter ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
          isUser
            ? "bg-surface-container-high text-on-surface-variant border border-border-subtle"
            : "gradient-orange text-on-primary shadow-md shadow-primary/10"
        }`}
        aria-hidden
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>

      <div
        className={`flex flex-col gap-2 min-w-0 ${
          isUser ? "items-end max-w-[70%]" : "items-start max-w-[85%] sm:max-w-[80%]"
        }`}
      >
        {message.meta && (
          <div className="text-[10px] font-mono uppercase tracking-wider text-on-surface-variant/70 px-1">
            {message.meta}
          </div>
        )}

        <div
          className={`chat-bubble px-3.5 py-2.5 rounded-2xl text-sm leading-[1.65] whitespace-pre-wrap break-words ${
            isUser
              ? "user-bubble rounded-tr-sm"
              : message.isError
                ? "error-bubble rounded-tl-sm"
                : "assistant-bubble rounded-tl-sm"
          }`}
        >
          {message.imageUrl && (
            <img
              src={message.imageUrl}
              alt="Uploaded machine"
              className="mb-2 w-full max-w-[200px] rounded-lg object-cover border border-border-subtle"
              loading="lazy"
            />
          )}
          {message.documentName && (
            <div className="mb-2 flex items-center gap-2 text-xs text-tertiary bg-tertiary/10 border border-tertiary/20 rounded-lg px-2.5 py-1.5 max-w-[240px]">
              <span className="truncate">{message.documentName}</span>
            </div>
          )}
          <div className="max-h-[min(60vh,420px)] overflow-y-auto scrollbar-hide">
            {message.text}
          </div>
        </div>

        {message.advisorMessage && (
          <div className="advisor-box rounded-xl px-3 py-2.5 text-xs max-w-full w-full">
            <div className="flex items-center gap-1.5 mb-1.5 text-tertiary font-semibold text-[11px]">
              <Sparkles className="w-3.5 h-3.5 shrink-0" />
              AI Recommendation
            </div>
            <p className="leading-relaxed text-on-secondary-container/90">{message.advisorMessage}</p>
          </div>
        )}

        {message.suggestions && message.suggestions.length > 0 && (
          <div className="flex flex-wrap gap-1.5 max-w-full">
            {message.suggestions.map((chip) => (
              <button
                key={chip}
                type="button"
                onClick={() => onSuggestionClick?.(chip)}
                className="suggestion-chip text-[11px] px-2.5 py-1 rounded-full cursor-pointer transition-all duration-150 focus-visible:ring-2 focus-visible:ring-primary/50"
              >
                {chip}
              </button>
            ))}
          </div>
        )}

        {message.handover?.enabled && message.handover.actions && (
          <div className="support-handover-card w-full rounded-xl border border-primary/25 bg-primary/5 px-3 py-3 space-y-2">
            {message.handover.message && (
              <p className="text-xs text-on-surface/90">{message.handover.message}</p>
            )}
            <div className="flex flex-wrap gap-2">
              {message.handover.actions.map((action) => {
                if (action.type === "request") {
                  return (
                    <button
                      key={action.label}
                      type="button"
                      onClick={() =>
                        onRaiseSupportRequest?.(message.handover?.reason || "general")
                      }
                      className="text-[11px] px-3 py-1.5 rounded-lg bg-surface-container-high border border-border-subtle hover:border-primary/40 transition-colors duration-150 cursor-pointer"
                    >
                      {action.label}
                    </button>
                  );
                }
                const href =
                  action.type === "call" && action.value
                    ? `tel:${action.value}`
                    : action.type === "whatsapp" && action.value
                      ? `https://wa.me/${action.value.replace(/\D/g, "")}`
                      : undefined;
                return (
                  <a
                    key={action.label}
                    href={href || "#"}
                    target={action.type === "whatsapp" ? "_blank" : undefined}
                    rel={action.type === "whatsapp" ? "noreferrer" : undefined}
                    className="text-[11px] px-3 py-1.5 rounded-lg bg-surface-container-high border border-border-subtle hover:border-primary/40 transition-colors duration-150"
                    onClick={!href ? (e) => e.preventDefault() : undefined}
                  >
                    {action.label}
                  </a>
                );
              })}
            </div>
          </div>
        )}

        {message.filters &&
          (message.filters.category || message.filters.city || message.filters.max_price) && (
            <div className="flex flex-wrap gap-1.5 items-center text-[10px]">
              <Info className="w-3 h-3 text-on-surface-variant shrink-0" />
              {message.filters.category && (
                <span className="filter-chip capitalize">{message.filters.category}</span>
              )}
              {message.filters.city && (
                <span className="filter-chip capitalize">{message.filters.city}</span>
              )}
              {message.filters.max_price != null && (
                <span className="filter-chip">≤ ₹{message.filters.max_price}</span>
              )}
            </div>
          )}
      </div>
    </div>
  );
}

export default memo(MessageBubble);
