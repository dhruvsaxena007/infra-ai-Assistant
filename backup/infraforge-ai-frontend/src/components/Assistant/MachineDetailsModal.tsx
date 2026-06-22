import React from "react";
import { Eye, MapPin, Star, User2, Wrench, Tag } from "lucide-react";
import type { Machine } from "../../types";
import { resolveMachineImageSrc } from "../../utils/machineImage";
import Modal from "./Modal";

interface Props {
  machine: Machine;
  onClose: () => void;
}

function Row({ label, value }: { label: string; value?: React.ReactNode }) {
  if (value == null || value === "") return null;
  return (
    <div className="flex justify-between gap-4 py-2 border-b border-border-subtle/40 last:border-0">
      <span className="text-on-surface-variant text-xs">{label}</span>
      <span className="text-on-surface text-xs font-medium text-right">{value}</span>
    </div>
  );
}

export default function MachineDetailsModal({ machine, onClose }: Props) {
  return (
    <Modal title="Machine details" icon={<Eye className="w-4 h-4 text-primary" />} onClose={onClose}>
      <div className="space-y-4">
        <div className="w-full h-48 rounded-xl overflow-hidden bg-surface-container-high border border-border-subtle">
          <img
            src={resolveMachineImageSrc(machine)}
            alt={machine.name}
            className="w-full h-full object-cover"
          />
        </div>
        <div>
          <h2 className="text-lg font-bold text-on-surface">{machine.name}</h2>
          <div className="flex items-center gap-3 mt-1 text-xs text-on-surface-variant flex-wrap">
            {machine.category && (
              <span className="flex items-center gap-1 capitalize">
                <Tag className="w-3.5 h-3.5" /> {machine.category}
              </span>
            )}
            {machine.city && (
              <span className="flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5" /> {machine.city}
              </span>
            )}
            {machine.rating != null && (
              <span className="flex items-center gap-1">
                <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" /> {machine.rating}
              </span>
            )}
          </div>
        </div>

        {machine.description && (
          <p className="text-sm text-on-surface-variant leading-relaxed">{machine.description}</p>
        )}

        <div className="bg-surface-container-high rounded-xl p-4 border border-border-subtle">
          <Row
            label="Price per day"
            value={machine.price_per_day != null ? `₹${machine.price_per_day.toLocaleString("en-IN")}` : undefined}
          />
          <Row label="Brand" value={machine.brand} />
          <Row label="Model" value={machine.model} />
          <Row
            label="Availability"
            value={machine.availability_status ? <span className="capitalize">{machine.availability_status}</span> : undefined}
          />
          <Row
            label="Owner"
            value={
              machine.owner_name ? (
                <span className="flex items-center gap-1 justify-end">
                  <User2 className="w-3.5 h-3.5" /> {machine.owner_name}
                </span>
              ) : undefined
            }
          />
          <Row label="Match score" value={machine.final_score} />
          <Row label="Machine ID" value={<span className="font-mono">{machine._id}</span>} />
        </div>

        <div className="flex items-center gap-2 text-[11px] text-on-surface-variant">
          <Wrench className="w-3.5 h-3.5" />
          Live data from the Infra AI-Assistant backend.
        </div>
      </div>
    </Modal>
  );
}
