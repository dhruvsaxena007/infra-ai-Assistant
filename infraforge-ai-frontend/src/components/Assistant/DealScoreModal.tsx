import React, { useEffect, useState } from "react";
import { Gauge, Loader2 } from "lucide-react";
import type { DealScoreResult, Machine } from "../../types";
import { getDealScore, BackendUnreachableError } from "../../api/assistantApi";
import { getMachineId } from "../../utils/machineId";
import Modal from "./Modal";
import ErrorBanner from "./ErrorBanner";

interface Props {
  machine: Machine;
  onClose: () => void;
}

function scoreColor(score: number) {
  if (score >= 85) return "#34d399"; // emerald
  if (score >= 70) return "#a3e635"; // lime
  if (score >= 50) return "#fbbf24"; // amber
  return "#fb7185"; // rose
}

export default function DealScoreModal({ machine, onClose }: Props) {
  const [data, setData] = useState<DealScoreResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const mid = getMachineId(machine);
        if (!mid) {
          setError("Machine ID missing — cannot load deal score.");
          return;
        }
        const res = await getDealScore(mid);
        if (!active) return;
        if (res.success) setData(res.data);
        else setError(res.message || "Could not load deal score.");
      } catch (e) {
        if (!active) return;
        setError(e instanceof BackendUnreachableError ? e.message : "Failed to load deal score.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [machine.id, machine._id]);

  const score = data?.deal_score ?? null;
  const pct = score != null ? Math.max(0, Math.min(100, score)) : 0;

  return (
    <Modal title="Deal score" icon={<Gauge className="w-4 h-4 text-primary" />} onClose={onClose}>
      {loading ? (
        <div className="flex items-center gap-2 text-on-surface-variant text-sm py-6 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> Scoring deal…
        </div>
      ) : error ? (
        <ErrorBanner message={error} />
      ) : data ? (
        <div className="space-y-5 text-center">
          <h2 className="text-base font-bold text-on-surface">{data.machine_name}</h2>

          {score != null ? (
            <div className="flex justify-center">
              <div
                className="relative w-36 h-36 rounded-full flex items-center justify-center"
                style={{
                  background: `conic-gradient(${scoreColor(score)} ${pct * 3.6}deg, rgba(255,255,255,0.06) 0deg)`,
                }}
              >
                <div className="absolute inset-3 rounded-full bg-surface-container flex flex-col items-center justify-center">
                  <span className="text-3xl font-bold text-on-surface">{score}</span>
                  <span className="text-[10px] text-on-surface-variant">/ 100</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-sm text-on-surface-variant py-4">No score available.</div>
          )}

          {data.deal_label && (
            <div
              className="inline-block px-4 py-1.5 rounded-full text-sm font-semibold border"
              style={{ color: score != null ? scoreColor(score) : undefined, borderColor: "rgba(255,255,255,0.1)" }}
            >
              {data.deal_label}
            </div>
          )}

          {data.reason && (
            <p className="text-xs text-on-surface-variant leading-relaxed">{data.reason}</p>
          )}
        </div>
      ) : null}
    </Modal>
  );
}
