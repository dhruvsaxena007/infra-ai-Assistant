import React, { useEffect } from "react";
import { X, PackageSearch } from "lucide-react";
import type { Machine } from "../../types";
import MachineResults from "./MachineResults";

interface Props {
  open: boolean;
  onClose: () => void;
  machines: Machine[];
  loading?: boolean;
  compareSelection: string[];
  onViewDetails: (m: Machine) => void;
  onToggleCompare: (m: Machine) => void;
  onPriceInsight: (m: Machine) => void;
  onDealScore: (m: Machine) => void;
  onSimilar: (m: Machine) => void;
  onContactOwner: (m: Machine) => void;
}

/** Mobile bottom-sheet for machine results. */
export default function MachineDrawer({
  open,
  onClose,
  machines,
  loading,
  compareSelection,
  onViewDetails,
  onToggleCompare,
  onPriceInsight,
  onDealScore,
  onSimilar,
  onContactOwner,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="md:hidden fixed inset-0 z-[80] flex flex-col justify-end" role="dialog" aria-modal="true" aria-label="Machine results">
      <button
        type="button"
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-label="Close machine results"
      />
      <div className="relative drawer-panel flex flex-col max-h-[88vh] rounded-t-2xl glass-panel border-t border-border-subtle shadow-2xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle flex-shrink-0">
          <div className="flex items-center gap-2">
            <PackageSearch className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold text-on-surface">Machine Results</span>
            <span className="count-badge">{machines.length}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-9 h-9 flex items-center justify-center rounded-lg bg-surface-container-high text-on-surface-variant hover:text-on-surface transition-colors focus-visible:ring-2 focus-visible:ring-primary/50"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-hide px-4 py-4 min-h-0">
          <MachineResults
            machines={machines}
            loading={loading}
            compareSelection={compareSelection}
            hideHeader
            compact
            onViewDetails={onViewDetails}
            onToggleCompare={onToggleCompare}
            onPriceInsight={onPriceInsight}
            onDealScore={onDealScore}
            onSimilar={onSimilar}
            onContactOwner={onContactOwner}
          />
        </div>
      </div>
    </div>
  );
}
