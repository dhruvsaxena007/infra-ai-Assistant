export type ListingType = "rent" | "sell";
export type ListingFilter = ListingType | "both";

export function normalizeListingType(value?: string | null): ListingType {
  const t = (value || "rent").toLowerCase();
  if (t === "sell" || t === "buy" || t === "purchase") return "sell";
  return "rent";
}

export function listingBadgeMeta(value?: string | null): {
  label: string;
  className: string;
} {
  const type = normalizeListingType(value);
  if (type === "sell") {
    return {
      label: "Buy",
      className: "listing-badge listing-badge-buy",
    };
  }
  return {
    label: "Rent",
    className: "listing-badge listing-badge-rent",
  };
}

export function availabilityBadgeMeta(status?: string | null): {
  label: string;
  className: string;
} {
  const s = (status || "").toLowerCase();
  if (s === "available") {
    return { label: "Available", className: "listing-badge listing-badge-available" };
  }
  if (s === "rented") {
    return { label: "Rented", className: "listing-badge listing-badge-rented" };
  }
  if (s === "pending") {
    return { label: "Pending", className: "listing-badge listing-badge-pending" };
  }
  return {
    label: status || "Unknown",
    className: "listing-badge listing-badge-neutral",
  };
}

export function filterMachinesByListing<T extends { listing_type?: string }>(
  machines: T[],
  filter: ListingFilter,
): T[] {
  if (filter === "both") return machines;
  return machines.filter((m) => normalizeListingType(m.listing_type) === filter);
}

export function listingFilterCounts(machines: { listing_type?: string }[]) {
  let rent = 0;
  let sell = 0;
  for (const m of machines) {
    if (normalizeListingType(m.listing_type) === "sell") sell += 1;
    else rent += 1;
  }
  return { rent, sell, all: machines.length };
}
