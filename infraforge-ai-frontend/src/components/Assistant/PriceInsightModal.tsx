import React, { useEffect, useState } from "react";
import { LineChart, Loader2 } from "lucide-react";
import type { Machine, PriceInsightResult } from "../../types";
import { getPriceInsight, BackendUnreachableError } from "../../api/assistantApi";
import { getMachineId } from "../../utils/machineId";
import Modal from "./Modal";
import ErrorBanner from "./ErrorBanner";

interface Props {
  machine: Machine;
  onClose: () => void;
}

function statusStyle(status?: string) {
  const s = (status || "").toLowerCase();
  if (s.includes("below")) return "text-emerald-300";
  if (s.includes("above")) return "text-rose-300";
  if (s.includes("fair")) return "text-amber-300";
  return "text-on-surface-variant";
}

export default function PriceInsightModal({ machine, onClose }: Props) {
  const [data, setData] = useState<PriceInsightResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const mid = getMachineId(machine);
        if (!mid) {
          setError("Machine ID missing — cannot load price insight.");
          return;
        }
        const res = await getPriceInsight(mid);
        if (!active) return;
        if (res.success) setData(res.data);
        else setError(res.message || "Could not load price insight.");
      } catch (e) {
        if (!active) return;
        setError(e instanceof BackendUnreachableError ? e.message : "Failed to load price insight.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [machine.id, machine._id]);

  return (
    <Modal title="Price insight" icon={<LineChart className="w-4 h-4 text-primary" />} onClose={onClose}>
      {loading ? (
        <div className="flex items-center gap-2 text-on-surface-variant text-sm py-6 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> Analyzing market…
        </div>
      ) : error ? (
        <ErrorBanner message={error} />
      ) : data ? (
        <div className="space-y-4">
          <h2 className="text-base font-bold text-on-surface">{data.machine_name}</h2>

          <div className={`text-center py-3 rounded-xl bg-surface-container-high border border-border-subtle ${statusStyle(data.price_status)}`}>
            <div className="text-lg font-bold">{data.price_status}</div>
            {data.percentage_difference != null && (
              <div className="text-xs mt-0.5">
                {data.percentage_difference > 0 ? "+" : ""}
                {data.percentage_difference}% vs market avg
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Stat label="Current price" value={data.current_price != null ? `₹${data.current_price.toLocaleString("en-IN")}` : "—"} />
            <Stat label="Market avg" value={data.average_market_price != null ? `₹${data.average_market_price.toLocaleString("en-IN")}` : "—"} />
            {data.price_difference != null && (
              <Stat label="Difference" value={`₹${data.price_difference.toLocaleString("en-IN")}`} />
            )}
            {data.similar_machine_count != null && (
              <Stat label="Compared with" value={`${data.similar_machine_count} machines`} />
            )}
          </div>

          {data.recommendation && (
            <p className="text-sm text-on-surface-variant leading-relaxed bg-surface-container-high border border-border-subtle rounded-xl p-3">
              {data.recommendation}
            </p>
          )}
        </div>
      ) : null}
    </Modal>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="bg-surface-container-high border border-border-subtle rounded-xl p-3">
      <div className="text-[10px] uppercase tracking-wider text-on-surface-variant">{label}</div>
      <div className="text-sm font-semibold text-on-surface mt-0.5">{value}</div>
    </div>
  );
}
