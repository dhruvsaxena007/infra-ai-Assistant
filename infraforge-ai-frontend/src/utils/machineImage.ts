/** Category fallback images when a remote listing photo fails or looks irrelevant. */

const SUSPICIOUS_FRAGMENTS = [
  "screenshot",
  "_serial.",
  "serial.jpg",
  "_engine.",
  "engine.jpg",
  "eicher-pro",
  "pexels-photo-276024",
  "pexels-photo-16105409",
  "pexels-photo-1090638",
  "pexels-photo-276724",
  "pexels-photo-256424",
  "unsplash.com/photo",
  "book",
  "mountain",
  "home-decor",
  "placeholder.com",
];

const CATEGORY_SLUGS: Record<string, string> = {
  excavator: "excavator",
  "backhoe loader": "backhoe-loader",
  crane: "crane",
  "hydra crane": "crane",
  "road roller": "road-roller",
  "dump truck": "dump-truck",
  "concrete mixer": "concrete-mixer",
  "mobile crusher": "default-machine",
  "motor grader": "motor-grader",
  bulldozer: "bulldozer",
  "wheel loader": "wheel-loader",
  forklift: "forklift",
  "boom lift": "boom-lift",
  "scissor lift": "scissor-lift",
  "crawler drill": "crawler-drill",
  telehandler: "telehandler",
  compactor: "road-roller",
  "drum roller": "road-roller",
};

const REMOTE_FALLBACKS: Record<string, string> = {
  "motor grader":
    "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779780612094_motor_grader_front.jpg",
  excavator:
    "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507295/652234-excavator-1174428.jpg.jpg",
  "backhoe loader":
    "https://res.cloudinary.com/dzjzxbebz/image/upload/v1776857303/productImages_1776857300241_backhoe_loader.png",
  "wheel loader":
    "https://res.cloudinary.com/dzjzxbebz/image/upload/v1776857303/productImages_1776857300241_backhoe_loader.png",
  bulldozer:
    "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507294/dimitrisvetsikas1969-bulldozer-2195329.jpg.jpg",
  crane:
    "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507411/dimitrisvetsikas1969-crane-1842747.jpg.jpg",
  "hydra crane":
    "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507411/dimitrisvetsikas1969-crane-1842747.jpg.jpg",
  "road roller":
    "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507294/katerwursty-road-roller-6564386.jpg.jpg",
  "dump truck":
    "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779942377195_press-13aug20-lowres.jpg",
  "concrete mixer":
    "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779942341129_press-13aug20-lowres.jpg",
  "mobile crusher":
    "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507333/dimitrisvetsikas1969-heavy-machinery-6761291.jpg.jpg",
};

const DEFAULT_REMOTE =
  "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507376/dimitrisvetsikas1969-machine-3023906.jpg.jpg";

export function isSuspiciousImageUrl(url?: string | null): boolean {
  if (!url?.trim()) return true;
  const lower = url.toLowerCase();
  if (!lower.startsWith("http")) return true;
  return SUSPICIOUS_FRAGMENTS.some((f) => lower.includes(f));
}

function localPlaceholderPath(_category?: string): string {
  return "/machine-placeholders/default-machine.svg";
}

export function resolveMachineImageSrc(machine: {
  image_url?: string;
  images?: string[] | string;
  category?: string;
}): string {
  const category = (machine.category || "").toLowerCase().trim();
  const fromUrl = machine.image_url?.trim();
  if (fromUrl && !isSuspiciousImageUrl(fromUrl)) return fromUrl;

  const images = machine.images;
  if (Array.isArray(images)) {
    const good = images.find((u) => u?.trim() && !isSuspiciousImageUrl(u));
    if (good) return good;
  } else if (typeof images === "string" && images.trim()) {
    const first = images.split(" ")[0]?.trim();
    if (first && !isSuspiciousImageUrl(first)) return first;
  }

  return REMOTE_FALLBACKS[category] || localPlaceholderPath(category);
}

export function fallbackForCategory(category?: string): string {
  const key = (category || "").toLowerCase().trim();
  return REMOTE_FALLBACKS[key] || localPlaceholderPath(category);
}
