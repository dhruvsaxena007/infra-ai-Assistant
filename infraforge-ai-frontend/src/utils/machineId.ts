import type { Machine } from "../types";

/** Stable machine id for API calls (ObjectId or seed_* string). */
export function getMachineId(machine: Machine | null | undefined): string | null {
  if (!machine) return null;
  const id = machine.id || machine._id;
  return id != null && String(id).trim() ? String(id) : null;
}

export function hasValidMachineId(machine: Machine | null | undefined): boolean {
  return getMachineId(machine) != null;
}
