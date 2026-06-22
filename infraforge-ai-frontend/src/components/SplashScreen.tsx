import React, { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Hammer } from "lucide-react";

interface Props {
  onComplete: () => void;
  /** Total splash duration in ms */
  duration?: number;
}

const STATUS_LINES = [
  "Syncing equipment catalog",
  "Loading AI search models",
  "Connecting marketplace data",
  "Preparing your assistant",
];

export default function SplashScreen({ onComplete, duration = 2800 }: Props) {
  const [progress, setProgress] = useState(0);
  const [statusIdx, setStatusIdx] = useState(0);
  const [fadeOut, setFadeOut] = useState(false);

  useEffect(() => {
    const start = performance.now();
    let frame = 0;

    const tick = (now: number) => {
      const elapsed = now - start;
      const t = Math.min(1, elapsed / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setProgress(Math.round(eased * 100));
      setStatusIdx(Math.min(STATUS_LINES.length - 1, Math.floor(eased * STATUS_LINES.length)));

      if (t < 1) {
        frame = requestAnimationFrame(tick);
      } else {
        setFadeOut(true);
      }
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [duration]);

  return (
    <motion.div
      initial={{ opacity: 1 }}
      animate={{ opacity: fadeOut ? 0 : 1, scale: fadeOut ? 1.03 : 1 }}
      transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      onAnimationComplete={() => {
        if (fadeOut) onComplete();
      }}
      className="fixed inset-0 z-[200] flex flex-col items-center justify-center overflow-hidden splash-bg"
    >
      <div className="splash-radial-glow absolute inset-0 pointer-events-none" />
      <div className="splash-grid absolute inset-0 pointer-events-none opacity-40" />
      <div className="splash-scanline absolute inset-0 pointer-events-none" />

      <div className="splash-orb splash-orb-1" />
      <div className="splash-orb splash-orb-2" />
      <div className="splash-orb splash-orb-3" />

      <div className="relative z-10 flex flex-col items-center gap-8 px-6 w-full max-w-md">
        <motion.div
          initial={{ opacity: 0, scale: 0.6, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="relative"
        >
          <span className="absolute -inset-3 rounded-3xl splash-icon-ring" />
          <div className="relative w-16 h-16 rounded-2xl gradient-orange flex items-center justify-center shadow-2xl shadow-primary/30">
            <Hammer className="w-8 h-8 text-on-primary" />
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.15 }}
          className="text-center"
        >
          <h1 className="splash-wordmark text-4xl sm:text-5xl font-bold tracking-tight leading-none">
            <span className="splash-letter splash-letter-1">I</span>
            <span className="splash-letter splash-letter-2">n</span>
            <span className="splash-letter splash-letter-3">f</span>
            <span className="splash-letter splash-letter-4">r</span>
            <span className="splash-letter splash-letter-5">a</span>
          </h1>
          <p className="mt-3 text-sm sm:text-base splash-subtitle tracking-[0.2em] uppercase font-medium">
            AI-Assistant for Marketplace
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.35 }}
          className="w-full max-w-xs space-y-3"
        >
          <div className="relative h-[3px] w-full rounded-full splash-track overflow-hidden">
            <div
              className="absolute inset-y-0 left-0 rounded-full splash-fill transition-[width] duration-100 ease-linear"
              style={{ width: `${progress}%` }}
            />
            <div
              className="splash-glint absolute top-1/2 -translate-y-1/2 w-8 h-[5px] rounded-full transition-[left] duration-100 ease-linear"
              style={{ left: `calc(${Math.max(progress, 2)}% - 16px)` }}
            />
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono">
            <span className="splash-status text-on-surface-variant/80 transition-opacity duration-300">
              {STATUS_LINES[statusIdx]}
            </span>
            <span className="splash-percent tabular-nums text-on-surface font-semibold">
              {progress}%
            </span>
          </div>
        </motion.div>
      </div>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.5 }}
        transition={{ delay: 0.8, duration: 0.6 }}
        className="absolute bottom-8 text-[10px] tracking-widest uppercase text-on-surface-variant/50 font-mono"
      >
        Heavy machinery · Smart search · Live listings
      </motion.p>
    </motion.div>
  );
}
