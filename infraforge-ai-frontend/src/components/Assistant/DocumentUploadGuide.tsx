import React from "react";
import { FileText, CheckCircle2 } from "lucide-react";
import Modal from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
  onContinue: () => void;
}

/**
 * Explains machine-document upload before opening the file picker.
 */
export default function DocumentUploadGuide({ open, onClose, onContinue }: Props) {
  if (!open) return null;

  const bullets = [
    "Answer questions about the machine",
    "Summarize manuals or brochures",
    "Explain specifications and features",
    "Clarify technical details from the document",
  ];

  return (
    <Modal
      title="Machine document upload"
      icon={<FileText className="w-4 h-4 text-tertiary" />}
      onClose={onClose}
      widthClass="max-w-md"
    >
      <p className="text-sm text-on-surface-variant leading-relaxed">
        Use this for <span className="text-on-surface font-medium">machine-related documents</span>{" "}
        such as manuals, brochures, specifications, and technical PDFs.
      </p>

      <ul className="mt-4 space-y-2">
        {bullets.map((item) => (
          <li key={item} className="flex items-start gap-2 text-sm text-on-surface-variant">
            <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
            <span>{item}</span>
          </li>
        ))}
      </ul>

      <p className="mt-4 text-xs text-on-surface-variant/80 leading-relaxed rounded-lg border border-border-subtle/80 bg-surface-container-high/60 px-3 py-2.5">
        Please avoid unrelated files (personal photos, random PDFs, or non-machine content).
        Irrelevant uploads waste time and reduce answer quality.
      </p>

      <div className="mt-5 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="h-10 px-4 rounded-xl border border-border-subtle text-sm text-on-surface-variant hover:text-on-surface hover:border-primary/30 transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onContinue}
          className="h-10 px-4 rounded-xl gradient-orange text-on-primary text-sm font-medium active:scale-[0.98] transition-transform"
        >
          Choose document
        </button>
      </div>
    </Modal>
  );
}
