import React, { useRef, useState } from "react";
import { FileText, Upload, HelpCircle, Sparkles, Loader2 } from "lucide-react";
import {
  ragAsk,
  ragUploadPdf,
  ragUploadText,
  BackendUnreachableError,
} from "../../api/assistantApi";
import type { RagAnswer } from "../../types";
import ErrorBanner from "./ErrorBanner";

/** Document Q&A: upload text or PDF into the backend RAG store, then ask questions. */
export default function RagPanel() {
  const pdfRef = useRef<HTMLInputElement>(null);

  const [text, setText] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<RagAnswer | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"text" | "pdf" | "ask" | null>(null);

  const handleError = (e: unknown, fallback: string) => {
    if (e instanceof BackendUnreachableError) setError(e.message);
    else setError(fallback);
  };

  const submitText = async () => {
    if (!text.trim()) return;
    setBusy("text");
    setError(null);
    setStatus(null);
    try {
      const res = await ragUploadText(text.trim());
      if (res.success) {
        setStatus(`Text added — ${res.data.chunks_added} chunk(s) stored.`);
        setText("");
      } else {
        setError(res.message || "Failed to add text.");
      }
    } catch (e) {
      handleError(e, "Failed to upload text.");
    } finally {
      setBusy(null);
    }
  };

  const submitPdf = async (file: File) => {
    setBusy("pdf");
    setError(null);
    setStatus(null);
    try {
      const res = await ragUploadPdf(file);
      if (res.success) {
        setStatus(`PDF "${res.data.file_name}" added — ${res.data.chunks_added} chunk(s) stored.`);
      } else {
        setError(res.message || "Failed to upload PDF.");
      }
    } catch (e) {
      handleError(e, "Failed to upload PDF.");
    } finally {
      setBusy(null);
      if (pdfRef.current) pdfRef.current.value = "";
    }
  };

  const submitQuestion = async () => {
    if (!question.trim()) return;
    setBusy("ask");
    setError(null);
    setAnswer(null);
    try {
      const res = await ragAsk(question.trim());
      if (res.success) {
        setAnswer(res.data);
      } else {
        setError(res.message || "Could not answer the question.");
      }
    } catch (e) {
      handleError(e, "Failed to ask question.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <FileText className="w-4 h-4 text-primary" />
        <h3 className="font-semibold text-sm text-on-surface">Document Q&amp;A</h3>
      </div>
      <p className="text-xs text-on-surface-variant leading-relaxed">
        Add documents (text or PDF) to the assistant's knowledge base, then ask
        questions answered from those documents.
      </p>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {status && (
        <div className="text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">
          {status}
        </div>
      )}

      {/* Upload text */}
      <div className="space-y-2">
        <label className="text-[11px] font-mono uppercase tracking-wider text-on-surface-variant">
          1 · Upload text
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          placeholder="Paste any document text here…"
          className="w-full resize-none bg-surface-container-high border border-border-subtle rounded-xl px-3 py-2.5 text-sm text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none focus:border-primary/50 scrollbar-hide"
        />
        <button
          onClick={submitText}
          disabled={busy !== null || !text.trim()}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-surface-container-highest border border-border-subtle text-xs font-medium text-on-surface hover:border-primary/40 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {busy === "text" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
          Add text
        </button>
      </div>

      {/* Upload PDF */}
      <div className="space-y-2">
        <label className="text-[11px] font-mono uppercase tracking-wider text-on-surface-variant">
          2 · Upload PDF
        </label>
        <input
          ref={pdfRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) submitPdf(f);
          }}
        />
        <button
          onClick={() => pdfRef.current?.click()}
          disabled={busy !== null}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-surface-container-highest border border-border-subtle text-xs font-medium text-on-surface hover:border-primary/40 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {busy === "pdf" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
          Choose PDF
        </button>
      </div>

      {/* Ask */}
      <div className="space-y-2">
        <label className="text-[11px] font-mono uppercase tracking-wider text-on-surface-variant">
          3 · Ask a question
        </label>
        <div className="flex items-end gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitQuestion();
            }}
            placeholder="Which machine is used for excavation?"
            className="flex-1 bg-surface-container-high border border-border-subtle rounded-xl px-3 py-2.5 text-sm text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none focus:border-primary/50"
          />
          <button
            onClick={submitQuestion}
            disabled={busy !== null || !question.trim()}
            className="h-10 px-4 flex items-center gap-2 rounded-xl gradient-orange text-white shadow-lg text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer active:scale-95 transition-all"
          >
            {busy === "ask" ? <Loader2 className="w-4 h-4 animate-spin" /> : <HelpCircle className="w-4 h-4" />}
            Ask
          </button>
        </div>
      </div>

      {answer && (
        <div className="bg-surface-container-high border border-border-subtle rounded-xl p-4 space-y-2 message-enter">
          <div className="flex items-center gap-2 text-primary">
            <Sparkles className="w-4 h-4" />
            <span className="text-xs font-semibold">Answer</span>
            {answer.answer_source && (
              <span className="ml-auto text-[10px] font-mono px-2 py-0.5 rounded-full bg-surface-container-highest border border-border-subtle text-on-surface-variant">
                {answer.answer_source}
                {answer.similarity_score != null ? ` · ${Number(answer.similarity_score).toFixed(2)}` : ""}
              </span>
            )}
          </div>
          <p className="text-sm text-on-surface leading-relaxed whitespace-pre-wrap">
            {answer.answer}
          </p>
        </div>
      )}
    </div>
  );
}
