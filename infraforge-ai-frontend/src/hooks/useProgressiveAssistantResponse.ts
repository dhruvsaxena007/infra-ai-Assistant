import { useCallback, useEffect, useRef, useState } from "react";
import { buildProgressiveRevealSchedule } from "../utils/tokenizeProgressiveText";
import { RESPONSE_ANIMATION_CONFIG } from "../utils/progressiveResponseConfig";
import type { ProgressiveRevealStep } from "../utils/progressiveResponseConfig";

export interface UseProgressiveAssistantResponseOptions {
  onUpdate: (messageId: string, displayedText: string) => void;
  onComplete: (messageId: string, fullText: string) => void;
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function useProgressiveAssistantResponse({
  onUpdate,
  onComplete,
}: UseProgressiveAssistantResponseOptions) {
  const generationSeqRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeRef = useRef<{
    messageId: string;
    fullText: string;
    steps: ProgressiveRevealStep[];
    stepIndex: number;
    generationId: number;
  } | null>(null);

  const onUpdateRef = useRef(onUpdate);
  const onCompleteRef = useRef(onComplete);
  onUpdateRef.current = onUpdate;
  onCompleteRef.current = onComplete;

  const [isGenerating, setIsGenerating] = useState(false);
  const [activeMessageId, setActiveMessageId] = useState<string | null>(null);
  const [displayedText, setDisplayedText] = useState("");
  const [indicatorFading, setIndicatorFading] = useState(false);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const completeWithFade = useCallback(
    (messageId: string, fullText: string, generationId: number) => {
      clearTimer();
      activeRef.current = null;

      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        if (generationSeqRef.current !== generationId) return;

        setIndicatorFading(true);
        timerRef.current = setTimeout(() => {
          timerRef.current = null;
          if (generationSeqRef.current !== generationId) return;

          setIndicatorFading(false);
          setIsGenerating(false);
          setActiveMessageId(null);
          setDisplayedText(fullText);
          onCompleteRef.current(messageId, fullText);
        }, RESPONSE_ANIMATION_CONFIG.shapeFadeDuration);
      }, RESPONSE_ANIMATION_CONFIG.completionDelay);
    },
    [clearTimer],
  );

  const finishActive = useCallback(
    (reason: "complete" | "cancel" | "immediate") => {
      const active = activeRef.current;
      clearTimer();
      setIndicatorFading(false);

      if (!active) {
        setIsGenerating(false);
        setActiveMessageId(null);
        return;
      }

      const { messageId, fullText } = active;
      activeRef.current = null;
      setIsGenerating(false);
      setActiveMessageId(null);

      if (reason === "cancel") {
        setDisplayedText("");
        return;
      }

      setDisplayedText(fullText);
      onUpdateRef.current(messageId, fullText);
      if (reason === "complete" || reason === "immediate") {
        onCompleteRef.current(messageId, fullText);
      }
    },
    [clearTimer],
  );

  const scheduleNextStep = useCallback(() => {
    const active = activeRef.current;
    if (!active) return;

    const { steps, stepIndex, messageId, fullText, generationId } = active;
    if (stepIndex >= steps.length) {
      finishActive("complete");
      return;
    }

    const step = steps[stepIndex];
    setDisplayedText(step.text);
    onUpdateRef.current(messageId, step.text);

    if (stepIndex >= steps.length - 1) {
      setDisplayedText(fullText);
      onUpdateRef.current(messageId, fullText);
      completeWithFade(messageId, fullText, generationId);
      return;
    }

    activeRef.current = {
      ...active,
      stepIndex: stepIndex + 1,
    };

    const nextStep = steps[stepIndex + 1];
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      if (activeRef.current?.generationId !== generationId) return;
      scheduleNextStep();
    }, nextStep.delayBeforeMs);
  }, [completeWithFade, finishActive]);

  const cancel = useCallback(() => {
    generationSeqRef.current += 1;
    finishActive("cancel");
  }, [finishActive]);

  const finishImmediately = useCallback(() => {
    const active = activeRef.current;
    if (!active) return;
    generationSeqRef.current += 1;
    const { messageId, fullText } = active;
    clearTimer();
    setIndicatorFading(false);
    activeRef.current = null;
    setIsGenerating(false);
    setActiveMessageId(null);
    setDisplayedText(fullText);
    onUpdateRef.current(messageId, fullText);
    onCompleteRef.current(messageId, fullText);
  }, [clearTimer]);

  const start = useCallback(
    (messageId: string, fullText: string) => {
      generationSeqRef.current += 1;
      const generationId = generationSeqRef.current;
      clearTimer();
      setIndicatorFading(false);

      if (prefersReducedMotion()) {
        activeRef.current = null;
        setIsGenerating(false);
        setActiveMessageId(null);
        setDisplayedText(fullText);
        onUpdateRef.current(messageId, fullText);
        onCompleteRef.current(messageId, fullText);
        return;
      }

      const steps = buildProgressiveRevealSchedule(fullText);
      activeRef.current = {
        messageId,
        fullText,
        steps,
        stepIndex: 0,
        generationId,
      };
      setIsGenerating(true);
      setActiveMessageId(messageId);
      setDisplayedText("");
      onUpdateRef.current(messageId, "");

      if (steps.length <= 1) {
        completeWithFade(messageId, fullText, generationId);
        return;
      }

      const firstReveal = steps[1];
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        if (activeRef.current?.generationId !== generationId) return;
        activeRef.current = { ...activeRef.current, stepIndex: 1 };
        scheduleNextStep();
      }, firstReveal.delayBeforeMs);
    },
    [clearTimer, completeWithFade, scheduleNextStep],
  );

  useEffect(
    () => () => {
      generationSeqRef.current += 1;
      clearTimer();
      activeRef.current = null;
    },
    [clearTimer],
  );

  return {
    start,
    cancel,
    finishImmediately,
    isGenerating,
    activeMessageId,
    displayedText,
    indicatorFading,
  };
}
