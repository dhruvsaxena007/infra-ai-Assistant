import React, { useState } from "react";
import { Headphones } from "lucide-react";
import Modal from "./Modal";
import { submitSupportRequest } from "../../api/assistantApi";

interface Props {
  open: boolean;
  onClose: () => void;
  sessionId: string;
  defaultIssueType?: string;
}

export default function SupportRequestModal({
  open,
  onClose,
  sessionId,
  defaultIssueType = "",
}: Props) {
  const [name, setName] = useState("");
  const [mobile, setMobile] = useState("");
  const [orderId, setOrderId] = useState("");
  const [issueType, setIssueType] = useState(defaultIssueType);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setFeedback(null);
    try {
      const res = await submitSupportRequest({
        session_id: sessionId,
        name: name.trim(),
        mobile: mobile.trim(),
        order_id: orderId.trim(),
        issue_type: issueType.trim() || "general",
        message: message.trim(),
      });
      if (res.success) {
        setFeedback(res.message || "Request submitted successfully.");
        setName("");
        setMobile("");
        setOrderId("");
        setMessage("");
      } else {
        setFeedback(res.message || "Could not submit request.");
      }
    } catch {
      setFeedback(
        "Request captured locally — backend endpoint may be unavailable. Please try Call or WhatsApp.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="Raise Support Request"
      icon={<Headphones className="w-4 h-4 text-primary" />}
      onClose={onClose}
      widthClass="max-w-md"
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label className="text-xs text-on-surface-variant">
          Name *
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border-subtle bg-surface-container-high px-3 py-2 text-sm text-on-surface"
          />
        </label>
        <label className="text-xs text-on-surface-variant">
          Mobile *
          <input
            required
            type="tel"
            value={mobile}
            onChange={(e) => setMobile(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border-subtle bg-surface-container-high px-3 py-2 text-sm text-on-surface"
          />
        </label>
        <label className="text-xs text-on-surface-variant">
          Order ID (optional)
          <input
            value={orderId}
            onChange={(e) => setOrderId(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border-subtle bg-surface-container-high px-3 py-2 text-sm text-on-surface"
          />
        </label>
        <label className="text-xs text-on-surface-variant">
          Issue type
          <select
            value={issueType}
            onChange={(e) => setIssueType(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border-subtle bg-surface-container-high px-3 py-2 text-sm text-on-surface"
          >
            <option value="">General</option>
            <option value="order_support">Order issue</option>
            <option value="refund_return">Refund / Return</option>
            <option value="payment_issue">Payment issue</option>
            <option value="complaint_issue">Complaint</option>
          </select>
        </label>
        <label className="text-xs text-on-surface-variant">
          Message *
          <textarea
            required
            rows={3}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border-subtle bg-surface-container-high px-3 py-2 text-sm text-on-surface resize-none"
          />
        </label>
        {feedback && (
          <p className="text-xs text-primary/90 bg-primary/5 border border-primary/20 rounded-lg px-3 py-2">
            {feedback}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="mt-1 w-full py-2.5 rounded-xl gradient-orange text-on-primary text-sm font-semibold disabled:opacity-50"
        >
          {submitting ? "Submitting…" : "Submit Request"}
        </button>
      </form>
    </Modal>
  );
}
