import React, { useEffect, useState } from "react";
import { GitCompareArrows, Loader2, Trophy, Wallet, Star } from "lucide-react";
import type { CompareResult, Machine } from "../../types";
import { compareMachines, BackendUnreachableError } from "../../api/assistantApi";
import Modal from "./Modal";
import ErrorBanner from "./ErrorBanner";

interface Props {
  machineA: Machine;
  machineB: Machine;
  onClose: () => void;
}

function MachineColumn({ machine, winner }: { machine: Machine; winner: boolean }) {
  return (
    <div
      className={`flex-1 rounded-xl border p-4 space-y-2 ${
        winner ? "border-primary ring-1 ring-primary/40 bg-primary-container/20" : "border-border-subtle bg-surface-container-high"
      }`}
    >
      <div className="flex items-center gap-1.5">
        {winner && <Trophy className="w-3.5 h-3.5 text-primary" />}
        <h4 className="font-semibold text-sm text-on-surface leading-snug">{machine.name}</h4>
      </div>
      <div className="text-xs text-on-surface-variant capitalize">{machine.category}</div>
      <div className="text-xs text-on-surface-variant">{machine.city}</div>
      <div className="text-lg font-bold text-on-surface">
        {machine.price_per_day != null ? `₹${machine.price_per_day.toLocaleString("en-IN")}` : "—"}
        <span className="text-[10px] font-normal text-on-surface-variant"> /day</span>
      </div>
      <div className="flex items-center gap-1 text-xs text-on-surface-variant">
        <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" /> {machine.rating ?? "—"}
      </div>
    </div>
  );
}

export default function ComparePanel({ machineA, machineB, onClose }: Props) {
  const [data, setData] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await compareMachines(machineA._id, machineB._id);
        if (!active) return;
        if (res.success) setData(res.data);
        else setError(res.message || "Could not compare machines.");
      } catch (e) {
        if (!active) return;
        setError(e instanceof BackendUnreachableError ? e.message : "Failed to compare machines.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [machineA._id, machineB._id]);

  const overall = data?.overall_recommendation;

  return (
    <Modal
      title="Compare machines"
      icon={<GitCompareArrows className="w-4 h-4 text-primary" />}
      onClose={onClose}
      widthClass="max-w-2xl"
    >
      {loading ? (
        <div className="flex items-center gap-2 text-on-surface-variant text-sm py-6 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> Comparing…
        </div>
      ) : error ? (
        <ErrorBanner message={error} />
      ) : data ? (
        <div className="space-y-4">
          <div className="flex gap-3 flex-col sm:flex-row">
            <MachineColumn machine={data.machine_1} winner={overall === data.machine_1.name} />
            <MachineColumn machine={data.machine_2} winner={overall === data.machine_2.name} />
          </div>

          <div className="space-y-2">
            <Verdict
              icon={<Wallet className="w-4 h-4 text-emerald-300" />}
              label="Better for budget"
              value={data.better_for_budget}
            />
            <Verdict
              icon={<Star className="w-4 h-4 text-amber-300" />}
              label="Better rating"
              value={data.better_rating}
            />
            <Verdict
              icon={<Trophy className="w-4 h-4 text-primary" />}
              label="Overall recommendation"
              value={data.overall_recommendation}
              highlight
            />
          </div>
        </div>
      ) : null}
    </Modal>
  );
}

function Verdict({
  icon,
  label,
  value,
  highlight,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-xl px-4 py-3 border ${
        highlight ? "border-primary/40 bg-primary-container/20" : "border-border-subtle bg-surface-container-high"
      }`}
    >
      <span className="flex items-center gap-2 text-xs text-on-surface-variant">
        {icon}
        {label}
      </span>
      <span className="text-sm font-semibold text-on-surface text-right">{value}</span>
    </div>
  );
}
