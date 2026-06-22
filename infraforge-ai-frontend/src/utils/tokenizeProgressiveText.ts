import {
  baseWordDelayForTextLength,
  punctuationPauseAfterWordChunk,
  scaleScheduleToDurationWindow,
  type ProgressiveRevealStep,
  RESPONSE_ANIMATION_CONFIG,
} from "./progressiveResponseConfig";

export interface ProgressiveToken {
  text: string;
  isWord: boolean;
}

/** Split text into words and whitespace/newline segments — order preserved. */
export function tokenizeProgressiveText(text: string): ProgressiveToken[] {
  if (!text) return [];
  const parts: ProgressiveToken[] = [];
  const re = /\S+|\n|\s/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    const segment = match[0];
    parts.push({ text: segment, isWord: /\S/.test(segment) });
  }
  return parts;
}

/** Group tokens into reveal units: one word plus trailing whitespace/newlines. */
export function groupWordRevealUnits(tokens: ProgressiveToken[]): string[] {
  const units: string[] = [];
  let i = 0;
  while (i < tokens.length) {
    if (tokens[i].isWord) {
      let chunk = tokens[i].text;
      i += 1;
      while (i < tokens.length && !tokens[i].isWord) {
        chunk += tokens[i].text;
        i += 1;
      }
      units.push(chunk);
    } else {
      units.push(tokens[i].text);
      i += 1;
    }
  }
  return units;
}

/**
 * Build word-by-word reveal schedule with punctuation pauses and adaptive scaling.
 */
export function buildProgressiveRevealSchedule(fullText: string): ProgressiveRevealStep[] {
  if (!fullText) {
    return [{ text: "", delayBeforeMs: 0 }];
  }

  const tokens = tokenizeProgressiveText(fullText);
  const baseDelay = baseWordDelayForTextLength(fullText.length);
  const steps: ProgressiveRevealStep[] = [{ text: "", delayBeforeMs: 0 }];

  let buffer = "";
  for (const part of tokens) {
    buffer += part.text;
    if (!part.isWord) {
      continue;
    }

    const delayBeforeMs =
      steps.length === 1
        ? RESPONSE_ANIMATION_CONFIG.initialDelay
        : baseDelay + punctuationPauseAfterWordChunk(buffer);

    steps.push({ text: buffer, delayBeforeMs });
  }

  if (steps.length === 1) {
    steps.push({ text: fullText, delayBeforeMs: RESPONSE_ANIMATION_CONFIG.initialDelay });
  } else if (steps[steps.length - 1].text !== fullText) {
    steps.push({
      text: fullText,
      delayBeforeMs: baseDelay,
    });
  }

  return scaleScheduleToDurationWindow(steps);
}

/**
 * Cumulative reveal steps ending with the full string (one word per step).
 */
export function buildProgressiveRevealSteps(fullText: string): string[] {
  return buildProgressiveRevealSchedule(fullText).map((step) => step.text);
}
