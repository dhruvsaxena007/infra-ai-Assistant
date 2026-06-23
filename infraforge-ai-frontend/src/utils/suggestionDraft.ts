/**
 * Centralized suggestion draft insertion — populates input without sending.
 */

export type InsertDraftOptions = {
  /** Replace entire input when true; otherwise insert at cursor. */
  replace?: boolean;
};

export function buildDraftAfterInsert(
  current: string,
  suggestion: string,
  selectionStart: number,
  selectionEnd: number,
  options?: InsertDraftOptions,
): { value: string; caret: number } {
  const text = suggestion.trim();
  if (!text) return { value: current, caret: selectionStart };

  if (options?.replace || !current.trim()) {
    return { value: text, caret: text.length };
  }

  const before = current.slice(0, selectionStart);
  const after = current.slice(selectionEnd);
  const needsSpaceBefore = before.length > 0 && !/\s$/.test(before);
  const needsSpaceAfter = after.length > 0 && !/^\s/.test(after);
  const insert = `${needsSpaceBefore ? " " : ""}${text}${needsSpaceAfter ? " " : ""}`;
  const value = `${before}${insert}${after}`;
  const caret = before.length + insert.length;
  return { value, caret };
}

export function focusInputWithCaret(
  input: HTMLTextAreaElement | HTMLInputElement | null,
  caret: number,
): void {
  if (!input) return;
  requestAnimationFrame(() => {
    input.focus();
    try {
      input.setSelectionRange(caret, caret);
    } catch {
      /* some browsers */
    }
  });
}

/** Action chips that open pickers — never populate draft text. */
export const SUGGESTION_ACTION_CHIPS = new Set([
  "Upload image",
  "Upload clearer image",
  "Voice search",
  "Document Q&A",
  "Upload document",
  "Upload PDF",
]);

export function isSuggestionActionChip(chip: string): boolean {
  return SUGGESTION_ACTION_CHIPS.has(chip);
}

export function resolveSuggestionDraftText(
  chip: string,
  promptMap: Record<string, string>,
): string {
  if (isSuggestionActionChip(chip)) return "";
  return (promptMap[chip] ?? chip).trim();
}
