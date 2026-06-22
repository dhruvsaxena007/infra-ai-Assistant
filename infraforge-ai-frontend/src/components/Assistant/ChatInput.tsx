import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { SendHorizonal, X, ImageIcon, FileText } from "lucide-react";
import VoiceRecorder from "./VoiceRecorder";
import ImagePicker, { type ImageSource } from "./ImagePicker";
import DocumentPicker from "./DocumentPicker";
import {
  buildDraftAfterInsert,
  focusInputWithCaret,
  type InsertDraftOptions,
} from "../../utils/suggestionDraft";
import { IMAGE_SEARCH_MAX_BYTES } from "../../api/assistantApi";

export interface ChatInputHandle {
  insertDraft: (text: string, options?: InsertDraftOptions) => void;
  focus: () => void;
}

interface Props {
  disabled: boolean;
  uploading?: boolean;
  onSendText: (text: string) => void;
  onSendVoice: (file: File) => void;
  onSendImage: (file: File, source: ImageSource) => void;
  onSendImageText: (file: File, text: string, source: ImageSource) => void;
  onSendDocumentText: (file: File, text: string) => void;
  onError: (message: string) => void;
  openImagePickerSignal?: number;
  openDocumentSignal?: number;
  startVoiceSignal?: number;
}

const ChatInput = forwardRef<ChatInputHandle, Props>(function ChatInput(
  {
    disabled,
    uploading = false,
    onSendText,
    onSendVoice,
    onSendImage,
    onSendImageText,
    onSendDocumentText,
    onError,
    openImagePickerSignal,
    openDocumentSignal,
    startVoiceSignal,
  },
  ref,
) {
  const [value, setValue] = useState("");
  const [recording, setRecording] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const prevDisabledRef = useRef(disabled);

  useImperativeHandle(ref, () => ({
    insertDraft(text: string, options?: InsertDraftOptions) {
      const el = inputRef.current;
      const start = el?.selectionStart ?? value.length;
      const end = el?.selectionEnd ?? value.length;
      const { value: next, caret } = buildDraftAfterInsert(
        value,
        text,
        start,
        end,
        options,
      );
      setValue(next);
      focusInputWithCaret(el, caret);
    },
    focus() {
      inputRef.current?.focus();
    },
  }));

  useEffect(() => {
    const wasDisabled = prevDisabledRef.current;
    prevDisabledRef.current = disabled;
    if (wasDisabled && !disabled && !recording) {
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [disabled, recording]);

  const [pendingImageFile, setPendingImageFile] = useState<File | null>(null);
  const [pendingImagePreviewUrl, setPendingImagePreviewUrl] = useState<string | null>(null);
  const [pendingImageSource, setPendingImageSource] = useState<ImageSource>("upload");

  const [pendingDocumentFile, setPendingDocumentFile] = useState<File | null>(null);

  useEffect(() => {
    return () => {
      if (pendingImagePreviewUrl) URL.revokeObjectURL(pendingImagePreviewUrl);
    };
  }, [pendingImagePreviewUrl]);

  const handlePickImage = (file: File, source: ImageSource) => {
    if (!file.type.startsWith("image/")) {
      onError("Please select a valid image file (jpg, png or webp).");
      return;
    }
    if (file.size > IMAGE_SEARCH_MAX_BYTES) {
      onError("Image is too large. Maximum size is 8 MB.");
      return;
    }
    if (pendingImagePreviewUrl) URL.revokeObjectURL(pendingImagePreviewUrl);
    setPendingDocumentFile(null);
    setPendingImageFile(file);
    setPendingImagePreviewUrl(URL.createObjectURL(file));
    setPendingImageSource(source);
  };

  const handlePickDocument = (file: File) => {
    const ok =
      file.type === "application/pdf" ||
      file.type.startsWith("text/") ||
      file.name.endsWith(".pdf") ||
      file.name.endsWith(".txt") ||
      file.name.endsWith(".doc") ||
      file.name.endsWith(".docx");
    if (!ok) {
      onError("Please attach a PDF or text document.");
      return;
    }
    clearPendingImage();
    setPendingDocumentFile(file);
  };

  const clearPendingImage = () => {
    if (pendingImagePreviewUrl) URL.revokeObjectURL(pendingImagePreviewUrl);
    setPendingImageFile(null);
    setPendingImagePreviewUrl(null);
  };

  const clearPendingDocument = () => setPendingDocumentFile(null);

  const submit = () => {
    if (disabled || uploading) return;
    const text = value.trim();

    if (pendingDocumentFile) {
      if (!text) {
        onError("Type a question about your document, then send.");
        return;
      }
      onSendDocumentText(pendingDocumentFile, text);
      setPendingDocumentFile(null);
      setValue("");
      return;
    }

    if (pendingImageFile) {
      if (text) onSendImageText(pendingImageFile, text, pendingImageSource);
      else onSendImage(pendingImageFile, pendingImageSource);
      setPendingImageFile(null);
      setPendingImagePreviewUrl(null);
      setValue("");
      return;
    }

    if (!text) return;
    onSendText(text);
    setValue("");
  };

  const canSend =
    !disabled &&
    !uploading &&
    (!!pendingImageFile || !!value.trim() || (!!pendingDocumentFile && !!value.trim()));

  const iconBtn =
    "h-10 w-10 sm:h-11 sm:w-11 flex items-center justify-center rounded-xl bg-surface-container-high/80 border border-border-subtle text-on-surface-variant hover:text-on-surface hover:border-primary/30 transition-all duration-150 focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-40";

  const placeholder = pendingDocumentFile
    ? "Ask about this document…"
    : pendingImageFile
      ? "Ask about this image…"
      : "Ask about machines… e.g. excavator in jaipur";

  return (
    <div className="chat-input-bar flex flex-col gap-2">
      {!recording && pendingImagePreviewUrl && (
        <div className="flex items-center gap-3 self-start image-preview-chip max-w-full message-enter">
          <div className="relative w-14 h-14 rounded-lg overflow-hidden flex-shrink-0 border border-primary/20">
            <img
              src={pendingImagePreviewUrl}
              alt="Selected machine"
              className="w-full h-full object-cover"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/40 to-transparent" />
            <ImageIcon className="absolute bottom-1 left-1 w-3 h-3 text-white/80" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs text-on-surface truncate max-w-[200px]">
              {pendingImageFile?.name || "Selected image"}
            </div>
            <div className="text-[10px] text-primary/80">Ready to send</div>
          </div>
          <button
            type="button"
            onClick={clearPendingImage}
            disabled={disabled}
            className="h-8 w-8 flex items-center justify-center rounded-full bg-surface-container-highest text-on-surface-variant hover:text-on-surface transition-colors focus-visible:ring-2 focus-visible:ring-primary/40"
            aria-label="Remove image"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {!recording && pendingDocumentFile && (
        <div className="flex items-center gap-3 self-start image-preview-chip max-w-full message-enter">
          <div className="w-14 h-14 rounded-lg flex items-center justify-center flex-shrink-0 border border-tertiary/30 bg-tertiary/10">
            <FileText className="w-6 h-6 text-tertiary" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs text-on-surface truncate max-w-[220px]">
              {pendingDocumentFile.name}
            </div>
            <div className="text-[10px] text-tertiary/90">Document attached — add your question</div>
          </div>
          <button
            type="button"
            onClick={clearPendingDocument}
            disabled={disabled}
            className="h-8 w-8 flex items-center justify-center rounded-full bg-surface-container-highest text-on-surface-variant hover:text-on-surface transition-colors"
            aria-label="Remove document"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      <div className="flex items-end gap-1.5 sm:gap-2">
        {!recording && (
          <textarea
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={1}
            disabled={disabled}
            placeholder={placeholder}
            aria-label="Chat message"
            className="chat-textarea flex-1 resize-none max-h-28 min-h-[44px] rounded-xl px-3.5 py-2.5 text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none disabled:opacity-50 scrollbar-hide"
          />
        )}

        <VoiceRecorder
          disabled={disabled}
          onRecorded={onSendVoice}
          onError={onError}
          onRecordingChange={setRecording}
          startSignal={startVoiceSignal}
        />

        {!recording && (
          <>
            <ImagePicker
              disabled={disabled}
              onPick={handlePickImage}
              openSignal={openImagePickerSignal}
            />
            <DocumentPicker
              disabled={disabled}
              onPick={handlePickDocument}
              openSignal={openDocumentSignal}
            />
            <button
              type="button"
              onClick={submit}
              disabled={!canSend}
              className="send-btn h-10 w-10 sm:h-11 sm:w-11 flex items-center justify-center rounded-xl gradient-orange text-on-primary disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-all duration-150 active:scale-95 focus-visible:ring-2 focus-visible:ring-primary/50"
              title="Send message"
              aria-label="Send message"
            >
              <SendHorizonal className="w-4 h-4" />
            </button>
          </>
        )}
      </div>
    </div>
  );
});

export default ChatInput;
