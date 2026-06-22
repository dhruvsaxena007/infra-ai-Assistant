import React, { useMemo } from "react";
import { PackageSearch, Loader2 } from "lucide-react";
import type { Machine } from "../../types";
import type { ListingFilter } from "../../utils/listingType";
import { getMachineId } from "../../utils/machineId";
import MachineCard from "./MachineCard";
import MachineCardSkeleton from "./MachineCardSkeleton";

interface Props {
  machines: Machine[];
  title?: string;
  loading?: boolean;
  compareSelection: string[];
  selectedMachineId?: string | null;
  hideHeader?: boolean;
  compact?: boolean;
  allMachinesCount?: number;
  listingFilter?: ListingFilter;
  listingCounts?: { rent: number; sell: number; all: number };
  onListingFilterChange?: (filter: ListingFilter) => void;
  onViewDetails: (m: Machine) => void;
  onToggleCompare: (m: Machine) => void;
  onSelectMachine?: (m: Machine) => void;
  onPriceInsight: (m: Machine) => void;
  onDealScore: (m: Machine) => void;
  onSimilar: (m: Machine) => void;
  onContactOwner: (m: Machine) => void;
}

const SKELETON_COUNT = 4;

export default function MachineResults({
  machines,
  title = "Machine Results",
  loading = false,
  compareSelection,
  selectedMachineId = null,
  hideHeader = false,
  compact = false,
  allMachinesCount,
  listingFilter = "both",
  listingCounts,
  onListingFilterChange,
  onViewDetails,
  onToggleCompare,
  onSelectMachine,
  onPriceInsight,
  onDealScore,
  onSimilar,
  onContactOwner,
}: Props) {
  const list = useMemo(() => (Array.isArray(machines) ? machines : []), [machines]);
  const total = allMachinesCount ?? list.length;
  const counts = listingCounts ?? { rent: 0, sell: 0, all: total };
  const showListingFilters =
    onListingFilterChange && total > 0 && (counts.rent > 0 || counts.sell > 0);

  const listingFilterBar = showListingFilters && (
    <div className="flex flex-wrap gap-1.5 pt-2">
      {(
        [
          ["both", `All (${counts.all})`],
          ["rent", `Rent (${counts.rent})`],
          ["sell", `Buy (${counts.sell})`],
        ] as const
      ).map(([key, label]) => (
        <button
          key={key}
          type="button"
          onClick={() => onListingFilterChange(key)}
          className={`px-2.5 py-1 rounded-full text-[10px] font-semibold border transition-colors ${
            listingFilter === key
              ? "bg-primary/20 text-primary border-primary/40"
              : "bg-surface-container-high text-on-surface-variant border-border-subtle hover:border-primary/30"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );

  const header = !hideHeader && (
    <div className="results-header sticky top-0 z-10 -mx-1 px-1 pb-3 pt-0.5 mb-1 bg-surface-container/95 backdrop-blur-md border-b border-border-subtle/60">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-on-surface">
          {title}
        </h3>
        <div className="flex items-center gap-2">
          {loading && <Loader2 className="w-3.5 h-3.5 text-primary animate-spin" />}
          <span className="count-badge">{loading ? "…" : list.length}</span>
        </div>
      </div>
      {listingFilterBar}
    </div>
  );

  if (loading && list.length === 0) {
    return (
      <div className="flex flex-col h-full min-h-0">
        {header}
        <div className="machine-grid flex-1">
          {Array.from({ length: SKELETON_COUNT }).map((_, i) => (
            <MachineCardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (list.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center text-center gap-3 py-12 px-4 text-on-surface-variant card-enter min-h-[200px]">
        <div className="w-12 h-12 rounded-2xl gradient-orange flex items-center justify-center shadow-lg shadow-primary/10">
          <PackageSearch className="w-6 h-6 text-on-primary" />
        </div>
        <p className="text-sm font-medium text-on-surface">No machines yet</p>
        <p className="text-xs max-w-[260px] leading-relaxed">
          Try{" "}
          <span className="text-primary font-medium">"excavator in jaipur under 8000"</span>{" "}
          to see live listings here.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-0">
      {header}
      <div className="machine-grid">
        {list.map((m, index) => {
          const mid = getMachineId(m) || m.name;
          return (
            <MachineCard
              key={mid}
              machine={m}
              index={index}
              compact={compact}
              selectedForCompare={compareSelection.includes(mid)}
              selectedForChat={selectedMachineId === mid}
              onViewDetails={onViewDetails}
              onToggleCompare={onToggleCompare}
              onSelectMachine={onSelectMachine}
              onPriceInsight={onPriceInsight}
              onDealScore={onDealScore}
              onSimilar={onSimilar}
              onContactOwner={onContactOwner}
            />
          );
        })}
      </div>
    </div>
  );
}
