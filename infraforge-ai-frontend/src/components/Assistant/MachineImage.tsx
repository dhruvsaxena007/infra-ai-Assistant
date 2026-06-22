import React, { memo, useCallback, useEffect, useMemo, useState } from "react";
import { Construction } from "lucide-react";
import { resolveMachineImageSrc, fallbackForCategory } from "../../utils/machineImage";

export interface MachineImageMachine {
  image_url?: string | null;
  images?: string[] | string;
  category?: string;
  name?: string;
  image_alt?: string;
  is_representative_image?: boolean;
}

interface Props {
  machine: MachineImageMachine;
  className?: string;
  aspectClassName?: string;
  loading?: "lazy" | "eager";
}

function MachineImage({
  machine,
  className = "w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.03]",
  aspectClassName = "",
  loading = "lazy",
}: Props) {
  const initialSrc = useMemo(() => resolveMachineImageSrc(machine), [machine]);
  const [src, setSrc] = useState(initialSrc);
  const [failed, setFailed] = useState(false);
  const [fallbackUsed, setFallbackUsed] = useState(false);

  useEffect(() => {
    setSrc(initialSrc);
    setFailed(false);
    setFallbackUsed(false);
  }, [initialSrc]);

  const alt =
    machine.image_alt?.trim() ||
    (machine.name
      ? `${machine.name}${machine.is_representative_image ? " (representative)" : ""}`
      : "Construction equipment");

  const onError = useCallback(() => {
    if (!fallbackUsed) {
      const fb = fallbackForCategory(machine.category);
      if (fb && fb !== src) {
        setFallbackUsed(true);
        setSrc(fb);
        return;
      }
    }
    setFailed(true);
  }, [fallbackUsed, machine.category, src]);

  if (failed) {
    return (
      <div
        className={`w-full h-full flex flex-col items-center justify-center gap-1.5 text-on-surface-variant bg-surface-container-highest ${aspectClassName}`}
        role="img"
        aria-label={alt}
      >
        <Construction className="w-7 h-7 opacity-40" aria-hidden />
        <span className="text-[10px]">No photo</span>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      className={className}
      loading={loading}
      decoding="async"
      onError={onError}
    />
  );
}

export default memo(MachineImage);
