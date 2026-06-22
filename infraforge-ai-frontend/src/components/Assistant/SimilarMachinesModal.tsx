import React, { useEffect, useState } from "react";
import { Layers, Loader2, MapPin, Star } from "lucide-react";
import type { Machine } from "../../types";
import { getRecommendations, BackendUnreachableError } from "../../api/assistantApi";
import { getMachineId } from "../../utils/machineId";
import Modal from "./Modal";
import ErrorBanner from "./ErrorBanner";

interface Props {
  machine: Machine;
  onClose: () => void;
  onViewDetails: (m: Machine) => void;
}

export default function SimilarMachinesModal({ machine, onClose, onViewDetails }: Props) {
  const [items, setItems] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const mid = getMachineId(machine);
        if (!mid) {
          setError("Machine ID missing — cannot load similar machines.");
          return;
        }
        const res = await getRecommendations(mid);
        if (!active) return;
        if (res.success) setItems(res.data.recommendations || []);
        else setError(res.message || "Could not load recommendations.");
      } catch (e) {
        if (!active) return;
        setError(e instanceof BackendUnreachableError ? e.message : "Failed to load recommendations.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [machine.id, machine._id]);

  return (
    <Modal
      title="Similar machines"
      icon={<Layers className="w-4 h-4 text-primary" />}
      onClose={onClose}
      widthClass="max-w-xl"
    >
      <p className="text-xs text-on-surface-variant mb-4">
        Recommendations similar to <span className="text-on-surface font-medium">{machine.name}</span>
      </p>

      {loading ? (
        <div className="flex items-center gap-2 text-on-surface-variant text-sm py-6 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> Finding similar machines…
        </div>
      ) : error ? (
        <ErrorBanner message={error} />
      ) : items.length === 0 ? (
        <div className="text-sm text-on-surface-variant text-center py-6">
          No similar machines found.
        </div>
      ) : (
        <div className="space-y-2.5">
          {items.map((m) => (
            <button
              key={m._id}
              onClick={() => onViewDetails(m)}
              className="w-full text-left bg-surface-container-high border border-border-subtle rounded-xl p-3 hover:border-primary/40 cursor-pointer transition-colors"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium text-sm text-on-surface truncate">{m.name}</span>
                {m.price_per_day != null && (
                  <span className="text-sm font-bold text-on-surface whitespace-nowrap">
                    ₹{m.price_per_day.toLocaleString("en-IN")}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-on-surface-variant flex-wrap">
                {m.category && <span className="capitalize text-primary">{m.category}</span>}
                {m.city && (
                  <span className="flex items-center gap-1">
                    <MapPin className="w-3 h-3" /> {m.city}
                  </span>
                )}
                {m.rating != null && (
                  <span className="flex items-center gap-1">
                    <Star className="w-3 h-3 text-amber-400 fill-amber-400" /> {m.rating}
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </Modal>
  );
}
