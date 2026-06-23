import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Hammer,
  Trash2,
  RotateCcw,
  Wifi,
  WifiOff,
  Loader2,
  GitCompareArrows,
  X,
} from "lucide-react";

import type {
  BackendStatus,
  ChatMessage,
  CompareResult,
  Machine,
  SessionUsage,
} from "../../types";
import {
  filterMachinesByListing,
  listingFilterCounts,
  type ListingFilter,
} from "../../utils/listingType";
import { useProgressiveAssistantResponse } from "../../hooks/useProgressiveAssistantResponse";
import {
  API_BASE_URL,
  BackendUnreachableError,
  checkHealth,
  HEALTH_CHECK_TIMEOUT_MS,
  IMAGE_SEARCH_LIMIT_PER_SESSION,
  resetAssistantSession,
  sendChatMessage,
  sendImageSearch,
  sendVoiceChat,
  VOICE_MESSAGE_LIMIT_PER_SESSION,
  VOICE_REQUEST_TIMEOUT_MS,
  ragUploadPdf,
  ragUploadText,
} from "../../api/assistantApi";
import SupportRequestModal from "./SupportRequestModal";
import SessionLimitModal, { type SessionLimitType } from "./SessionLimitModal";
import type { ImageSource } from "./ImagePicker";

import ChatWindow from "./ChatWindow";
import ChatInput, { type ChatInputHandle } from "./ChatInput";
import MachineResults from "./MachineResults";
import ErrorBanner from "./ErrorBanner";
import MachineDetailsModal from "./MachineDetailsModal";
import PriceInsightModal from "./PriceInsightModal";
import DealScoreModal from "./DealScoreModal";
import SimilarMachinesModal from "./SimilarMachinesModal";
import ComparePanel from "./ComparePanel";
import ContactOwnerModal from "./ContactOwnerModal";
import MachineDrawer from "./MachineDrawer";
import { getMachineId } from "../../utils/machineId";
import {
  isSuggestionActionChip,
  resolveSuggestionDraftText,
} from "../../utils/suggestionDraft";
import { createSessionId, loadSessionId, persistSessionId } from "../../utils/sessionId";

const IMAGE_CLARIFICATION_CHIPS = new Set([
  "Exact same machine",
  "Similar machines",
  "Just identify this machine",
  "Bilkul same machine",
  "Similar machines dikhao",
  "Bas identify karo",
]);

const DEFAULT_SESSION_USAGE: SessionUsage = {
  image_search_count: 0,
  image_search_limit: IMAGE_SEARCH_LIMIT_PER_SESSION,
  voice_message_count: 0,
  voice_message_limit: VOICE_MESSAGE_LIMIT_PER_SESSION,
};

type LimitModalState = {
  limitType: SessionLimitType;
  used: number;
  limit: number;
} | null;

const SELECTED_MACHINE_KEY = "infra_assistant_selected_machine";

function loadSelectedMachineId(sessionId: string): string | null {
  try {
    const raw = sessionStorage.getItem(`${SELECTED_MACHINE_KEY}:${sessionId}`);
    return raw || null;
  } catch {
    return null;
  }
}

