// ---------------------------------------------------------------------------
// Shared types for the Infra AI-Assistant for Marketplace frontend.
// These mirror the FastAPI backend's standardized response shapes.
// ---------------------------------------------------------------------------

/** Standard envelope returned by every backend endpoint. */
export interface ApiResponse<T = Record<string, unknown>> {
  success: boolean;
  message: string;
  data: T;
  error: unknown;
}

/** A machine listing as returned by the backend search/recommendation APIs. */
export interface Machine {
  id?: string;
  _id: string;
  name: string;
  category?: string;
  category_display?: string;
  city?: string;
  price_per_day?: number;
  rating?: number;
  description?: string;
  availability?: boolean;
  availability_status?: string;
  seller_name?: string;
  owner_name?: string;
  brand?: string;
  model?: string;
  image_url?: string;
  images?: string[];
  specifications?: Record<string, unknown>;
  listing_type?: string;
  rent_type?: string;
  security_deposit?: number | null;
  selling_price?: number | null;
  slug?: string | null;
  source?: "infraforge_real_db" | "seed_sample" | string;
  mobile_number?: string | null;
  contact_number?: string | null;
  seller_phone?: string | null;
  whatsapp_number?: string | null;
  final_score?: number;
  similarity_score?: number;
  recommendation_score?: number;
}

export interface HandoverAction {
  label: string;
  type: "call" | "whatsapp" | "request" | string;
  value?: string;
}

export interface HandoverPayload {
  enabled?: boolean;
  reason?: string;
  message?: string;
  actions?: HandoverAction[];
}

/** Active filters resolved by the chatbot for the current turn. */
export interface ChatFilters {
  category?: string | null;
  city?: string | null;
  max_price?: number | null;
}

/** Memory / fallback metadata returned alongside chat results. */
export interface ChatContext {
  used_previous_context?: boolean;
  used_image_context?: boolean;
  assistant_mode?: string;
  pending_clarification?: Record<string, unknown> | null;
  search_query?: string;
  fallback_used?: boolean;
  fallback_query?: string | null;
  intent?: string;
}

/** Payload portion of a /chat or /voice/chat response. */
export interface ChatData {
  advisor_message?: string | null;
  machines?: Machine[];
  filters?: ChatFilters;
  context?: ChatContext;
  suggestions?: string[];
  handover?: HandoverPayload | null;
  voice_input?: {
    original_voice_text?: string;
    original_transcription?: string;
    normalized_text?: string;
    enhanced_query?: string;
    text_understanding?: Record<string, unknown>;
  };
  [key: string]: unknown;
}

/** Payload portion of an /image-search success response. */
export interface ImageSearchData {
  match_type: "exact" | "broad" | "unknown" | string;
  detected_machine_type?: string | null;
  search_query?: string | null;
  suggested_categories?: string[];
  predictions?: Array<{ label?: string; score?: number }>;
  results?: Machine[];
}

/** A single chat bubble rendered in the conversation window. */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  timestamp: number;
  isError?: boolean;
  /** Optional metadata line shown above an assistant bubble (voice/image info). */
  meta?: string;
  advisorMessage?: string | null;
  filters?: ChatFilters | null;
  suggestions?: string[];
  handover?: HandoverPayload | null;
  assistantMode?: string;
  /** Object URL for an image thumbnail shown inside the bubble (image uploads). */
  imageUrl?: string;
  /** Attached document filename shown in user bubble. */
  documentName?: string;
}

/**
 * Remembered context from the last uploaded image, used to resolve follow-up
 * questions like "is this available in jaipur" → "crane in jaipur".
 */
export interface ImageContext {
  detected_machine_type: string;
  suggested_categories: string[];
  timestamp: number;
}

export type AssistantMode = "text" | "voice" | "image" | "rag";

export type BackendStatus = "checking" | "connected" | "disconnected";

// --- Feature-specific result shapes -----------------------------------------

export interface CompareResult {
  better_for_budget: string;
  better_rating: string;
  overall_recommendation: string;
  machine_1: Machine;
  machine_2: Machine;
}

export interface PriceInsightResult {
  machine_name?: string;
  category?: string;
  city?: string;
  current_price?: number | null;
  average_market_price?: number | null;
  price_difference?: number;
  percentage_difference?: number;
  price_status?: string;
  recommendation?: string;
  similar_machine_count?: number;
}

export interface DealScoreResult {
  machine_name?: string;
  deal_score?: number | null;
  deal_label?: string;
  reason?: string;
}

export interface RagAnswer {
  question?: string;
  answer?: string;
  answer_source?: string;
  similarity_score?: number;
}
