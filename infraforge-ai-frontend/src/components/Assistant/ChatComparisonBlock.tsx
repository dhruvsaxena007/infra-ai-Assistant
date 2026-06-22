import React from "react";
import { Star, Trophy, Wallet } from "lucide-react";
import type { CompareResult } from "../../types";

interface Props {
  data: CompareResult;
}

function VerdictRow({
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
      className={`flex items-center justify-between gap-3 rounded-lg px-3 py-2 border text-xs ${
        highlight ? "border-primary/40 bg-primary-container/15" : "border-border-subtle bg-surface-container-high"
      }`}
    >
      <span className="flex items-center gap-1.5 text-on-surface-variant">{icon}{label}</span>
      <span className="font-semibold text-on-surface text-right">{value}</span>
    </div>
  );
}

export default function ChatComparisonBlock({ data }: Props) {
  const rows = data.comparison_rows || [];
  const m1 = data.machine_1;
  const m2 = data.machine_2;
  const label1 = m1?.name || m1?.brand || "Option A";
  const label2 = m2?.name || m2?.brand || "Option B";
  const overall = data.overall_recommendation;
  const summary = data.llm_summary || data.summary_draft;

  if (!m1 || !m2) return null;

  return (
    <div className="space-y-3 mt-2 w-full">
      {summary && (
        <div className="rounded-xl border border-primary/25 bg-primary-container/10 px-3 py-2.5 text-xs text-on-surface leading-relaxed">
          {summary}
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-border-subtle">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-container-high text-on-surface-variant">
                <th className="text-left px-2.5 py-1.5 font-medium">Spec</th>
                <th className="text-left px-2.5 py-1.5 font-medium">{label1}</th>
                <th className="text-left px-2.5 py-1.5 font-medium">{label2}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className="border-b border-border-subtle/60 last:border-0">
                  <td className="px-2.5 py-1.5 text-on-surface-variant">{row.label}</td>
                  <td
                    className={`px-2.5 py-1.5 ${row.winner === "a" ? "text-primary font-semibold" : "text-on-surface"}`}
                  >
                    {row.a}
                  </td>
                  <td
                    className={`px-2.5 py-1.5 ${row.winner === "b" ? "text-primary font-semibold" : "text-on-surface"}`}
                  >
                    {row.b}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="space-y-1.5">
        {data.better_for_budget && (
          <VerdictRow
            icon={<Wallet className="w-3.5 h-3.5 text-emerald-300" />}
            label="Better for budget"
            value={data.better_for_budget}
          />
        )}
        {data.better_rating && (
          <VerdictRow
            icon={<Star className="w-3.5 h-3.5 text-amber-300" />}
            label="Better rating"
            value={data.better_rating}
          />
        )}
        {data.value_for_money && (
          <VerdictRow
            icon={<Wallet className="w-3.5 h-3.5 text-sky-300" />}
            label="Value for money"
            value={data.value_for_money}
          />
        )}
        {overall && (
          <VerdictRow
            icon={<Trophy className="w-3.5 h-3.5 text-primary" />}
            label="Overall pick"
            value={overall}
            highlight
          />
        )}
      </div>
    </div>
  );
}
