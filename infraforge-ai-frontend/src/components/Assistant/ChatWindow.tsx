import React, { useEffect, useRef, useState } from "react";
import { Bot, Search, Mic, Camera, FileText } from "lucide-react";
import type { ChatMessage } from "../../types";
import MessageBubble from "./MessageBubble";
import LoadingIndicator from "./LoadingIndicator";

const INTRO_CHIPS = [
  "Search machine",
  "Upload image",
  "Voice search",
  "Ask recommendation",
];

const NEAR_BOTTOM_PX = 120;

function isNearBottom(el: HTMLElement): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
}

interface Props {
  messages: ChatMessage[];
  loading: boolean;
  loadingLabel?: string;
  isGenerating?: boolean;
  activeGenerationMessageId?: string | null;
  indicatorFading?: boolean;
  onSuggestionClick?: (text: string) => void;
  onRaiseSupportRequest?: (issueType?: string) => void;
}

export default function ChatWindow({
  messages,
  loading,
  loadingLabel,
  isGenerating = false,
  activeGenerationMessageId = null,
  indicatorFading = false,
  onSuggestionClick,
  onRaiseSupportRequest,
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const nearBottomRef = useRef(true);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      nearBottomRef.current = isNearBottom(el);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (messages.length === 0 && !loading && !isGenerating) return;
    if (!nearBottomRef.current) return;
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading, isGenerating]);

  return (
    <div className="chat-window flex-1 flex flex-col min-h-0 overflow-hidden">
      <div ref={containerRef} className="flex-1 overflow-y-auto overscroll-contain scrollbar-hide px-2 sm:px-3 py-2 space-y-4 min-h-0">
      {messages.length === 0 && !loading && (
        <div className="flex flex-col items-center justify-center text-center gap-4 min-h-[min(100%,320px)] py-10 sm:py-12 card-enter">
          <div className="w-14 h-14 rounded-2xl gradient-orange flex items-center justify-center shadow-lg shadow-primary/15">
            <Bot className="w-7 h-7 text-on-primary" />
          </div>
          <div className="space-y-2 max-w-sm">
            <p className="text-base font-semibold text-on-surface">
              Infra AI-Assistant for Marketplace
            </p>
            <p className="text-xs leading-relaxed text-on-surface-variant">
              Search heavy machinery in English, Hindi or Hinglish. Type, speak, or upload a photo.
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-2 max-w-md px-2">
            {INTRO_CHIPS.map((chip) => (
              <button
                key={chip}
                type="button"
                onClick={() => onSuggestionClick?.(chip)}
                className="suggestion-chip text-[11px] px-3 py-1.5 rounded-full flex items-center gap-1.5 transition-all duration-150 focus-visible:ring-2 focus-visible:ring-primary/50"
              >
                {chip === "Search machine" && <Search className="w-3 h-3" />}
                {chip === "Upload image" && <Camera className="w-3 h-3" />}
                {chip === "Voice search" && <Mic className="w-3 h-3" />}
                {chip === "Ask recommendation" && <FileText className="w-3 h-3" />}
                {chip}
              </button>
            ))}
          </div>
        </div>
      )}

      {messages.map((m) => (
        <MessageBubble
          key={m.id}
          message={m}
          indicatorFading={
            m.id === activeGenerationMessageId && indicatorFading
          }
          onSuggestionClick={onSuggestionClick}
          onRaiseSupportRequest={onRaiseSupportRequest}
        />
      ))}

      {loading && (
        <div className="flex gap-2.5 message-enter" aria-live="polite" aria-busy="true">
          <div className="relative w-8 h-8 flex-shrink-0">
            <div className="relative w-8 h-8 rounded-full gradient-orange text-on-primary flex items-center justify-center">
              <Bot className="w-4 h-4" />
            </div>
          </div>
          <div className="assistant-bubble rounded-2xl rounded-tl-sm px-3.5 py-3">
            <LoadingIndicator label={loadingLabel} />
          </div>
        </div>
      )}

      <div ref={endRef} className="h-px shrink-0" aria-hidden />
      </div>
    </div>
  );
}
