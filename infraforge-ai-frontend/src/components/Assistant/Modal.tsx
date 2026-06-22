import React from "react";
import { X } from "lucide-react";

interface Props {
  title: string;
  icon?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  widthClass?: string;
}

/** Generic centered modal/side panel shell with a dark backdrop. */
export default function Modal({ title, icon, onClose, children, widthClass = "max-w-lg" }: Props) {
  return (
    <div
      className="fixed inset-0 bg-background/85 backdrop-blur-md flex items-center justify-center z-[120] p-4"
      onClick={onClose}
    >
      <div
        className={`bg-surface-container border border-border-subtle rounded-2xl w-full ${widthClass} max-h-[85vh] overflow-y-auto scrollbar-hide message-enter shadow-2xl`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-surface-container/95 backdrop-blur-sm flex items-center justify-between px-5 py-4 border-b border-border-subtle">
          <div className="flex items-center gap-2 text-on-surface">
            {icon}
            <h3 className="font-semibold text-sm">{title}</h3>
          </div>
          <button
            onClick={onClose}
            className="text-on-surface-variant hover:text-on-surface cursor-pointer"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
