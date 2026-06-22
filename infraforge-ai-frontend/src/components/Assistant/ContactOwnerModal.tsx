import React from "react";
import { Phone, MessageCircle, User2 } from "lucide-react";
import type { Machine } from "../../types";
import Modal from "./Modal";

interface Props {
  machine: Machine;
  onClose: () => void;
}

export default function ContactOwnerModal({ machine, onClose }: Props) {
  const owner = machine.owner_name || machine.seller_name || "Owner";
  const phone =
    machine.contact_number || machine.seller_phone || machine.mobile_number || null;
  const whatsapp = machine.whatsapp_number || phone;

  return (
    <Modal title="Contact owner" icon={<User2 className="w-4 h-4 text-primary" />} onClose={onClose}>
      <div className="space-y-4 text-sm text-on-surface">
        <div>
          <div className="text-xs text-on-surface-variant mb-1">Listing</div>
          <div className="font-medium">{machine.name}</div>
        </div>
        <div>
          <div className="text-xs text-on-surface-variant mb-1">Owner / seller</div>
          <div>{owner}</div>
        </div>

        {phone ? (
          <div className="flex flex-col gap-2">
            <a
              href={`tel:${phone}`}
              className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-surface-container-high border border-border-subtle hover:border-primary/40"
            >
              <Phone className="w-4 h-4" /> Call {phone}
            </a>
            {whatsapp && (
              <a
                href={`https://wa.me/${whatsapp.replace(/\D/g, "")}`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-200 hover:border-emerald-400/50"
              >
                <MessageCircle className="w-4 h-4" /> WhatsApp
              </a>
            )}
          </div>
        ) : (
          <p className="text-on-surface-variant leading-relaxed">
            Contact details are not public. You can raise a request and our team will contact you.
          </p>
        )}

        <button
          type="button"
          onClick={onClose}
          className="w-full px-4 py-2.5 rounded-xl gradient-orange text-white text-sm font-medium"
        >
          Raise request
        </button>
      </div>
    </Modal>
  );
}
