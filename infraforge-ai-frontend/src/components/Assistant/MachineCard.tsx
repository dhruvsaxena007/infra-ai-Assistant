import React, { memo } from "react";
import {
  MapPin,
  Star,
  User2,
  BadgeCheck,
  Eye,
  GitCompareArrows,
  LineChart,
  Gauge,
  Layers,
  CheckCircle2,
  Tag,
  Calendar,
  Phone,
  Construction,
} from "lucide-react";
import type { Machine } from "../../types";
import { hasValidMachineId } from "../../utils/machineId";
import { listingBadgeMeta, availabilityBadgeMeta } from "../../utils/listingType";
import MachineImage from "./MachineImage";

interface Props {
  machine: Machine;
  selectedForCompare: boolean;
  selectedForChat?: boolean;
  index?: number;
  compact?: boolean;
  onViewDetails: (m: Machine) => void;
  onToggleCompare: (m: Machine) => void;
  onSelectMachine?: (m: Machine) => void;
  onPriceInsight: (m: Machine) => void;
  onDealScore: (m: Machine) => void;
  onSimilar: (m: Machine) => void;
  onContactOwner: (m: Machine) => void;
}

function availabilityStyle(status?: string) {
  return availabilityBadgeMeta(status).className;
}

function formatPrice(machine: Machine): { amount: string; suffix: string } {
  const listingType = (machine.listing_type || "rent").toLowerCase();
  if (listingType === "sell") {
    const price = machine.selling_price ?? machine.price_per_day;
    return {
      amount: price != null ? `₹${price.toLocaleString("en-IN")}` : "N/A",
      suffix: "sell price",
    };
  }
  const price = machine.price_per_day;
  const rentType = machine.rent_type || "day";
  return {
    amount: price != null ? `₹${price.toLocaleString("en-IN")}` : "N/A",
    suffix: `per ${rentType}`,
  };
}

