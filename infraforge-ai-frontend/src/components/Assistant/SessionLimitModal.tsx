import React from "react";
import { ImageIcon, Mic } from "lucide-react";
import Modal from "./Modal";

export type SessionLimitType = "image_search" | "voice_message";

interface Props {
  open: boolean;
  onClose: () => void;
  limitType: SessionLimitType;
  used: number;
  limit: number;
  onNewChat?: () => void;
}

export default function SessionLimitModal({
  open,
  onClose,
  limitType,
  used,
  limit,
  onNewChat,
}: Props) {
  if (!open) return null;

  const isImage = limitType === "image_search";
  const title = isImage ? "Image search limit reached" : "Voice message limit reached";
  const icon = isImage ? (
    <ImageIcon className="w-4 h-4 text-primary" />
  ) : (
    <Mic className="w-4 h-4 text-primary" />
  );
  const featureLabel = isImage ? "image searches" : "voice messages";

  return (
    <Modal title={title} icon={icon} onClose={onClose} widthClass="max-w-md">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-on-surface-variant leading-relaxed">
          You&apos;ve used {used} of {limit} {featureLabel} in this chat session.
          To upload more, start a new chat — that resets your session limits.
        </p>
        <div className="flex flex-col sm:flex-row gap-2">
          {onNewChat && (
            <button
              type="button"
              onClick={() => {
                onNewChat();
                onClose();
              }}
              className="flex-1 py-2.5 rounded-xl gradient-orange text-on-primary text-sm font-semibold"
            >
              New chat
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-2.5 rounded-xl border border-border-subtle bg-surface-container-high text-on-surface text-sm font-medium"
          >
            Got it
          </button>
        </div>
      </div>
    </Modal>
  );
}
