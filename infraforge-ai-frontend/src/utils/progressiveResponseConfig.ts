/** Centralized timing for progressive assistant text reveal and morph indicator. */

export const RESPONSE_ANIMATION_CONFIG = {
  initialDelay: 350,
  shortResponseWordDelay: 125,
  normalWordDelay: 100,
  longResponseWordDelay: 65,
  commaPause: 60,
  sentencePause: 180,
  paragraphPause: 250,
  minimumDuration: 1400,
  maximumDuration: 12000,
  completionDelay: 350,
  shapeMorphDuration: 700,
  shapeFadeDuration: 300,
} as const;

export const SHORT_TEXT_LENGTH = 80;
export const MEDIUM_TEXT_LENGTH = 400;

/** @deprecated Use RESPONSE_ANIMATION_CONFIG — kept for test migration */
export const PROGRESSIVE_TICK_MS = RESPONSE_ANIMATION_CONFIG.normalWordDelay;

export const PROGRESSIVE_LENGTH_THRESHOLDS = {
  short: SHORT_TEXT_LENGTH,
  medium: MEDIUM_TEXT_LENGTH,
} as const;

export function baseWordDelayForTextLength(charLength: number): number {
  const c = RESPONSE_ANIMATION_CONFIG;
  if (charLength <= SHORT_TEXT_LENGTH) return c.shortResponseWordDelay;
  if (charLength <= MEDIUM_TEXT_LENGTH) return c.normalWordDelay;
  return c.longResponseWordDelay;
}

/** @deprecated Use baseWordDelayForTextLength */
export function tickDelayForTextLength(length: number): number {
  return baseWordDelayForTextLength(length);
}

/** @deprecated Word-by-word reveal — always 1 */
export function chunkSizeForTextLength(_length: number): number {
  return 1;
}

export function punctuationPauseAfterWordChunk(chunk: string): number {
  const c = RESPONSE_ANIMATION_CONFIG;
  const trimmed = chunk.trimEnd();
  if (chunk.includes("\n\n") || (chunk.endsWith("\n") && chunk.trim().length === 0)) {
    return c.paragraphPause;
  }
  if (chunk.endsWith("\n\n") || /\n\n\s*$/.test(chunk)) {
    return c.paragraphPause;
  }
  if (chunk.endsWith("\n")) {
    return c.paragraphPause;
  }
  if (/[,;:]$/.test(trimmed)) {
    return c.commaPause;
  }
  if (/[.!?]["')\]]*$/.test(trimmed) || /[.!?]$/.test(trimmed)) {
    return c.sentencePause;
  }
  return 0;
}

export interface ProgressiveRevealStep {
  text: string;
  delayBeforeMs: number;
}

export function scaleScheduleToDurationWindow(
  steps: ProgressiveRevealStep[],
): ProgressiveRevealStep[] {
  const cfg = RESPONSE_ANIMATION_CONFIG;
  if (steps.length <= 1) return steps;

  const sumDelays = (list: ProgressiveRevealStep[]) =>
    list.slice(1).reduce((sum, step) => sum + step.delayBeforeMs, 0);

  let scaled = steps.map((step) => ({ ...step }));
  let total = sumDelays(scaled);

  if (total < cfg.minimumDuration) {
    const wordSteps = scaled.length - 1;
    const extra = cfg.minimumDuration - total;
    if (wordSteps > 0) {
      const perStep = extra / wordSteps;
      scaled = scaled.map((step, index) =>
        index === 0
          ? step
          : { ...step, delayBeforeMs: step.delayBeforeMs + perStep },
      );
    }
    total = sumDelays(scaled);
  }

  if (total > cfg.maximumDuration) {
    const factor = cfg.maximumDuration / total;
    scaled = scaled.map((step, index) =>
      index === 0
        ? step
        : {
            ...step,
            delayBeforeMs: Math.max(50, Math.floor(step.delayBeforeMs * factor)),
          },
    );
    total = sumDelays(scaled);
    if (total > cfg.maximumDuration) {
      const overflow = total - cfg.maximumDuration;
      const lastIndex = scaled.length - 1;
      scaled[lastIndex] = {
        ...scaled[lastIndex],
        delayBeforeMs: Math.max(50, scaled[lastIndex].delayBeforeMs - overflow),
      };
    }
  }

  return scaled;
}
