import React from "react";

export default function MachineCardSkeleton() {
  return (
    <div className="premium-card rounded-2xl p-4 flex flex-col gap-3 animate-pulse">
      <div className="w-full aspect-[16/10] rounded-xl bg-surface-container-highest/80" />
      <div className="h-4 w-3/4 rounded-md bg-surface-container-highest/80" />
      <div className="h-3 w-1/2 rounded-md bg-surface-container-highest/60" />
      <div className="flex gap-2">
        <div className="h-3 w-16 rounded-md bg-surface-container-highest/60" />
        <div className="h-3 w-12 rounded-md bg-surface-container-highest/60" />
      </div>
      <div className="h-5 w-24 rounded-md bg-surface-container-highest/80 mt-1" />
      <div className="grid grid-cols-2 gap-1.5 pt-1">
        <div className="col-span-2 h-8 rounded-lg bg-surface-container-highest/60" />
        <div className="h-8 rounded-lg bg-surface-container-highest/50" />
        <div className="h-8 rounded-lg bg-surface-container-highest/50" />
      </div>
    </div>
  );
}