function saveSelectedMachineId(sessionId: string, id: string | null) {
  try {
    const key = `${SELECTED_MACHINE_KEY}:${sessionId}`;
    if (id) sessionStorage.setItem(key, id);
    else sessionStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

function titleCase(value?: string | null): string {
  if (!value) return "machine";
  return value.replace(/\b\w/g, (c) => c.toUpperCase());
}

type ActiveModal =
  | { type: "details"; machine: Machine }
  | { type: "price"; machine: Machine }
  | { type: "deal"; machine: Machine }
  | { type: "similar"; machine: Machine }
  | { type: "compare"; a: Machine; b: Machine }
  | { type: "contact"; machine: Machine }
  | null;

const SUGGESTION_PROMPTS: Record<string, string> = {
  "Search Machine": "excavator in jaipur",
  "Search machine": "excavator in jaipur",
  "Search this machine": "Search this machine",
  "Upload image": "",
  "Voice search": "",
  "Ask recommendation": "Ask recommendation",
  "Talk to support": "Talk to support",
  "Order issue": "Order issue",
  "Booking issue": "Booking issue",
  "Refund/Return": "Refund/Return",
  "Payment issue": "Payment issue",
  "Contact support": "Contact support",
  "Upload document": "",
  "Share order ID": "Share order ID",
  "Share booking ID": "Share booking ID",
  "Share transaction ID": "Share transaction ID",
  "Booking policy": "Booking policy",
  "Compare brands": "Compare brands",
  "Compare machines": "Compare machines",
  "Show cheaper options": "Show cheaper options",
  "Rent only": "Rent only",
  "Contact owner": "Contact owner",
  "Search nearby cities": "Search nearby cities",
  "Try similar machines": "Try similar machines",
  "Increase budget": "Increase budget",
  "Show other brands": "Show other brands",
  "Tell city for listings": "Tell city for listings",
  "Digging": "Digging",
  "Lifting": "Lifting",
  "Compaction": "Compaction",
  "Loading": "Loading",
  "Transport": "Transport",
  "Road work": "Road work",
  "Building": "Building",
  "Earthwork": "Earthwork",
  "Jaipur": "Jaipur",
  "Delhi": "Delhi",
  "Mumbai": "Mumbai",
  "Pune": "Pune",
  "Excavator": "Excavator",
  "Road Roller": "Road Roller",
  "Crane": "Crane",
  "Backhoe Loader": "Backhoe Loader",
  "Raise request": "",
  "Raise Request": "",
  "Call support": "Call support",
  "WhatsApp": "WhatsApp",
};

export default function AssistantPage() {
  const [sessionId, setSessionId] = useState<string>(loadSessionId);
  const [openImagePickerSignal, setOpenImagePickerSignal] = useState(0);
  const [openDocumentSignal, setOpenDocumentSignal] = useState(0);
  const [startVoiceSignal, setStartVoiceSignal] = useState(0);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [listingFilter, setListingFilter] = useState<ListingFilter>("both");
  const [selectedMachineId, setSelectedMachineId] = useState<string | null>(() =>
    loadSelectedMachineId(loadSessionId()),
  );
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("Thinking");
  const [error, setError] = useState<string | null>(null);

  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");
  const [compareSelection, setCompareSelection] = useState<Machine[]>([]);
  const [modal, setModal] = useState<ActiveModal>(null);

  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [supportModalOpen, setSupportModalOpen] = useState(false);
  const [supportIssueType, setSupportIssueType] = useState("");
  const [sessionUsage, setSessionUsage] = useState<SessionUsage>(DEFAULT_SESSION_USAGE);
  const [limitModal, setLimitModal] = useState<LimitModalState>(null);

  const chatInputRef = useRef<ChatInputHandle>(null);
  const voiceAbortRef = useRef<AbortController | null>(null);
  const voiceInFlightRef = useRef(false);
  const imageUploadInFlightRef = useRef(false);

  useEffect(() => {
    return () => {
      voiceAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    setSelectedMachineId(loadSelectedMachineId(sessionId));
  }, [sessionId]);

  // --- Backend health -------------------------------------------------------
  const markBackendConnected = useCallback(() => {
    setBackendStatus("connected");
    setError(null);
  }, []);

  const runHealthCheck = useCallback(async (options?: { silent?: boolean }) => {
    if (!options?.silent) {
      setBackendStatus("checking");
    }

    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const controller = new AbortController();
        const timeoutId = window.setTimeout(
          () => controller.abort(),
          HEALTH_CHECK_TIMEOUT_MS,
        );
        const res = await checkHealth({ signal: controller.signal });
        window.clearTimeout(timeoutId);

        if (res.success) {
          markBackendConnected();
          return;
        }
      } catch {
        /* retry — Render cold start or transient network blip */
      }
      if (attempt < 2) {
        await new Promise((resolve) => window.setTimeout(resolve, 2500));
      }
    }

    setBackendStatus((prev) => (prev === "connected" ? "connected" : "disconnected"));
  }, [markBackendConnected]);

  useEffect(() => {
    void runHealthCheck();
    const id = window.setInterval(() => {
      void runHealthCheck({ silent: true });
    }, 30000);
    return () => window.clearInterval(id);
  }, [runHealthCheck]);

  // --- Helpers --------------------------------------------------------------
  const pushMessage = (m: ChatMessage) => setMessages((prev) => [...prev, m]);

  const progressive = useProgressiveAssistantResponse({
    onUpdate: (messageId, displayedText) => {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId ? { ...m, displayedText } : m,
        ),
      );
    },
    onComplete: (messageId, fullText) => {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId
            ? {
                ...m,
                text: fullText,
                displayedText: undefined,
                isGenerating: false,
                generationComplete: true,
              }
            : m,
        ),
      );
      chatInputRef.current?.focus();
    },
  });

  const enqueueAssistantResponse = useCallback(
    (payload: Omit<ChatMessage, "isGenerating" | "generationComplete" | "displayedText">) => {
      const id = payload.id || `a-${Date.now()}`;
      const fullText = payload.text;
      pushMessage({
        ...payload,
        id,
        role: "assistant",
        text: fullText,
        displayedText: "",
        isGenerating: true,
        generationComplete: false,
      });
      progressive.start(id, fullText);
    },
    [progressive],
  );

  const pushAssistantError = (text: string, meta?: string) =>
    pushMessage({
      id: `err-${Date.now()}`,
      role: "assistant",
      text,
      timestamp: Date.now(),
      isError: true,
      meta,
      generationComplete: true,
    });

  const pushAssistantInfo = (text: string, meta?: string) =>
    enqueueAssistantResponse({
      id: `i-${Date.now()}`,
      role: "assistant",
      text,
      timestamp: Date.now(),
      meta,
    });

  const syncSessionUsage = (usage?: SessionUsage | null) => {
    if (!usage || typeof usage !== "object") return;
    setSessionUsage({
      image_search_count: Number(usage.image_search_count) || 0,
      image_search_limit: Number(usage.image_search_limit) || IMAGE_SEARCH_LIMIT_PER_SESSION,
      voice_message_count: Number(usage.voice_message_count) || 0,
      voice_message_limit: Number(usage.voice_message_limit) || VOICE_MESSAGE_LIMIT_PER_SESSION,
    });
  };

  const showSessionLimitModal = (
    limitType: SessionLimitType,
    used: number,
    limit: number,
  ) => {
    setLimitModal({ limitType, used, limit });
  };

  const isSessionLimitError = (
    err: unknown,
  ): { limitType: SessionLimitType; used: number; limit: number } | null => {
    if (!err || typeof err !== "object") return null;
    const e = err as Record<string, unknown>;
    if (e.stage !== "session_limit_exceeded") return null;
    const limitType = e.limit_type === "voice_message" ? "voice_message" : "image_search";
    return {
      limitType,
      used: Number(e.used) || 0,
      limit: Number(e.limit) || (limitType === "voice_message"
        ? VOICE_MESSAGE_LIMIT_PER_SESSION
        : IMAGE_SEARCH_LIMIT_PER_SESSION),
    };
  };

  const handleSessionLimitResponse = (res: { success: boolean; error?: unknown }) => {
    if (res.success) return false;
    const info = isSessionLimitError(res.error);
    if (!info) return false;
    setSessionUsage((prev) => ({
      ...prev,
      ...(info.limitType === "image_search"
        ? { image_search_count: info.used, image_search_limit: info.limit }
        : { voice_message_count: info.used, voice_message_limit: info.limit }),
    }));
    showSessionLimitModal(info.limitType, info.used, info.limit);
    return true;
  };

  const applyChatResponse = (
    res: Awaited<ReturnType<typeof sendChatMessage>>,
    options?: { meta?: string; clearMachinesOnClarification?: boolean },
  ) => {
    if (res.success) {
      markBackendConnected();
      const data = res.data ?? {};
      syncSessionUsage(data.session_usage as SessionUsage | undefined);
      const mode = (data.context?.assistant_mode ?? data.assistant_mode) as string | undefined;
      const comparison = extractComparisonFromResponse(data as Record<string, unknown>);
      const isImageClarification =
        mode === "image_clarification" || data.needs_clarification === true;
      enqueueAssistantResponse({
        id: `a-${Date.now()}`,
        role: "assistant",
        text: res.message,
        timestamp: Date.now(),
        meta: options?.meta ?? (comparison ? "Comparison" : isImageClarification ? "Image" : undefined),
        advisorMessage: comparison ? null : (data.advisor_message ?? null),
        filters: data.filters ?? null,
        suggestions: Array.isArray(data.suggestions) ? data.suggestions : undefined,
        handover: data.handover ?? null,
        assistantMode: typeof mode === "string" ? mode : undefined,
        comparison,
      });
      const ctx = data.context as Record<string, unknown> | undefined;
      const preserve =
        Boolean(ctx?.preserve_machine_panel) ||
        mode === "conversational" ||
        mode === "comparison";
      const pool = extractMachinesFromResponse(data as Record<string, unknown>);
      if (isImageClarification || options?.clearMachinesOnClarification) {
        if (pool.length === 0) setMachines([]);
      }
      if (preserve && pool.length === 0) return;
      if (pool.length > 0) {
        setMachines(pool);
        setListingFilter("both");
        const lt = (data.filters as { listing_type?: string } | undefined)?.listing_type;
        if (lt === "rent" || lt === "sell" || lt === "buy") {
          setListingFilter(lt === "rent" ? "rent" : "sell");
        }
      }
    } else {
      pushAssistantError(res.message || "The assistant could not process that request.");
    }
  };

  const extractMachinesFromResponse = (data: Record<string, unknown>): Machine[] => {
    if (!data || typeof data !== "object") return [];
    const pools = [
      data.machines,
      data.results,
      data.alternatives,
      data.recommendations,
      data.exact_results,
    ];
    for (const pool of pools) {
      if (Array.isArray(pool)) return pool as Machine[];
    }
    return [];
  };

  /** Apply a successful /chat response payload to the chat + results panel. */
  const extractComparisonFromResponse = (
    data: Record<string, unknown>,
  ): CompareResult | null => {
    const m1 = data.machine_1 as CompareResult["machine_1"] | undefined;
    const m2 = data.machine_2 as CompareResult["machine_2"] | undefined;
    const nested = data.comparison as CompareResult | undefined;

    const baseM1 = m1 || nested?.machine_1;
    const baseM2 = m2 || nested?.machine_2;
    if (!baseM1?.name || !baseM2?.name) {
      return null;
    }

    return {
      machine_1: baseM1,
      machine_2: baseM2,
      comparison_rows:
        (data.comparison_rows as CompareResult["comparison_rows"]) ||
        nested?.comparison_rows ||
        [],
      llm_summary:
        (data.llm_summary as string | undefined) ||
        nested?.llm_summary ||
        nested?.summary_draft,
      summary_draft: nested?.summary_draft,
      better_for_budget:
        (data.better_for_budget as string) || nested?.better_for_budget || "",
      better_rating:
        (data.better_rating as string) || nested?.better_rating || "",
      overall_recommendation:
        (data.overall_recommendation as string) ||
        nested?.overall_recommendation ||
        "",
      value_for_money:
        (data.value_for_money as string | undefined) || nested?.value_for_money,
      cross_type_warning: nested?.cross_type_warning,
    };
  };

  const handleNetworkError = (e: unknown, fallback: string) => {
    progressive.cancel();
    if (e instanceof BackendUnreachableError) {
      setError(e.message);
      setBackendStatus("disconnected");
      pushAssistantError("Backend not reachable. Please make sure the API is running.");
    } else {
      setError(fallback);
      pushAssistantError(fallback);
    }
  };

  // --- Text chat ------------------------------------------------------------
  const handleSendText = async (text: string) => {
    setError(null);
    if (progressive.isGenerating) progressive.finishImmediately();

    // The bubble always shows what the user actually typed.
    pushMessage({ id: `u-${Date.now()}`, role: "user", text, timestamp: Date.now() });

    setLoadingLabel("Thinking");
    setLoading(true);
    try {
      const res = await sendChatMessage(sessionId, text, selectedMachineId);
      applyChatResponse(res);
    } catch (e) {
      handleNetworkError(e, "Something went wrong while sending your message.");
    } finally {
      setLoading(false);
    }
  };

  const cancelVoiceRequest = useCallback(() => {
    voiceAbortRef.current?.abort();
    voiceAbortRef.current = null;
    voiceInFlightRef.current = false;
  }, []);

  // --- Voice chat -----------------------------------------------------------
  const handleSendVoice = async (file: File) => {
    if (voiceInFlightRef.current) return;
    if (sessionUsage.voice_message_count >= sessionUsage.voice_message_limit) {
      showSessionLimitModal(
        "voice_message",
        sessionUsage.voice_message_count,
        sessionUsage.voice_message_limit,
      );
      return;
    }
    setError(null);
    if (progressive.isGenerating) progressive.finishImmediately();
    const userMsgId = `u-${Date.now()}`;
    pushMessage({
      id: userMsgId,
      role: "user",
      text: "🎙️ Voice message",
      timestamp: Date.now(),
    });
    setLoadingLabel("Processing voice");
    setLoading(true);
    voiceInFlightRef.current = true;
    voiceAbortRef.current?.abort();
    const controller = new AbortController();
    voiceAbortRef.current = controller;
    const timeoutId = window.setTimeout(() => controller.abort(), VOICE_REQUEST_TIMEOUT_MS);
    try {
      const res = await sendVoiceChat(sessionId, file, selectedMachineId, {
        signal: controller.signal,
      });
      if (res.success) {
        const data = res.data ?? {};
        syncSessionUsage(data.session_usage);
        const transcript = data.voice_input?.original_voice_text;
        if (transcript) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === userMsgId ? { ...m, text: `🎙️ ${transcript}` } : m,
            ),
          );
        }
        applyChatResponse(res);
      } else if (handleSessionLimitResponse(res)) {
        setMessages((prev) => prev.filter((m) => m.id !== userMsgId));
      } else {
        pushAssistantError(res.message || "Voice transcription failed. Please try again.");
      }
    } catch (e) {
      if ((e as DOMException)?.name === "AbortError") {
        setMessages((prev) => prev.filter((m) => m.id !== userMsgId));
        return;
      }
      handleNetworkError(e, "Something went wrong while processing your voice message.");
    } finally {
      window.clearTimeout(timeoutId);
      voiceInFlightRef.current = false;
      if (voiceAbortRef.current === controller) {
        voiceAbortRef.current = null;
      }
      setLoading(false);
    }
  };

  // --- Image search (single API path → applyChatResponse) -------------------
  const handleImageUpload = async (
    file: File,
    caption: string,
    _source: ImageSource = "upload",
  ) => {
    if (imageUploadInFlightRef.current) return;
    if (sessionUsage.image_search_count >= sessionUsage.image_search_limit) {
      showSessionLimitModal(
        "image_search",
        sessionUsage.image_search_count,
        sessionUsage.image_search_limit,
      );
      return;
    }
    setError(null);
    if (progressive.isGenerating) progressive.finishImmediately();
    const previewUrl = URL.createObjectURL(file);
    const userMsgId = `u-${Date.now()}`;
    pushMessage({
      id: userMsgId,
      role: "user",
      text: caption.trim() || "Uploaded an image for machine search",
      timestamp: Date.now(),
      imageUrl: previewUrl,
    });
    setLoadingLabel("Analyzing image");
    setLoading(true);
    imageUploadInFlightRef.current = true;
    try {
      const res = await sendImageSearch(file, sessionId, caption.trim() || undefined);
      if (handleSessionLimitResponse(res)) {
        setMessages((prev) => prev.filter((m) => m.id !== userMsgId));
        URL.revokeObjectURL(previewUrl);
        return;
      }
      applyChatResponse(res, { meta: "Image", clearMachinesOnClarification: true });
    } catch (e) {
      handleNetworkError(e, "Something went wrong while searching by image.");
    } finally {
      imageUploadInFlightRef.current = false;
      setLoading(false);
    }
  };

  const handleSendImage = (file: File, source: ImageSource = "upload") =>
    handleImageUpload(file, "", source);

  const handleSendImageText = (file: File, text: string, source: ImageSource = "upload") =>
    handleImageUpload(file, text, source);

  // --- Document + text (inline RAG via /chat after upload) -------------------
  const handleSendDocumentText = async (file: File, text: string) => {
    setError(null);
    if (progressive.isGenerating) progressive.finishImmediately();
    pushMessage({
      id: `u-${Date.now()}`,
      role: "user",
      text,
      timestamp: Date.now(),
      documentName: file.name,
    });
    setLoadingLabel("Reading document");
    setLoading(true);
    try {
      if (file.type.startsWith("text/") || file.name.endsWith(".txt")) {
        const body = await file.text();
        const up = await ragUploadText(body, sessionId);
        if (!up.success) {
          pushAssistantError(up.message || "Could not upload document text.");
          return;
        }
      } else {
        const up = await ragUploadPdf(file, sessionId);
        if (!up.success) {
          pushAssistantError(up.message || "Could not upload PDF.");
          return;
        }
      }
      setLoadingLabel("Answering from document");
      const chatRes = await sendChatMessage(sessionId, text, selectedMachineId);
      applyChatResponse(chatRes);
    } catch (e) {
      handleNetworkError(e, "Something went wrong while processing your document.");
    } finally {
      setLoading(false);
    }
  };

  const handleRaiseSupportRequest = (issueType?: string) => {
    setSupportIssueType(issueType || "");
    setSupportModalOpen(true);
  };

  // --- Compare selection ----------------------------------------------------
  const toggleCompare = (m: Machine) => {
    const mid = getMachineId(m);
    if (!mid) return;
    setCompareSelection((prev) => {
      const exists = prev.some((x) => getMachineId(x) === mid);
      if (exists) return prev.filter((x) => getMachineId(x) !== mid);
      return [...prev, m].slice(-2);
    });
  };

  const compareIds = useMemo(
    () => compareSelection.map((m) => getMachineId(m) || ""),
    [compareSelection],
  );

  const visibleMachines = useMemo(
    () => filterMachinesByListing(machines, listingFilter),
    [machines, listingFilter],
  );

  const listingCounts = useMemo(() => listingFilterCounts(machines), [machines]);

  const handleSelectMachine = (m: Machine) => {
    const mid = getMachineId(m);
    if (!mid) return;
    const next = selectedMachineId === mid ? null : mid;
    setSelectedMachineId(next);
    saveSelectedMachineId(sessionId, next);
  };

  const handleSuggestionClick = (chip: string) => {
    if (isSuggestionActionChip(chip)) {
      if (chip === "Upload image" || chip === "Upload clearer image") {
        setOpenImagePickerSignal((n) => n + 1);
      } else if (chip === "Voice search") {
        setStartVoiceSignal((n) => n + 1);
      } else if (chip === "Document Q&A" || chip === "Upload document" || chip === "Upload PDF") {
        setOpenDocumentSignal((n) => n + 1);
      }
      return;
    }
    if (chip === "Raise request" || chip === "Raise Request" || chip === "Call support" || chip === "WhatsApp") {
      handleRaiseSupportRequest();
      return;
    }
    if (IMAGE_CLARIFICATION_CHIPS.has(chip)) {
      void handleSendText(chip);
      return;
    }
    const draft = resolveSuggestionDraftText(chip, SUGGESTION_PROMPTS);
    void handleSendText(draft || chip);
  };

  // --- Session controls -----------------------------------------------------
  const resetBackendSession = useCallback(async (sid: string) => {
    if (!sid) return;
    try {
      await resetAssistantSession(sid);
    } catch {
      /* backend reset is best-effort; UI still clears locally */
    }
  }, []);

  const clearChat = () => {
    progressive.cancel();
    cancelVoiceRequest();
    void resetBackendSession(sessionId);
    setMessages([]);
    setMachines([]);
    setCompareSelection([]);
    setSelectedMachineId(null);
    saveSelectedMachineId(sessionId, null);
    setSessionUsage({ ...DEFAULT_SESSION_USAGE });
    setLimitModal(null);
    setError(null);
  };

  const resetSession = () => {
    progressive.cancel();
    cancelVoiceRequest();
    const previous = sessionId;
    void resetBackendSession(previous);
    const fresh = createSessionId();
    persistSessionId(fresh);
    setSessionId(fresh);
    setSelectedMachineId(null);
    saveSelectedMachineId(fresh, null);
    setMessages([]);
    setMachines([]);
    setCompareSelection([]);
    setSessionUsage({ ...DEFAULT_SESSION_USAGE });
    setLimitModal(null);
    setError(null);
  };

  // --- Render ---------------------------------------------------------------
  const machineHandlers = {
    onViewDetails: (m: Machine) => setModal({ type: "details", machine: m }),
    onToggleCompare: toggleCompare,
    onSelectMachine: handleSelectMachine,
    onPriceInsight: (m: Machine) => setModal({ type: "price", machine: m }),
    onDealScore: (m: Machine) => setModal({ type: "deal", machine: m }),
    onSimilar: (m: Machine) => setModal({ type: "similar", machine: m }),
    onContactOwner: (m: Machine) => setModal({ type: "contact", machine: m }),
  };

  const isLocalApi =
    API_BASE_URL.includes("127.0.0.1") || API_BASE_URL.includes("localhost");

  const disconnectedBannerMessage = isLocalApi
    ? `Backend not reachable at ${API_BASE_URL}. Start it with: uvicorn app.main:app --reload`
    : `Backend is waking up at ${API_BASE_URL}. Wait 30 seconds, then click the status badge to retry. Chat may still work once the server is live.`;

  const statusBadge = (
    <button
      type="button"
      onClick={runHealthCheck}
      title={`Backend: ${API_BASE_URL} — click to re-check`}
      className={`status-pill flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[11px] font-medium cursor-pointer transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-primary/40 ${
        backendStatus === "connected"
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
          : backendStatus === "disconnected"
            ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
            : "border-border-subtle bg-surface-container-high text-on-surface-variant"
      }`}
    >
      {backendStatus === "checking" ? (
        <Loader2 className="w-3 h-3 animate-spin" />
      ) : backendStatus === "connected" ? (
        <Wifi className="w-3 h-3" />
      ) : (
        <WifiOff className="w-3 h-3" />
      )}
      {backendStatus === "connected"
        ? "Connected"
        : backendStatus === "disconnected"
          ? "Disconnected"
          : "Checking…"}
    </button>
  );

  return (
    <div className="app-shell h-dvh max-h-dvh flex flex-col overflow-hidden bg-background text-on-background gradient-mesh">
      {/* Header */}
      <header className="app-header flex-shrink-0 z-40 flex items-center justify-between gap-2 sm:gap-3 px-3 sm:px-6 lg:px-8 h-14 sm:h-16 glass-panel border-b border-border-subtle">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl gradient-orange flex items-center justify-center text-on-primary shadow-lg shadow-primary/20 flex-shrink-0">
            <Hammer className="w-4 h-4 sm:w-5 sm:h-5" />
          </div>
          <div className="min-w-0">
            <div className="font-semibold text-xs sm:text-sm lg:text-base text-on-surface leading-tight truncate">
              Drv's <span className="text-primary">Infra AI-Assistant</span>
            </div>
            <div className="text-[9px] sm:text-[10px] text-on-surface-variant font-mono truncate max-w-[140px] sm:max-w-none">
              {sessionId}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
          {statusBadge}
          <button
            type="button"
            onClick={clearChat}
            title="Clear chat"
            aria-label="Clear chat"
            className="header-action-btn flex items-center gap-1.5 px-2 sm:px-2.5 py-1.5 rounded-lg border border-border-subtle bg-surface-container-high text-on-surface-variant hover:text-on-surface text-[11px] font-medium cursor-pointer transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Clear</span>
          </button>
          <button
            type="button"
            onClick={resetSession}
            title="Reset session"
            aria-label="Reset session"
            className="header-action-btn flex items-center gap-1.5 px-2 sm:px-2.5 py-1.5 rounded-lg border border-border-subtle bg-surface-container-high text-on-surface-variant hover:text-on-surface text-[11px] font-medium cursor-pointer transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Reset</span>
          </button>
        </div>
      </header>

      {backendStatus === "disconnected" && (
        <div className="flex-shrink-0 px-4 md:px-8 pt-2 pb-1">
          <ErrorBanner
            message={disconnectedBannerMessage}
            onDismiss={() => markBackendConnected()}
          />
        </div>
      )}

      {/* Body */}
      <main className="assistant-layout flex-1 w-full max-w-[1440px] mx-auto px-3 sm:px-6 lg:px-8 py-3 sm:py-4 min-h-0 overflow-hidden">
        {/* Chat panel */}
        <section className="chat-panel glass-panel rounded-2xl flex flex-col min-h-0 max-h-full overflow-hidden">
          <ChatWindow
            messages={messages}
            loading={loading}
            loadingLabel={loadingLabel}
            isGenerating={progressive.isGenerating}
            activeGenerationMessageId={progressive.activeMessageId}
            indicatorFading={progressive.indicatorFading}
            onSuggestionClick={handleSuggestionClick}
            onRaiseSupportRequest={handleRaiseSupportRequest}
          />

          {error && (
            <div className="px-3 sm:px-4 pb-2 flex-shrink-0">
              <ErrorBanner message={error} onDismiss={() => setError(null)} />
            </div>
          )}

          <div className="chat-input-sticky px-3 sm:px-4 py-3 border-t border-border-subtle/80 flex-shrink-0">
            <ChatInput
              ref={chatInputRef}
              disabled={loading || progressive.isGenerating}
              uploading={loading && loadingLabel === "Analyzing image"}
              onSendText={handleSendText}
              onSendVoice={handleSendVoice}
              onSendImage={handleSendImage}
              onSendImageText={handleSendImageText}
              onSendDocumentText={handleSendDocumentText}
              onError={setError}
              openImagePickerSignal={openImagePickerSignal}
              openDocumentSignal={openDocumentSignal}
              startVoiceSignal={startVoiceSignal}
            />
          </div>
        </section>

        {/* Desktop / tablet results */}
        <section className="results-panel hidden md:flex flex-col glass-panel rounded-2xl p-4 min-h-0 overflow-hidden">
          <div className="flex-1 overflow-y-auto scrollbar-hide min-h-0">
            <MachineResults
              machines={visibleMachines}
              allMachinesCount={machines.length}
              listingFilter={listingFilter}
              listingCounts={listingCounts}
              onListingFilterChange={setListingFilter}
              loading={loading}
              compareSelection={compareIds}
              selectedMachineId={selectedMachineId}
              {...machineHandlers}
            />
          </div>
        </section>
      </main>

      {/* Mobile: floating view machines button */}
      {machines.length > 0 && (
        <button
          type="button"
          onClick={() => setMobileDrawerOpen(true)}
          className="md:hidden fixed bottom-4 left-1/2 -translate-x-1/2 z-[70] view-machines-btn flex items-center gap-2 px-4 py-2.5 rounded-full gradient-orange text-on-primary text-xs font-semibold shadow-xl shadow-primary/20 transition-transform duration-150 active:scale-95 focus-visible:ring-2 focus-visible:ring-primary/50"
          aria-label={`View ${machines.length} machines`}
        >
          View Machines ({machines.length})
        </button>
      )}

      <MachineDrawer
        open={mobileDrawerOpen}
        onClose={() => setMobileDrawerOpen(false)}
        machines={visibleMachines}
        allMachinesCount={machines.length}
        listingFilter={listingFilter}
        listingCounts={listingCounts}
        onListingFilterChange={setListingFilter}
        loading={loading}
        compareSelection={compareIds}
        selectedMachineId={selectedMachineId}
        {...machineHandlers}
      />

      {/* Compare action bar */}
      {compareSelection.length > 0 && (
        <div className="fixed bottom-5 md:bottom-5 left-1/2 -translate-x-1/2 z-[90] message-enter compare-bar mb-14 md:mb-0 max-w-[calc(100vw-2rem)]">
          <div className="flex items-center gap-3 bg-surface-container-highest border border-border-subtle rounded-2xl shadow-2xl px-4 py-3">
            <GitCompareArrows className="w-4 h-4 text-primary" />
            <span className="text-xs text-on-surface-variant">
              {compareSelection.length === 1
                ? "Select one more machine to compare"
                : "2 machines selected"}
            </span>
            <div className="flex items-center gap-1.5">
              {compareSelection.map((m) => (
                <span
                  key={m._id}
                  className="text-[10px] px-2 py-0.5 rounded-full bg-surface-container-high border border-border-subtle text-on-surface max-w-[120px] truncate"
                >
                  {m.name}
                </span>
              ))}
            </div>
            <button
              onClick={() =>
                compareSelection.length === 2 &&
                setModal({ type: "compare", a: compareSelection[0], b: compareSelection[1] })
              }
              disabled={compareSelection.length !== 2}
              className="text-xs font-semibold px-3 py-1.5 rounded-lg gradient-orange text-white disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              Compare
            </button>
            <button
              onClick={() => setCompareSelection([])}
              className="text-on-surface-variant hover:text-on-surface cursor-pointer"
              aria-label="Clear selection"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Modals */}
      {modal?.type === "details" && (
        <MachineDetailsModal machine={modal.machine} onClose={() => setModal(null)} />
      )}
      {modal?.type === "price" && (
        <PriceInsightModal machine={modal.machine} onClose={() => setModal(null)} />
      )}
      {modal?.type === "deal" && (
        <DealScoreModal machine={modal.machine} onClose={() => setModal(null)} />
      )}
      {modal?.type === "similar" && (
        <SimilarMachinesModal
          machine={modal.machine}
          onClose={() => setModal(null)}
          onViewDetails={(m) => setModal({ type: "details", machine: m })}
        />
      )}
      {modal?.type === "compare" && (
        <ComparePanel machineA={modal.a} machineB={modal.b} onClose={() => setModal(null)} />
      )}
      {modal?.type === "contact" && (
        <ContactOwnerModal machine={modal.machine} onClose={() => setModal(null)} />
      )}

      <SupportRequestModal
        open={supportModalOpen}
        onClose={() => setSupportModalOpen(false)}
        sessionId={sessionId}
        defaultIssueType={supportIssueType}
      />

      {limitModal && (
        <SessionLimitModal
          open
          onClose={() => setLimitModal(null)}
          limitType={limitModal.limitType}
          used={limitModal.used}
          limit={limitModal.limit}
          onNewChat={resetSession}
        />
      )}
    </div>
  );
}
