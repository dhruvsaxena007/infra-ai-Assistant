import React, { useCallback, useEffect, useMemo, useState } from "react";
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
  ImageContext,
  ImageSearchData,
  Machine,
} from "../../types";
import {
  API_BASE_URL,
  BackendUnreachableError,
  checkHealth,
  sendChatMessage,
  sendImageSearch,
  sendVoiceChat,
  ragUploadPdf,
  ragUploadText,
  ragAsk,
} from "../../api/assistantApi";
import SupportRequestModal from "./SupportRequestModal";
import type { ImageSource } from "./ImagePicker";

import ChatWindow from "./ChatWindow";
import ChatInput from "./ChatInput";
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

const SESSION_KEY = "infraforge_session_id";
const IMAGE_CONTEXT_KEY = "infraforge_last_image_context";

function loadSessionId(): string {
  try {
    const existing = localStorage.getItem(SESSION_KEY);
    if (existing) return existing;
  } catch {
    /* localStorage may be unavailable */
  }
  const fresh = `frontend_${Math.random().toString(36).slice(2, 10)}`;
  try {
    localStorage.setItem(SESSION_KEY, fresh);
  } catch {
    /* ignore */
  }
  return fresh;
}

function loadImageContext(): ImageContext | null {
  try {
    const raw = localStorage.getItem(IMAGE_CONTEXT_KEY);
    if (raw) return JSON.parse(raw) as ImageContext;
  } catch {
    /* ignore */
  }
  return null;
}

// Strong demonstratives that clearly mean "the machine from the image".
const STRONG_REFERENCE_TRIGGERS = [
  "this type", "this machine", "this one", "is this", "this",
  "same machine", "same type", "same",
  "ye wali machine", "ye wali", "ye machine", "yeh machine", "ye", "yeh",
  "kya ye", "kya yeh",
];

// Weak triggers only count as image references when an image context exists
// (so a generic "machines available in delhi" is not hijacked).
const WEAK_REFERENCE_TRIGGERS = ["available"];

// Phrases stripped out when injecting image context, so the resulting query is
// clean ("is this type of machine available in jaipur" -> "available in jaipur").
const IMAGE_REFERENCE_PHRASES = [
  "is this type of machine", "this type of machine", "type of machine",
  "is this machine", "this machine", "is this", "this type", "this one", "this",
  "same machine", "same type", "same",
  "ye wali machine", "ye wali", "ye machine", "yeh machine",
  "kya ye", "kya yeh", "ye", "yeh",
];

// If the user explicitly names a machine, do NOT override with image context.
const EXPLICIT_MACHINE_WORDS = [
  "excavator", "digger", "poclain", "jcb", "3dx", "4dx", "backhoe",
  "hydra", "crane", "bulldozer", "dozer", "road roller", "roller",
  "dump truck", "dumper", "tipper", "concrete mixer", "mixer",
  "grader", "wheel loader", "loader",
];

function matchesWord(text: string, word: string): boolean {
  return new RegExp(`(^|[^a-z0-9])${word}([^a-z0-9]|$)`, "i").test(text);
}

function hasStrongReference(text: string): boolean {
  return STRONG_REFERENCE_TRIGGERS.some((w) => matchesWord(text, w));
}

function hasWeakReference(text: string): boolean {
  return WEAK_REFERENCE_TRIGGERS.some((w) => matchesWord(text, w));
}

function mentionsExplicitMachine(text: string): boolean {
  return EXPLICIT_MACHINE_WORDS.some((w) => matchesWord(text, w));
}

/** Build a backend query from a follow-up question + remembered image type. */
function injectImageContext(text: string, machineType: string): string {
  let t = ` ${text.toLowerCase()} `;
  for (const phrase of [...IMAGE_REFERENCE_PHRASES].sort((a, b) => b.length - a.length)) {
    t = t.replace(new RegExp(`(^|[^a-z0-9])${phrase}([^a-z0-9]|$)`, "gi"), " ");
  }
  t = t.replace(/\s+/g, " ").trim();
  const combined = `${machineType} ${t}`.replace(/\s+/g, " ").trim();
  return combined || machineType;
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
  "Search machine": "excavator in jaipur",
  "Upload image": "",
  "Voice search": "",
  "Ask recommendation": "road project ke liye best machine kaunsi hai?",
  "Talk to support": "I need help from support",
  "Order issue": "I ordered a machine and I have a problem",
  "Booking issue": "booking me issue hai",
  "Refund/Return": "I want refund",
  "Payment issue": "payment failed amount deducted",
  "Contact support": "I need help from support",
  "Upload document": "",
  "Share order ID": "My order ID is ",
  "Booking policy": "What is the rental cancellation policy?",
};