function MachineCard({
  machine,
  selectedForCompare,
  selectedForChat = false,
  index = 0,
  compact = false,
  onViewDetails,
  onToggleCompare,
  onSelectMachine,
  onPriceInsight,
  onDealScore,
  onSimilar,
  onContactOwner,
}: Props) {
  const canRunInsights = hasValidMachineId(machine);
  const { amount, suffix } = formatPrice(machine);
  const listingBadge = listingBadgeMeta(machine.listing_type);
  const specs = machine.specifications || {};
  const categoryLabel = machine.category_display || machine.category;
  const animateEntry = index < 4;

  const btnBase =
    "flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg border text-[11px] font-medium cursor-pointer transition-all duration-150 focus-visible:ring-2 focus-visible:ring-primary/40";
  const btnGhost = `${btnBase} bg-surface-container-highest/60 border-border-subtle text-on-surface hover:border-primary/40 hover:-translate-y-0.5`;

  return (
    <article
      className={`machine-card premium-card rounded-2xl flex flex-col gap-2.5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-primary/5 ${
        compact ? "p-3" : "p-3.5"
      } ${selectedForCompare ? "ring-1 ring-primary/50 border-primary/40" : ""} ${
        selectedForChat ? "ring-2 ring-tertiary/60 border-tertiary/40" : ""
      } ${
        animateEntry ? "card-enter" : ""
      }`}
      style={animateEntry ? { animationDelay: `${index * 40}ms` } : undefined}
    >
      <div className="relative w-full aspect-[16/10] rounded-xl overflow-hidden bg-surface-container-highest border border-border-subtle group">
        <MachineImage machine={machine} />
        <div className="absolute inset-0 bg-gradient-to-t from-surface-container/90 via-surface-container/10 to-transparent pointer-events-none" />
        <span
          className={`absolute top-2 left-2 z-10 ${listingBadge.className}`}
        >
          {listingBadge.label}
        </span>
        {machine.availability_status && (
          <span
            className={`absolute top-2 right-2 z-10 capitalize ${availabilityStyle(
              machine.availability_status,
            )}`}
          >
            {machine.availability_status}
          </span>
        )}
      </div>

      <div className="min-w-0 space-y-1">
        <h4 className="font-semibold text-[13px] text-on-surface leading-snug line-clamp-2">
          {machine.name}
        </h4>
        <div className="flex items-center gap-1.5 flex-wrap">
          {categoryLabel && (
            <span className="text-[9px] font-mono uppercase tracking-wider text-primary">
              {categoryLabel}
            </span>
          )}
          {machine.brand && (
            <span className="text-[9px] text-on-surface-variant">· {machine.brand}</span>
          )}
          {machine.model && (
            <span className="text-[9px] text-on-surface-variant">· {machine.model}</span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2.5 text-[11px] text-on-surface-variant flex-wrap">
        {machine.city && (
          <span className="flex items-center gap-1">
            <MapPin className="w-3 h-3 text-primary/80 shrink-0" /> {machine.city}
          </span>
        )}
        <span className="flex items-center gap-1">
          <Star className="w-3 h-3 text-amber-400 fill-amber-400 shrink-0" />
          {machine.rating != null ? machine.rating : (
            <span className="text-on-surface-variant/70">Rating N/A</span>
          )}
        </span>
        {!compact && (machine.seller_name || machine.owner_name) && (
          <span className="flex items-center gap-1 truncate max-w-[120px]">
            <User2 className="w-3 h-3 shrink-0" /> {machine.seller_name || machine.owner_name}
          </span>
        )}
        {specs.condition && (
          <span className="flex items-center gap-1 capitalize">
            <Tag className="w-3 h-3 shrink-0" /> {String(specs.condition)}
          </span>
        )}
        {specs.manufacturing_year && (
          <span className="flex items-center gap-1">
            <Calendar className="w-3 h-3 shrink-0" /> {String(specs.manufacturing_year)}
          </span>
        )}
      </div>

      {machine.description && (
        <p className="text-[11px] text-on-surface-variant leading-relaxed line-clamp-2">
          {machine.description}
        </p>
      )}

      <div className="flex items-end justify-between gap-2 mt-auto">
        <div>
          <div className="text-base font-bold text-on-surface tracking-tight">{amount}</div>
          <div className="text-[9px] text-on-surface-variant">{suffix}</div>
          {machine.security_deposit != null && machine.listing_type === "rent" && (
            <div className="text-[9px] text-on-surface-variant">
              Deposit ₹{machine.security_deposit.toLocaleString("en-IN")}
            </div>
          )}
        </div>
        {machine.final_score != null && (
          <span className="flex items-center gap-1 text-[9px] font-mono px-1.5 py-0.5 rounded-md bg-primary-container/40 text-on-primary-container border border-primary/20">
            <BadgeCheck className="w-3 h-3" /> {machine.final_score}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-1.5 pt-0.5">
        <button type="button" onClick={() => onViewDetails(machine)} className={`${btnGhost} col-span-2`}>
          <Eye className="w-3.5 h-3.5" /> View details
        </button>
        {onSelectMachine && (
          <button
            type="button"
            onClick={() => onSelectMachine(machine)}
            className={
              selectedForChat
                ? `${btnBase} bg-tertiary/20 text-tertiary border-tertiary/40 col-span-2`
                : `${btnGhost} col-span-2`
            }
          >
            {selectedForChat ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Construction className="w-3.5 h-3.5" />}
            {selectedForChat ? "Selected for chat" : "Select for chat"}
          </button>
        )}
        <button
          type="button"
          onClick={() => onToggleCompare(machine)}
          className={
            selectedForCompare
              ? `${btnBase} bg-primary text-on-primary border-primary`
              : btnGhost
          }
        >
          {selectedForCompare ? <CheckCircle2 className="w-3.5 h-3.5" /> : <GitCompareArrows className="w-3.5 h-3.5" />}
          Compare
        </button>
        <button
          type="button"
          onClick={() => canRunInsights && onPriceInsight(machine)}
          disabled={!canRunInsights}
          className={`${btnGhost} disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0`}
        >
          <LineChart className="w-3.5 h-3.5" /> Price
        </button>
        <button
          type="button"
          onClick={() => canRunInsights && onDealScore(machine)}
          disabled={!canRunInsights}
          className={`${btnGhost} disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0`}
        >
          <Gauge className="w-3.5 h-3.5" /> Deal Score
        </button>
        <button
          type="button"
          onClick={() => canRunInsights && onSimilar(machine)}
          disabled={!canRunInsights}
          className={`${btnGhost} disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0`}
        >
          <Layers className="w-3.5 h-3.5" /> Similar
        </button>
        <button
          type="button"
          onClick={() => onContactOwner(machine)}
          className={`${btnBase} col-span-2 gradient-orange text-on-primary border-transparent font-semibold shadow-md shadow-primary/10 hover:opacity-95`}
        >
          <Phone className="w-3.5 h-3.5" /> Contact Owner
        </button>
      </div>
    </article>
  );
}

export default memo(MachineCard);