export default function AssistantPage() {
  const [sessionId, setSessionId] = useState<string>(loadSessionId);
  const [openImagePickerSignal, setOpenImagePickerSignal] = useState(0);
  const [openDocumentSignal, setOpenDocumentSignal] = useState(0);
  const [startVoiceSignal, setStartVoiceSignal] = useState(0);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("Thinking");
  const [error, setError] = useState<string | null>(null);

  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");
  const [compareSelection, setCompareSelection] = useState<Machine[]>([]);
  const [modal, setModal] = useState<ActiveModal>(null);

  const [lastImageContext, setLastImageContext] = useState<ImageContext | null>(loadImageContext);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [supportModalOpen, setSupportModalOpen] = useState(false);
  const [supportIssueType, setSupportIssueType] = useState("");

  // --- Backend health -------------------------------------------------------
  const runHealthCheck = useCallback(async () => {
    setBackendStatus("checking");
    try {
      const res = await checkHealth();
      setBackendStatus(res.success ? "connected" : "disconnected");
    } catch {
      setBackendStatus("disconnected");
    }
  }, []);

  useEffect(() => {
    runHealthCheck();
    const id = setInterval(runHealthCheck, 30000);
    return () => clearInterval(id);
  }, [runHealthCheck]);

  // --- Helpers --------------------------------------------------------------
  const pushMessage = (m: ChatMessage) => setMessages((prev) => [...prev, m]);

  const pushAssistantError = (text: string, meta?: string) =>
    pushMessage({
      id: `err-${Date.now()}`,
      role: "assistant",
      text,
      timestamp: Date.now(),
      isError: true,
      meta,
    });

  const pushAssistantInfo = (text: string, meta?: string) =>
    pushMessage({
      id: `i-${Date.now()}`,
      role: "assistant",
      text,
      timestamp: Date.now(),
      meta,
    });

  const rememberImageContext = (data: ImageSearchData): string | null => {
    const type = data.detected_machine_type || data.suggested_categories?.[0] || null;
    if (!type) return null;
    const ctx: ImageContext = {
      detected_machine_type: type,
      suggested_categories: data.suggested_categories?.length ? data.suggested_categories : [type],
      timestamp: Date.now(),
    };
    setLastImageContext(ctx);
    try {
      localStorage.setItem(IMAGE_CONTEXT_KEY, JSON.stringify(ctx));
    } catch {
      /* ignore */
    }
    return type;
  };

  const extractMachinesFromResponse = (data: Record<string, unknown>): Machine[] => {
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
  const applyChatResponse = (
    res: Awaited<ReturnType<typeof sendChatMessage>>,
  ) => {
    if (res.success) {
      const data = res.data ?? {};
      const mode = data.context?.assistant_mode ?? data.assistant_mode;
      pushMessage({
        id: `a-${Date.now()}`,
        role: "assistant",
        text: res.message,
        timestamp: Date.now(),
        advisorMessage: data.advisor_message ?? null,
        filters: data.filters ?? null,
        suggestions: Array.isArray(data.suggestions) ? data.suggestions : undefined,
        handover: data.handover ?? null,
        assistantMode: typeof mode === "string" ? mode : undefined,
      });
      const ctx = data.context as Record<string, unknown> | undefined;
      if (!ctx?.preserve_machine_panel) {
        const pool = extractMachinesFromResponse(data as Record<string, unknown>);
        setMachines(pool);
      }
    } else {
      pushAssistantError(res.message || "The assistant could not process that request.");
    }
  };

  const handleNetworkError = (e: unknown, fallback: string) => {
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

    // The bubble always shows what the user actually typed.
    pushMessage({ id: `u-${Date.now()}`, role: "user", text, timestamp: Date.now() });

    // Image context enriches the query when available; session memory on the
    // backend handles "this/ye" follow-ups about last shown machines.
    const explicit = mentionsExplicitMachine(text);
    const strong = hasStrongReference(text);
    const weak = hasWeakReference(text);
    const hasImageCtx = !!lastImageContext?.detected_machine_type;
    const usesImageRef =
      !explicit && (strong || (weak && hasImageCtx)) && hasImageCtx;

    const messageToSend =
      usesImageRef && lastImageContext
        ? injectImageContext(text, lastImageContext.detected_machine_type)
        : text;

    setLoadingLabel("Thinking");
    setLoading(true);
    try {
      const res = await sendChatMessage(sessionId, messageToSend);
      applyChatResponse(res);
    } catch (e) {
      handleNetworkError(e, "Something went wrong while sending your message.");
    } finally {
      setLoading(false);
    }
  };

  // --- Voice chat -----------------------------------------------------------
  const handleSendVoice = async (file: File) => {
    setError(null);
    const userMsgId = `u-${Date.now()}`;
    pushMessage({
      id: userMsgId,
      role: "user",
      text: "🎙️ Voice message",
      timestamp: Date.now(),
    });
    setLoadingLabel("Processing voice");
    setLoading(true);
    try {
      const res = await sendVoiceChat(sessionId, file);
      if (res.success) {
        const data = res.data ?? {};
        const transcript = data.voice_input?.original_voice_text;
        // Replace the placeholder user bubble with the actual transcript.
        if (transcript) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === userMsgId ? { ...m, text: `🎙️ ${transcript}` } : m,
            ),
          );
        }
        applyChatResponse(res);
      } else {
        pushAssistantError(res.message || "Voice transcription failed. Please try again.");
      }
    } catch (e) {
      handleNetworkError(e, "Something went wrong while processing your voice message.");
    } finally {
      setLoading(false);
    }
  };

  // --- Image search (image only) -------------------------------------------
  const handleSendImage = async (file: File, _source: ImageSource = "upload") => {
    setError(null);
    const previewUrl = URL.createObjectURL(file);
    pushMessage({
      id: `u-${Date.now()}`,
      role: "user",
      text: "Uploaded an image for machine search",
      timestamp: Date.now(),
      imageUrl: previewUrl,
    });
    setLoadingLabel("Analyzing image");
    setLoading(true);
    try {
      const res = await sendImageSearch(file, sessionId);
      if (res.success) {
        const data = res.data;
        rememberImageContext(data);
        const parts: string[] = [];
        if (data.detected_machine_type)
          parts.push(`Detected machine type: ${titleCase(data.detected_machine_type)}`);
        parts.push(`Match: ${data.match_type}`);
        if (data.suggested_categories?.length)
          parts.push(`Categories: ${data.suggested_categories.join(", ")}`);
        pushMessage({
          id: `a-${Date.now()}`,
          role: "assistant",
          text: `${res.message}\n\n${parts.join(" · ")}`,
          timestamp: Date.now(),
          meta: "Image search",
        });
        const pool = extractMachinesFromResponse(data as unknown as Record<string, unknown>);
        setMachines(pool);
        if (data.match_type === "image_clarification") {
          pushAssistantInfo(res.message, "Image clarification");
        }
      } else {
        setMachines([]);
        pushAssistantError(
          res.message || "Could not identify the machine in that image. Try a clearer photo.",
          "Image search",
        );
      }
    } catch (e) {
      handleNetworkError(e, "Something went wrong while searching by image.");
    } finally {
      setLoading(false);
    }
  };

  // --- Document + text (inline RAG in chat) ---------------------------------
  const handleSendDocumentText = async (file: File, text: string) => {
    setError(null);
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
        const up = await ragUploadText(body);
        if (!up.success) {
          pushAssistantError(up.message || "Could not upload document text.");
          return;
        }
      } else {
        const up = await ragUploadPdf(file);
        if (!up.success) {
          pushAssistantError(up.message || "Could not upload PDF.");
          return;
        }
      }
      setLoadingLabel("Answering from document");
      const ans = await ragAsk(text);
      if (ans.success) {
        const answer = ans.data?.answer || ans.message || "No answer found in document.";
        pushMessage({
          id: `a-${Date.now()}`,
          role: "assistant",
          text: answer,
          timestamp: Date.now(),
          assistantMode: "document_qa",
          meta: "Document Q&A",
        });
      } else {
        pushAssistantError(ans.message || "Could not answer from document.");
      }
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

  // --- Image + text (ChatGPT-style combined send) ---------------------------
  const handleSendImageText = async (
    file: File,
    text: string,
    _source: ImageSource = "upload",
  ) => {
    setError(null);
    const previewUrl = URL.createObjectURL(file);
    pushMessage({
      id: `u-${Date.now()}`,
      role: "user",
      text,
      timestamp: Date.now(),
      imageUrl: previewUrl,
    });
    setLoadingLabel("Analyzing image");
    setLoading(true);
    try {
      // 1) Identify the machine in the image.
      const imgRes = await sendImageSearch(file, sessionId);
      if (!imgRes.success) {
        pushAssistantError(
          imgRes.message || "Could not identify the machine in that image. Try a clearer photo.",
          "Image search",
        );
        return;
      }

      const data = imgRes.data;
      const detected = rememberImageContext(data);

      pushAssistantInfo(
        detected
          ? `Detected machine type: ${titleCase(detected)}`
          : "I could not confidently detect the machine type from that image.",
        "Image search",
      );

      // 2) If we know the type, combine it with the question and ask /chat.
      if (!detected) {
        setMachines(Array.isArray(data.results) ? data.results : []);
        return;
      }

      const query = injectImageContext(text, detected);
      setLoadingLabel(`Searching ${titleCase(detected)}`);
      const chatRes = await sendChatMessage(sessionId, query);
      applyChatResponse(chatRes);
    } catch (e) {
      handleNetworkError(e, "Something went wrong while searching by image.");
    } finally {
      setLoading(false);
    }
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

  const handleSuggestionClick = (chip: string) => {
    if (chip === "Upload image") {
      setOpenImagePickerSignal((n) => n + 1);
      return;
    }
    if (chip === "Voice search") {
      setStartVoiceSignal((n) => n + 1);
      return;
    }
    if (chip === "Document Q&A" || chip === "Upload document") {
      setOpenDocumentSignal((n) => n + 1);
      return;
    }
    const prompt = SUGGESTION_PROMPTS[chip] || chip;
    if (prompt) void handleSendText(prompt);
  };

  // --- Session controls -----------------------------------------------------
  const clearChat = () => {
    setMessages([]);
    setMachines([]);
    setCompareSelection([]);
    setError(null);
  };

  const resetSession = () => {
    const fresh = `frontend_${Math.random().toString(36).slice(2, 10)}`;
    try {
      localStorage.setItem(SESSION_KEY, fresh);
      localStorage.removeItem(IMAGE_CONTEXT_KEY);
    } catch {
      /* ignore */
    }
    setSessionId(fresh);
    setLastImageContext(null);
    clearChat();
  };

  // --- Render ---------------------------------------------------------------
  const machineHandlers = {
    onViewDetails: (m: Machine) => setModal({ type: "details", machine: m }),
    onToggleCompare: toggleCompare,
    onPriceInsight: (m: Machine) => setModal({ type: "price", machine: m }),
    onDealScore: (m: Machine) => setModal({ type: "deal", machine: m }),
    onSimilar: (m: Machine) => setModal({ type: "similar", machine: m }),
    onContactOwner: (m: Machine) => setModal({ type: "contact", machine: m }),
  };

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
              Infra <span className="text-primary">AI-Assistant</span>
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
            message={`Backend not reachable at ${API_BASE_URL}. Start it with: uvicorn app.main:app --reload`}
            onDismiss={() => setError(null)}
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
              disabled={loading}
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
              machines={machines}
              loading={loading}
              compareSelection={compareIds}
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
        machines={machines}
        loading={loading}
        compareSelection={compareIds}
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
    </div>
  );
}
