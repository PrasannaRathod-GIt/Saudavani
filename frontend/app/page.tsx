"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { REC_LABEL, useSilenceRecorder } from "./useSilenceRecorder";

/*
 * SaudaVani farmer-facing page.
 * Contract checked against the uploaded FastAPI main.py:
 *   GET  /health
 *   GET  /api/session/{session_id}
 *   POST /api/voice/process (multipart/form-data)
 *   WS   /ws/trade/{session_id}
 *
 * Deal actions remain in the conversation/backend. No buyer/admin controls are
 * exposed here. Escrow is always a simulation; actual money transferred is ₹0.
 */

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
const WS_BASE = API_BASE.replace(/^http/i, "ws");
const REQUEST_TIMEOUT_MS = 180_000;
const SESSION_STORAGE_KEY = "saudavani_session_id";

const LANGUAGE_OPTIONS = [
  { value: "mr-IN", label: "मराठी · Marathi" },
  { value: "hi-IN", label: "हिन्दी · Hindi" },
  { value: "hinglish", label: "Hinglish" },
] as const;

type LanguageHint = (typeof LANGUAGE_OPTIONS)[number]["value"];
type Phase = "idle" | "processing" | "speaking";
type UnknownRecord = Record<string, unknown>;

type QualityState = Record<string, unknown>;

type PublicOffer = {
  price_per_quintal?: number | null;
  quantity_quintals?: number | null;
  buyer_id?: string | null;
  source?: string | null;
  proposed_by?: string | null;
  verified?: boolean;
  active?: boolean;
  status?: string | null;
  round?: number | null;
  buyer_confirmed?: boolean;
  reported_at?: string | null;
  submitted_at?: string | null;
  proposed_at?: string | null;
  expired_at?: string | null;
};

type ActiveOffer = {
  price_per_quintal?: number | null;
  quantity_quintals?: number | null;
  gross_value?: number | null;
  source?: string | null;
  proposed_by?: string | null;
  verified?: boolean;
  status?: string | null;
  offer_version?: number | null;
  expires_at?: string | null;
};

type FallbackRecord = {
  market?: string | null;
  variety?: string | null;
  modal_price?: number | null;
  min_price?: number | null;
  max_price?: number | null;
};

type PricingState = {
  available?: boolean | null;
  source?: string | null;
  source_url?: string | null;
  as_of?: string | null;
  market_scope?: string | null;
  market_requested?: string | null;
  modal_reference?: number | null;
  modal_reference_label?: string | null;
  reference_type?: "market_actual" | "calculated_median" | "fallback_record" | string | null;
  official_market_modal?: number | null;
  calculated_median_modal?: number | null;
  district_median_modal?: number | null;
  fair_price_low?: number | null;
  fair_price_high?: number | null;
  strong_target_price?: number | null;
  modal_spread_low?: number | null;
  modal_spread_high?: number | null;
  lowest_market_min?: number | null;
  highest_market_max?: number | null;
  range_method?: string | null;
  stale?: boolean | null;
  status?: string | null;
  variety_match?: boolean | null;
  market_matched?: boolean | null;
  market_fallback?: boolean | null;
  variety_fallback?: boolean | null;
  varieties_combined?: number | null;
  fallback_record?: FallbackRecord | null;
  from_cache?: boolean | null;
  record_count?: number | null;
  market_count?: number | null;
  gross_value_for_offer?: number | null;
  price_unit?: string | null;
};

type LockedDeal = {
  status?: string;
  agreement_status?: string;
  voucher_id?: string;
  commodity?: string;
  commodity_id?: string;
  product_form?: string | null;
  variety?: string;
  quality?: QualityState;
  quantity_quintals?: number;
  price_per_quintal?: number;
  gross_amount_inr?: number;
  advance_amount_demo_estimate_inr?: number;
  remaining_amount_demo_estimate_inr?: number;
  advance_percent_demo_calculation?: number;
  advance_is_simulated?: boolean;
  district?: string;
  market?: string;
  offer_version?: number;
  price_reference_date?: string | null;
  locked_at?: string;
  money_moved?: boolean;
  notice?: string;
};

type EscrowAuditEvent = {
  event?: string;
  at?: string;
  detail?: string;
};

type SimulatedEscrow = {
  escrow_id?: string;
  is_simulation?: boolean;
  status?: string;
  simulated_funds_locked?: boolean;
  simulated_amount_inr?: number;
  actual_money_transferred_inr?: number;
  currency?: string;
  voucher_id?: string;
  offer_version?: number;
  created_at?: string;
  funds_locked_at?: string;
  released_at?: string | null;
  cleared_at?: string | null;
  notice?: string;
  audit_events?: EscrowAuditEvent[];
};

type BackendPublicState = {
  session_id?: string;
  farmer_name?: string | null;
  commodity_id?: string | null;
  crop?: string | null;
  product_form?: string | null;
  variety?: string | null;
  quantity?: number | null;
  market?: string | null;
  district?: string | null;
  quality?: QualityState;
  deal_status?: string;
  waiting_for?: string | null;
  buyer_offer?: PublicOffer | null;
  reported_buyer_quote?: PublicOffer | null;
  buyer_offer_status?: string | null;
  active_offer?: ActiveOffer | null;
  offer_version?: number;
  farmer_counter_price?: number | null;
  negotiation_round?: number;
  negotiation_rounds?: number;
  farmer_confirmed?: boolean;
  buyer_confirmed?: boolean;
  pricing?: PricingState;
  locked_deal?: LockedDeal | null;
  simulated_escrow?: SimulatedEscrow | null;
  language?: string | null;
  turns?: number;
};

type VoiceDealState = {
  deal_status?: string;
  crop?: string | null;
  commodity_id?: string | null;
  variety?: string | null;
  quantity?: number | null;
  district?: string | null;
  market?: string | null;
  buyer_offer?: PublicOffer | null;
  reported_buyer_quote?: PublicOffer | null;
  active_offer?: ActiveOffer | null;
  offer_version?: number;
  negotiation_round?: number;
  farmer_confirmed?: boolean;
  buyer_confirmed?: boolean;
  voucher?: LockedDeal | null;
};

type VoiceResponse = {
  session_id: string;
  session_rotated?: boolean;
  previous_session_id?: string | null;
  user_transcript?: string;
  stt_source?: string;
  language?: { key?: string; label?: string; code?: string };
  tts_language?: string;
  intent?: string;
  agent_text?: string;
  agent_source?: string;
  audio_status?: string;
  audio_source?: string;
  audio_error?: string;
  audio_http_status?: number | null;
  audio_base64?: string | null;
  audio_mime_type?: string;
  pricing?: PricingState;
  deal_state?: VoiceDealState;
  next_action?: string | null;
  latency_ms?: { stt?: number | null; agent?: number | null; tts?: number | null; total?: number | null };
};

type WsMessage = {
  type?: string;
  state?: BackendPublicState;
  agent_text?: string;
  user_transcript?: string;
  notice?: boolean;
  event?: string;
};

type HealthState = {
  status?: string;
  version?: string;
  groq?: boolean;
  gnani?: boolean;
  market_data?: boolean;
  unauthenticated_demo_actions_enabled?: boolean;
  voice_final_confirm_and_cancel_enabled?: boolean;
  production_ready_for_real_trading?: boolean;
  escrow?: string;
};

type TradeState = {
  sessionId: string | null;
  dealStatus: string;
  crop: string | null;
  commodityId: string | null;
  productForm: string | null;
  variety: string | null;
  quantity: number | null;
  district: string | null;
  market: string | null;
  quality: QualityState;
  waitingFor: string | null;
  buyerOffer: PublicOffer | null;
  reportedBuyerQuote: PublicOffer | null;
  buyerOfferStatus: string | null;
  activeOffer: ActiveOffer | null;
  offerVersion: number;
  farmerCounterPrice: number | null;
  negotiationRound: number;
  farmerConfirmed: boolean;
  buyerConfirmed: boolean;
  pricing: PricingState;
  lockedDeal: LockedDeal | null;
  escrow: SimulatedEscrow | null;
};

type Message = { id: string; role: "farmer" | "agent"; text: string };
type Timings = { stt: number | null; agent: number | null; tts: number | null; total: number | null };

const EMPTY_TRADE: TradeState = {
  sessionId: null,
  dealStatus: "GATHERING_DETAILS",
  crop: null,
  commodityId: null,
  productForm: null,
  variety: null,
  quantity: null,
  district: null,
  market: null,
  quality: {},
  waitingFor: "commodity",
  buyerOffer: null,
  reportedBuyerQuote: null,
  buyerOfferStatus: null,
  activeOffer: null,
  offerVersion: 0,
  farmerCounterPrice: null,
  negotiationRound: 0,
  farmerConfirmed: false,
  buyerConfirmed: false,
  pricing: {},
  lockedDeal: null,
  escrow: null,
};

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

function money(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "—" : INR.format(Math.round(value));
}

function numberText(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "—" : new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(value);
}

function dateText(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(date);
}

function dateTimeText(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function newSessionId(): string {
  const id = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID().replace(/-/g, "").slice(0, 12)
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  return `SV-${id.toUpperCase()}`;
}

function toTradeState(raw: BackendPublicState): TradeState {
  return {
    sessionId: raw.session_id ?? null,
    dealStatus: raw.deal_status ?? "GATHERING_DETAILS",
    crop: raw.crop ?? null,
    commodityId: raw.commodity_id ?? null,
    productForm: raw.product_form ?? null,
    variety: raw.variety ?? null,
    quantity: raw.quantity ?? null,
    district: raw.district ?? null,
    market: raw.market ?? null,
    quality: raw.quality ?? {},
    waitingFor: raw.waiting_for ?? null,
    buyerOffer: raw.buyer_offer ?? null,
    reportedBuyerQuote: raw.reported_buyer_quote ?? null,
    buyerOfferStatus: raw.buyer_offer_status ?? null,
    activeOffer: raw.active_offer ?? null,
    offerVersion: raw.offer_version ?? raw.active_offer?.offer_version ?? 0,
    farmerCounterPrice: raw.farmer_counter_price ?? null,
    negotiationRound: raw.negotiation_round ?? raw.negotiation_rounds ?? 0,
    farmerConfirmed: raw.farmer_confirmed ?? false,
    buyerConfirmed: raw.buyer_confirmed ?? false,
    pricing: raw.pricing ?? {},
    lockedDeal: raw.locked_deal ?? null,
    escrow: raw.simulated_escrow ?? null,
  };
}

function dealAcceptedMessage(trade: TradeState, language: LanguageHint): string {
  const locked = trade.lockedDeal;
  const price = locked?.price_per_quintal
    ?? trade.activeOffer?.price_per_quintal
    ?? trade.buyerOffer?.price_per_quintal
    ?? null;
  const quantity = locked?.quantity_quintals ?? trade.quantity;
  const gross = locked?.gross_amount_inr
    ?? (price != null && quantity != null ? price * quantity : null);
  const crop = locked?.commodity ?? trade.crop ?? "माल";
  const variety = locked?.variety ?? trade.variety;
  const cropLabel = variety ? `${crop} (${variety})` : crop;
  const rateLabel = money(price);
  const quantityLabel = quantity == null ? "—" : numberText(quantity);
  const grossLabel = money(gross);

  if (language === "mr-IN") {
    return `खरेदीदाराने तुमचा प्रस्ताव स्वीकारला आहे. ${cropLabel} चा ${rateLabel} प्रति क्विंटल दराने ${quantityLabel} क्विंटलचा सौदा निश्चित झाला आहे. एकूण रक्कम ${grossLabel}. हा फक्त डेमो व्यवहार आहे; प्रत्यक्ष पैसे ट्रान्सफर झालेले नाहीत (₹०).`;
  }
  if (language === "hi-IN") {
    return `खरीदार ने आपका प्रस्ताव स्वीकार कर लिया है। ${cropLabel} का ${rateLabel} प्रति क्विंटल के हिसाब से ${quantityLabel} क्विंटल का सौदा पक्का हो गया है। कुल राशि ${grossLabel} है। यह केवल डेमो है; वास्तविक पैसे ट्रांसफर नहीं हुए हैं (₹0)।`;
  }
  return `Buyer ne aapka offer accept kar liya hai. ${cropLabel} ka rate ${rateLabel} per quintal aur quantity ${quantityLabel} quintal hai. Deal confirm ho gayi hai; total ${grossLabel}. Yeh sirf demo hai — actual money transferred: ₹0.`;
}

function readableStatus(status: string): string {
  const labels: Record<string, string> = {
    GATHERING_DETAILS: "Collecting lot details",
    PRICE_DISCOVERY: "Checking mandi reference",
    NEGOTIATING: "Negotiation in progress",
    NEGOTIATING_WITHOUT_MARKET_REFERENCE: "Negotiating without a mandi reference",
    PENDING_BUYER_RESPONSE: "Waiting for buyer response",
    PENDING_FARMER_CONFIRMATION: "Waiting for farmer confirmation",
    PENDING_BUYER_CONFIRMATION: "Waiting for buyer confirmation",
    OFFER_REJECTED: "Offer rejected · fresh offer required",
    OFFER_EXPIRED: "Offer expired · fresh offer required",
    LOCKED: "Agreement confirmed by both parties",
    LOCKED_DEMO: "Demo agreement locked",
    CANCELLED: "Negotiation cancelled",
  };
  return labels[status] ?? status.replace(/_/g, " ").toLowerCase();
}

function qualityLabel(key: string): string {
  const labels: Record<string, string> = {
    moisture: "Moisture",
    cleanliness: "Cleanliness",
    grain_condition: "Grain condition",
    seed_condition: "Seed condition",
    product_form: "Product form",
    size: "Size",
    firmness: "Firmness",
    damage: "Damage",
    trash: "Foreign matter / trash",
  };
  return labels[key] ?? key.replace(/_/g, " ");
}

function qualityValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (typeof value === "object") {
    const record = value as UnknownRecord;
    if (record.reported_percent != null) return `${record.reported_percent}%`;
    if (record.description === "dry_self_reported") return "Farmer reported dry";
    if (record.description === "moist_self_reported") return "Farmer reported moist";
    if (typeof record.answer === "string") return record.answer;
    return "Reported";
  }
  return "—";
}

function apiErrorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => (item && typeof item === "object" && "msg" in item ? String((item as { msg: unknown }).msg) : String(item))).join("; ");
  }
  return fallback;
}

function priceReferenceLabel(pricing: PricingState): string {
  switch (pricing.reference_type) {
    case "market_actual":
      return "Reported market modal · exact available record";
    case "calculated_median":
      return "Calculated median · not an official mandi modal";
    case "fallback_record":
      return "Fallback record · not the exact requested market/variety";
    default:
      return pricing.modal_reference_label ?? "Mandi reference";
  }
}

function statusPillClass(status: string): string {
  if (status === "LOCKED" || status === "LOCKED_DEMO") return "bg-emerald-100 text-emerald-900";
  if (status === "CANCELLED" || status === "OFFER_EXPIRED" || status === "OFFER_REJECTED") return "bg-rose-100 text-rose-900";
  return "bg-amber-100 text-amber-950";
}

function SmallStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-200 bg-white px-3 py-2.5">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 break-words text-sm font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function TradeSummary({ trade }: { trade: TradeState }) {
  const pricing = trade.pricing;
  const active = trade.activeOffer;
  const original = trade.reportedBuyerQuote ?? trade.buyerOffer;
  const buyerSubmittedOriginal = original?.source === "buyer_submitted_offer";
  const locked = trade.lockedDeal;
  const escrow = trade.escrow;
  const hasLot = Boolean(trade.crop || trade.variety || trade.quantity != null || trade.district);
  const hasOffer = Boolean(active || original || trade.farmerConfirmed || trade.buyerConfirmed);

  return (
    <section className="space-y-4" aria-label="Trade summary">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Trade summary</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-900">{trade.crop ?? "Your lot"}</h2>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusPillClass(trade.dealStatus)}`}>
          {readableStatus(trade.dealStatus)}
        </span>
      </div>

      {hasLot ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <SmallStat label="Variety" value={trade.variety ?? "Not provided"} />
          <SmallStat label="Quantity" value={trade.quantity == null ? "Not provided" : `${numberText(trade.quantity)} quintal`} />
          <SmallStat label="Product form" value={trade.productForm ?? "—"} />
          <SmallStat label="District" value={trade.district ?? "Not provided"} />
          <SmallStat label="Mandi" value={trade.market ?? "Any market / not selected"} />
          <SmallStat label="Quality answers" value={`${Object.values(trade.quality).filter((value) => value != null).length} recorded`} />
        </div>
      ) : (
        <p className="rounded-xl border border-dashed border-slate-300 bg-white/70 px-4 py-3 text-sm text-slate-600">
          Start by telling SaudaVani which crop you want to sell, its quantity and your district.
        </p>
      )}

      {Object.keys(trade.quality).length > 0 && (
        <details className="rounded-xl border border-slate-200 bg-white px-4 py-3">
          <summary className="cursor-pointer text-sm font-semibold text-slate-800">Quality details</summary>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {Object.entries(trade.quality).filter(([, value]) => value != null).map(([key, value]) => (
              <div key={key} className="flex justify-between gap-3 border-b border-slate-100 py-1.5 text-sm">
                <span className="text-slate-500">{qualityLabel(key)}</span>
                <span className="text-right font-medium text-slate-800">{qualityValue(value)}</span>
              </div>
            ))}
          </div>
        </details>
      )}

      <div className="rounded-2xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Mandi price reference</p>
            <p className="mt-1 text-2xl font-bold tracking-tight text-slate-950">
              {pricing.modal_reference == null ? "Not available" : money(pricing.modal_reference)}
              {pricing.modal_reference != null && <span className="ml-1 text-xs font-medium text-slate-500">/ quintal</span>}
            </p>
            {pricing.modal_reference != null && <p className="mt-1 text-xs text-slate-600">{priceReferenceLabel(pricing)}</p>}
          </div>
          <div className="text-right text-xs text-slate-500">
            <p>Report date</p>
            <p className="mt-1 font-semibold text-slate-700">{dateText(pricing.as_of)}</p>
          </div>
        </div>

        {pricing.modal_reference == null ? (
          <p className="mt-3 text-sm text-slate-600">
            A usable mandi reference has not been returned. SaudaVani should not treat an unavailable price as a quote.
            {pricing.status ? ` Status: ${pricing.status.replace(/_/g, " ")}.` : ""}
          </p>
        ) : (
          <div className="mt-3 space-y-2 border-t border-slate-100 pt-3 text-sm">
            {pricing.fair_price_low != null || pricing.fair_price_high != null ? (
              <div className="flex flex-wrap justify-between gap-2">
                <span className="text-slate-500">{pricing.range_method?.toLowerCase().includes("spread") ? "Modal spread" : "Reported record range"}</span>
                <span className="font-semibold text-slate-800">{money(pricing.fair_price_low)} – {money(pricing.fair_price_high)}</span>
              </div>
            ) : null}
            {pricing.calculated_median_modal != null && (
              <div className="flex justify-between gap-2"><span className="text-slate-500">Calculated median modal</span><span className="font-semibold">{money(pricing.calculated_median_modal)}</span></div>
            )}
            {pricing.official_market_modal != null && (
              <div className="flex justify-between gap-2"><span className="text-slate-500">Official reported market modal</span><span className="font-semibold">{money(pricing.official_market_modal)}</span></div>
            )}
            {(pricing.lowest_market_min != null || pricing.highest_market_max != null) && (
              <div className="flex justify-between gap-2"><span className="text-slate-500">Outer reported min–max envelope</span><span className="font-semibold">{money(pricing.lowest_market_min)} – {money(pricing.highest_market_max)}</span></div>
            )}
            <div className="flex justify-between gap-2"><span className="text-slate-500">Market scope</span><span className="text-right font-medium">{pricing.market_scope ?? "—"}</span></div>
            <div className="flex justify-between gap-2"><span className="text-slate-500">Records / markets</span><span className="font-medium">{pricing.record_count ?? "—"} / {pricing.market_count ?? "—"}</span></div>
          </div>
        )}

        {(pricing.variety_fallback || pricing.variety_match === false) && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-950">
            Variety fallback: the requested variety was not matched. This reference must not be described as the modal price of your requested variety.
            {pricing.fallback_record?.variety ? ` Available record variety: ${pricing.fallback_record.variety}.` : ""}
          </p>
        )}
        {(pricing.market_fallback || pricing.market_matched === false) && (
          <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-950">
            Market fallback: the selected mandi was not matched; district-level/other available market records were used.
          </p>
        )}
        {pricing.stale && (
          <p className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-xs leading-relaxed text-rose-900">
            Warning: this market report is older than the configured freshness limit. Do not treat it as a current auction bid.
          </p>
        )}
        {pricing.from_cache && <p className="mt-2 text-xs text-slate-500">Retrieved from the recent successful lookup cache.</p>}
        {pricing.source && <p className="mt-3 text-[11px] text-slate-500">Source: {pricing.source}</p>}
      </div>

      {hasOffer && (
        <div className="rounded-2xl border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-semibold text-slate-900">Negotiation</h3>
            <span className="text-xs text-slate-500">Round {trade.negotiationRound} · Version {trade.offerVersion}</span>
          </div>

          {original && (
            <div className="mt-3 rounded-xl bg-slate-50 p-3">
              <p className="text-xs font-semibold text-slate-500">
                {buyerSubmittedOriginal ? "Buyer-submitted offer · identity not authenticated" : "Farmer-reported buyer quote · unverified"}
              </p>
              <p className="mt-1 text-xl font-bold text-slate-900">{money(original.price_per_quintal)} <span className="text-xs font-medium text-slate-500">/ quintal</span></p>
              <p className="mt-1 text-xs text-slate-500">{buyerSubmittedOriginal ? "Submitted through the buyer-offer endpoint; the buyer's identity has not been authenticated." : "Reported by the farmer; SaudaVani has not verified this quote with the buyer."}</p>
            </div>
          )}

          {active && (
            <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-amber-900">Current active offer</p>
                <span className="rounded-full bg-white/80 px-2 py-1 text-[11px] font-semibold text-amber-950">{active.proposed_by === "farmer" ? "Farmer counter" : active.source === "buyer_submitted_offer" ? "Buyer-submitted · identity not authenticated" : "Farmer-reported quote · unverified"}</span>
              </div>
              <p className="mt-1 text-2xl font-bold text-slate-950">{money(active.price_per_quintal)} <span className="text-xs font-medium text-slate-600">/ quintal</span></p>
              <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
                <div><p className="text-xs text-slate-500">Quantity</p><p className="font-semibold">{numberText(active.quantity_quintals)} quintal</p></div>
                <div><p className="text-xs text-slate-500">Gross value</p><p className="font-semibold">{money(active.gross_value)}</p></div>
              </div>
              {active.expires_at && <p className="mt-2 text-xs text-slate-600">Offer expiry: {dateTimeText(active.expires_at)}</p>}
              <p className="mt-1 text-xs text-slate-600">Status: {active.status ?? "active"}</p>
            </div>
          )}

          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-600">
            <span>Farmer: <strong className="text-slate-900">{trade.farmerConfirmed ? "Confirmed" : "Pending"}</strong></span>
            <span>Buyer: <strong className="text-slate-900">{trade.buyerConfirmed ? "Confirmed" : "Pending"}</strong></span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-slate-500">A deal is locked only when both parties confirm the same active offer version.</p>
        </div>
      )}

      {locked && (
        <div className="rounded-2xl border border-emerald-300 bg-emerald-50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-800">Agreement record locked</p>
          <p className="mt-1 text-sm font-semibold text-emerald-950">{locked.voucher_id ?? "Deal record"}</p>
          <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
            <div><p className="text-xs text-emerald-800">Agreed rate</p><p className="font-bold">{money(locked.price_per_quintal)} / quintal</p></div>
            <div><p className="text-xs text-emerald-800">Gross value</p><p className="font-bold">{money(locked.gross_amount_inr)}</p></div>
            <div><p className="text-xs text-emerald-800">Demo advance estimate</p><p className="font-semibold">{money(locked.advance_amount_demo_estimate_inr)}</p></div>
            <div><p className="text-xs text-emerald-800">Demo remaining estimate</p><p className="font-semibold">{money(locked.remaining_amount_demo_estimate_inr)}</p></div>
          </div>
          <p className="mt-3 text-xs font-semibold text-emerald-950">No payment has occurred. These are simulated demo calculations only.</p>
        </div>
      )}

      {escrow && (
        <div className="rounded-2xl border border-slate-300 bg-slate-900 p-4 text-white">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-300">Simulated escrow ledger</p>
          <p className="mt-1 font-semibold">{escrow.status?.replace(/_/g, " ") ?? "SIMULATION"}</p>
          <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <div><p className="text-xs text-slate-300">Simulated amount</p><p className="font-bold">{money(escrow.simulated_amount_inr)}</p></div>
            <div><p className="text-xs text-slate-300">Actual money transferred</p><p className="font-bold">₹0</p></div>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-slate-300">{escrow.notice ?? "Simulation only. No real payment service is connected."}</p>
        </div>
      )}
    </section>
  );
}

export default function SaudaVaniPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [language, setLanguage] = useState<LanguageHint>("mr-IN");
  const [phase, setPhase] = useState<Phase>("idle");
  const [trade, setTrade] = useState<TradeState>(EMPTY_TRADE);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [shareMessage, setShareMessage] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthState | null>(null);
  const [healthStatus, setHealthStatus] = useState<"checking" | "online" | "offline">("checking");
  const [wsLive, setWsLive] = useState(false);
  const [timings, setTimings] = useState<Timings | null>(null);
  const playerRef = useRef<HTMLAudioElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);
  const logRef = useRef<HTMLDivElement | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const languageRef = useRef<LanguageHint>(language);
  const speakInBrowserRef = useRef<(text: string, ttsLanguage?: string) => boolean>(() => false);
  const lastWsDealStatusRef = useRef<string | null>(null);
  const lockNoticeSessionRef = useRef<string | null>(null);
  const shareTimeoutRef = useRef<number | null>(null);
  languageRef.current = language;

  // Resume the same backend session after a page refresh or backend restart.
  // The backend persists sessions in SQLite; generating a fresh ID on every mount
  // would make the UI look like the farmer must enter all details again.
  useEffect(() => {
    const storedId = window.localStorage.getItem(SESSION_STORAGE_KEY);
    // Backend-rotated IDs append a commodity and UUID suffix, so accept the full backend ID alphabet.
    const id = storedId && /^[A-Za-z0-9_.:\-]{1,128}$/.test(storedId)
      ? storedId
      : newSessionId();
    window.localStorage.setItem(SESSION_STORAGE_KEY, id);
    setSessionId(id);
  }, []);

  const syncSessionState = useCallback(async (id: string, signal?: AbortSignal): Promise<BackendPublicState | null> => {
    try {
      const response = await fetch(`${API_BASE}/api/session/${encodeURIComponent(id)}`, { signal, cache: "no-store" });
      if (!response.ok) return null;
      const state = (await response.json()) as BackendPublicState;
      setTrade(toTradeState(state));
      return state;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const checkHealth = async () => {
      try {
        const response = await fetch(`${API_BASE}/health`, { cache: "no-store" });
        if (!response.ok) throw new Error("Backend health check failed");
        const data = (await response.json()) as HealthState;
        if (!cancelled) {
          setHealth(data);
          setHealthStatus("online");
        }
      } catch {
        if (!cancelled) {
          setHealth(null);
          setHealthStatus("offline");
        }
      }
    };
    void checkHealth();
    const interval = window.setInterval(checkHealth, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    let disposed = false;
    let retryTimer: number | undefined;
    let socket: WebSocket | null = null;

    const connect = () => {
      if (disposed) return;
      socket = new WebSocket(`${WS_BASE}/ws/trade/${encodeURIComponent(sessionId)}`);
      wsRef.current = socket;
      socket.onopen = () => {
        setWsLive(true);
        socket?.send("get_state");
        void syncSessionState(sessionId);
      };
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as WsMessage;
          const noticeText = message.agent_text?.trim();
          const noticeReceived = message.notice === true && Boolean(noticeText);

          if (noticeReceived && noticeText) {
            setMessages((current) => [
              ...current,
              { id: newSessionId(), role: "agent", text: noticeText },
            ]);
            speakInBrowserRef.current(noticeText, languageRef.current);
            if (message.event === "buyer_accepted_locked") {
              lockNoticeSessionRef.current = sessionId;
            }
          }

          if (!message.state) return;
          const nextTrade = toTradeState(message.state);
          // The first WebSocket packet is a snapshot. Seed the status without announcing an
          // old locked deal as if it had just been accepted during this page visit.
          if (message.type === "snapshot" || lastWsDealStatusRef.current == null) {
            lastWsDealStatusRef.current = nextTrade.dealStatus;
            setTrade(nextTrade);
            return;
          }

          const previousStatus = lastWsDealStatusRef.current;
          lastWsDealStatusRef.current = nextTrade.dealStatus;
          setTrade(nextTrade);

          const isLocked = nextTrade.dealStatus === "LOCKED" || nextTrade.dealStatus === "LOCKED_DEMO";
          const wasLocked = previousStatus === "LOCKED" || previousStatus === "LOCKED_DEMO";
          // Retain the local message only as a fallback if the server did not send a lock notice.
          if (isLocked && !wasLocked && !noticeReceived && !message.agent_text && lockNoticeSessionRef.current !== sessionId) {
            lockNoticeSessionRef.current = sessionId;
            const acceptedText = dealAcceptedMessage(nextTrade, languageRef.current);
            setMessages((current) => [
              ...current,
              { id: newSessionId(), role: "agent", text: acceptedText },
            ]);
          }
        } catch {
          // Ignore malformed socket messages; the HTTP voice response remains authoritative.
        }
      };
      socket.onclose = () => {
        setWsLive(false);
        if (!disposed) retryTimer = window.setTimeout(connect, 2500);
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      disposed = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      socket?.close();
      if (wsRef.current === socket) wsRef.current = null;
    };
  }, [sessionId, syncSessionState]);

  useEffect(() => {
    if (!sessionId) return;
    void syncSessionState(sessionId);
  }, [sessionId, syncSessionState]);


  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, phase]);

  useEffect(() => {
    return () => {
      if (shareTimeoutRef.current !== null) window.clearTimeout(shareTimeoutRef.current);
    };
  }, []);

  const stopPlayback = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    const player = playerRef.current;
    if (player) {
      player.pause();
      player.removeAttribute("src");
      player.load();
      playerRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      stopPlayback();
      wsRef.current?.close();
    };
  }, [stopPlayback]);

  const speakInBrowser = useCallback((text: string, ttsLanguage?: string) => {
    if (!text || !("speechSynthesis" in window)) return false;
    const utterance = new SpeechSynthesisUtterance(text);
    const lang = (ttsLanguage ?? "mr").toLowerCase();
    utterance.lang = lang.startsWith("hi") ? "hi-IN" : lang.startsWith("en") ? "en-IN" : "mr-IN";
    utterance.onend = () => setPhase("idle");
    utterance.onerror = () => setPhase("idle");
    window.speechSynthesis.cancel();
    setPhase("speaking");
    window.speechSynthesis.speak(utterance);
    return true;
  }, []);

  useEffect(() => {
    speakInBrowserRef.current = speakInBrowser;
  }, [speakInBrowser]);

  const shareBuyerLink = useCallback(async () => {
    if (!sessionId) return;
    const link = `${window.location.origin}/buyer/${sessionId}`;

    const copyFallback = () => {
      const input = document.createElement("textarea");
      input.value = link;
      input.setAttribute("readonly", "");
      input.style.position = "fixed";
      input.style.left = "-9999px";
      document.body.appendChild(input);
      input.select();
      const copied = document.execCommand("copy");
      input.remove();
      return copied;
    };

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(link);
      } else if (!copyFallback()) {
        throw new Error("Clipboard copy was not available.");
      }
      setShareMessage("Link copied");
    } catch {
      setShareMessage(copyFallback() ? "Link copied" : "Could not copy link");
    }

    if (shareTimeoutRef.current !== null) window.clearTimeout(shareTimeoutRef.current);
    shareTimeoutRef.current = window.setTimeout(() => setShareMessage(null), 2000);
  }, [sessionId]);

  const sendTurn = useCallback(async (input: { transcript?: string; audio?: Blob }) => {
    if (!sessionId || inFlightRef.current) return;
    const transcript = input.transcript?.trim();
    if (!transcript && !input.audio) return;

    inFlightRef.current = true;
    setError(null);
    setNotice(null);
    setPhase("processing");
    stopPlayback();

    const controller = new AbortController();
    abortRef.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    const startedAt = performance.now();

    try {
      const form = new FormData();
      form.append("session_id", sessionId);
      form.append("language", language);
      if (transcript) {
        form.append("transcript", transcript);
      } else if (input.audio) {
        const mime = input.audio.type || "audio/webm";
        const extension = mime.includes("mp4") ? "mp4" : mime.includes("ogg") ? "ogg" : "webm";
        form.append("audio", input.audio, `saudavani.${extension}`);
      }

      const response = await fetch(`${API_BASE}/api/voice/process`, {
        method: "POST",
        body: form,
        signal: controller.signal,
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiErrorMessage(body, `Backend returned HTTP ${response.status}.`));
      if (!body || typeof body !== "object") throw new Error("The backend returned an invalid response.");

      const data = body as VoiceResponse;
      const responseSessionId = typeof data.session_id === "string" && data.session_id
        ? data.session_id
        : sessionId;
      if (data.session_rotated && responseSessionId !== sessionId) {
        window.localStorage.setItem(SESSION_STORAGE_KEY, responseSessionId);
        setSessionId(responseSessionId); // sessionId-dependent effect reconnects /ws/trade to the new session
        lastWsDealStatusRef.current = null;
        lockNoticeSessionRef.current = null;
      }
      const agentText = data.agent_text?.trim() || "I could not prepare a response. Please try again.";
      const userText = data.user_transcript?.trim() || transcript || "Voice message";

      setMessages((current) => [
        ...current,
        { id: newSessionId(), role: "farmer", text: userText },
        { id: newSessionId(), role: "agent", text: agentText },
      ]);

      setTimings({
        stt: data.latency_ms?.stt ?? null,
        agent: data.latency_ms?.agent ?? null,
        tts: data.latency_ms?.tts ?? null,
        total: data.latency_ms?.total ?? Math.round(performance.now() - startedAt),
      });

      if (data.deal_state) {
        setTrade((current) => ({
          ...current,
          dealStatus: data.deal_state?.deal_status ?? current.dealStatus,
          crop: data.deal_state?.crop ?? current.crop,
          commodityId: data.deal_state?.commodity_id ?? current.commodityId,
          variety: data.deal_state?.variety ?? current.variety,
          quantity: data.deal_state?.quantity ?? current.quantity,
          district: data.deal_state?.district ?? current.district,
          market: data.deal_state?.market ?? current.market,
          buyerOffer: data.deal_state?.buyer_offer ?? current.buyerOffer,
          reportedBuyerQuote: data.deal_state?.reported_buyer_quote ?? current.reportedBuyerQuote,
          activeOffer: data.deal_state?.active_offer ?? current.activeOffer,
          offerVersion: data.deal_state?.offer_version ?? current.offerVersion,
          negotiationRound: data.deal_state?.negotiation_round ?? current.negotiationRound,
          farmerConfirmed: data.deal_state?.farmer_confirmed ?? current.farmerConfirmed,
          buyerConfirmed: data.deal_state?.buyer_confirmed ?? current.buyerConfirmed,
          lockedDeal: data.deal_state?.voucher ?? current.lockedDeal,
          pricing: data.pricing ?? current.pricing,
        }));
      }

      // Fetch the complete public state: it includes quality, product form and escrow details.
      // On a crop rotation, never re-fetch the old session after adopting the new session ID.
      await syncSessionState(responseSessionId, controller.signal);

      if (data.audio_base64) {
        const mime = data.audio_mime_type || "audio/wav";
        const player = new Audio(`data:${mime};base64,${data.audio_base64}`);
        playerRef.current = player;
        player.onended = () => {
          playerRef.current = null;
          setPhase("idle");
        };
        player.onerror = () => {
          playerRef.current = null;
          if (!speakInBrowser(agentText, data.tts_language)) setPhase("idle");
        };
        setPhase("speaking");
        try {
          await player.play();
        } catch {
          playerRef.current = null;
          if (!speakInBrowser(agentText, data.tts_language)) setPhase("idle");
        }
      } else {
        if (data.audio_error) setNotice(`Text reply is ready, but voice playback was unavailable: ${data.audio_error}`);
        if (!speakInBrowser(agentText, data.tts_language)) setPhase("idle");
      }
    } catch (caught) {
      setPhase("idle");
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setError("The request timed out. Check the backend and Gnani service, then try again or use text input.");
      } else if (caught instanceof TypeError) {
        setError(`Cannot reach ${API_BASE}. Start the backend and check NEXT_PUBLIC_API_URL in frontend/.env.local.`);
      } else {
        setError(caught instanceof Error ? caught.message : "Something went wrong. Please try again.");
      }
    } finally {
      window.clearTimeout(timeout);
      inFlightRef.current = false;
      abortRef.current = null;
    }
  }, [language, sessionId, speakInBrowser, stopPlayback, syncSessionState]);

  const handleRecordedAudio = useCallback(async (blob: Blob, mimeType: string) => {
    const audioBlob = blob.type ? blob : new Blob([blob], { type: mimeType });
    await sendTurn({ audio: audioBlob });
  }, [sendTurn]);

  const {
    state: recState,
    error: recError,
    start,
    stop,
    isRecording,
  } = useSilenceRecorder(handleRecordedAudio);

  const onMicClick = useCallback(() => {
    if (isRecording) {
      stop();
    } else if (phase === "speaking") {
      stopPlayback();
      setPhase("idle");
    } else if (phase === "idle" && recState !== "processing") {
      setError(null);
      setNotice(null);
      stopPlayback();
      void start();
    }
  }, [isRecording, phase, recState, start, stop, stopPlayback]);

  const submitText = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || inFlightRef.current || isRecording) return;
    setDraft("");
    void sendTurn({ transcript: text });
  };

  const resetSession = () => {
    if (isRecording) return; // do not submit an in-progress recording to a session being replaced
    abortRef.current?.abort();
    stopPlayback();
    inFlightRef.current = false;
    setPhase("idle");
    setTrade(EMPTY_TRADE);
    setMessages([]);
    setTimings(null);
    setError(null);
    setNotice(null);
    setShareMessage(null);
    setDraft("");
    lastWsDealStatusRef.current = null;
    lockNoticeSessionRef.current = null;
    const nextId = newSessionId();
    window.localStorage.setItem(SESSION_STORAGE_KEY, nextId);
    setSessionId(nextId);
  };

  const busy = phase === "processing" || recState === "processing";
  const micLabel = recState !== "idle"
    ? REC_LABEL[recState]
    : phase === "processing"
      ? "Checking your details and preparing a reply…"
      : phase === "speaking"
        ? "SaudaVani is speaking · tap to stop"
        : "Tap to speak, or type your message";

  const suggestions = language === "mr-IN"
    ? ["माझ्याकडे 3 क्विंटल गहू आहे", "माझ्या मालाचा मंडी भाव सांगा", "भाव थोडा वाढवा"]
    : language === "hi-IN"
      ? ["मेरे पास 3 क्विंटल गेहूं है", "मेरे माल का मंडी भाव बताइए", "भाव थोड़ा बढ़ाइए"]
      : ["Mere paas 3 quintal gehun hai", "Mandi ka rate batao", "Rate thoda badhao"];

  const buyerLink = sessionId && typeof window !== "undefined"
    ? `${window.location.origin}/buyer/${sessionId}`
    : null;

  return (
    <main className="min-h-screen bg-[#f4f6f7] text-slate-900">
      <div className="mx-auto max-w-6xl px-4 py-5 sm:px-6 lg:py-8">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-800 text-lg font-bold text-white">स</span>
              <div>
                <h1 className="text-2xl font-bold tracking-tight">SaudaVani <span className="text-slate-400">सौदावाणी</span></h1>
                <p className="text-xs text-slate-500">Mandi voice assistant · Farmer desk</p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold ${healthStatus === "online" ? "bg-emerald-100 text-emerald-800" : healthStatus === "offline" ? "bg-rose-100 text-rose-800" : "bg-slate-200 text-slate-600"}`}>
              <span className={`h-2 w-2 rounded-full ${healthStatus === "online" ? "bg-emerald-600" : healthStatus === "offline" ? "bg-rose-600" : "bg-slate-400"}`} />
              {healthStatus === "online" ? "Backend connected" : healthStatus === "offline" ? "Backend offline" : "Checking backend"}
            </span>
            <span className={`rounded-full px-3 py-1.5 text-xs font-semibold ${wsLive ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-600"}`}>
              {wsLive ? "Live sync on" : "Live sync reconnecting"}
            </span>
            <button type="button" onClick={resetSession} disabled={isRecording || busy} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50">
              New session
            </button>
          </div>
        </header>

        <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(330px,0.85fr)]">
          <section className="flex min-h-[640px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm" aria-label="Farmer conversation">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-4 sm:px-5">
              <div>
                <h2 className="font-semibold text-slate-900">Talk to SaudaVani</h2>
                <p className="mt-0.5 text-xs text-slate-500">Speak naturally. You can also type in the chat.</p>
              </div>
              <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
                Language
                <select value={language} onChange={(event) => setLanguage(event.target.value as LanguageHint)} disabled={busy || isRecording} className="rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-800 outline-none focus:border-emerald-700">
                  {LANGUAGE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
            </div>

            <div ref={logRef} className="flex-1 space-y-4 overflow-y-auto bg-[#fbfcfc] p-4 sm:p-5" aria-live="polite" aria-relevant="additions text">
              {messages.length === 0 ? (
                <div className="mx-auto mt-8 max-w-md text-center">
                  <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-emerald-50 text-3xl">🌾</div>
                  <h3 className="mt-4 text-lg font-semibold">Namaskar! नमस्कार!</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">Tell me what crop you want to sell. I’ll ask for the quantity, variety, district and quality details, then check the available mandi reference.</p>
                  <div className="mt-5 flex flex-wrap justify-center gap-2">
                    {suggestions.map((suggestion) => (
                      <button key={suggestion} type="button" disabled={busy || isRecording || !sessionId} onClick={() => void sendTurn({ transcript: suggestion })} className="rounded-full border border-slate-200 bg-white px-3 py-2 text-left text-xs text-slate-700 hover:border-emerald-700 hover:text-emerald-800 disabled:opacity-50">
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((message) => (
                  <div key={message.id} className={`flex ${message.role === "farmer" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[88%] rounded-2xl px-4 py-3 ${message.role === "farmer" ? "rounded-br-md bg-emerald-800 text-white" : "rounded-bl-md border border-slate-200 bg-white text-slate-900"}`}>
                      <p className={`mb-1 text-[11px] font-semibold ${message.role === "farmer" ? "text-emerald-100" : "text-slate-500"}`}>{message.role === "farmer" ? "You" : "SaudaVani"}</p>
                      <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.text}</p>
                    </div>
                  </div>
                ))
              )}
              {busy && (
                <div className="flex justify-start">
                  <div className="rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                    <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-700" />
                    Processing your message…
                  </div>
                </div>
              )}
            </div>

            {error && <div role="alert" className="mx-4 mb-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{error}</div>}
            {recState === "error" && recError && <div role="alert" className="mx-4 mb-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{recError}</div>}
            {notice && <div role="status" className="mx-4 mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">{notice}</div>}

            <div className="border-t border-slate-100 p-4 sm:p-5">
              <div className="mb-3 flex items-center justify-center gap-2 text-xs text-slate-500" role="status" aria-live="polite">
                {isRecording && <span className="h-2 w-2 animate-pulse rounded-full bg-rose-600" />}
                {micLabel}
              </div>
              <div className="flex items-center justify-center">
                <button type="button" onClick={onMicClick} disabled={busy || !sessionId || healthStatus === "offline" || (healthStatus === "online" && health?.gnani === false)} aria-label={isRecording ? "Stop recording and send" : phase === "speaking" ? "Stop speech" : "Start microphone"} className={`grid h-20 w-20 place-items-center rounded-full text-white shadow-lg transition focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-800 disabled:cursor-not-allowed disabled:opacity-50 ${isRecording ? "bg-rose-600 hover:bg-rose-700" : busy ? "bg-slate-500" : "bg-emerald-800 hover:bg-emerald-900"}`}>
                  {busy ? <span className="h-7 w-7 animate-spin rounded-full border-2 border-white/40 border-t-white" /> : isRecording ? <span className="h-6 w-6 rounded-md bg-white" /> : phase === "speaking" ? <span className="text-2xl">■</span> : <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3m-4 0h8" strokeLinecap="round" /></svg>}
                </button>
              </div>
              <form onSubmit={submitText} className="mt-4 flex items-end gap-2">
                <label className="sr-only" htmlFor="farmer-message">Type a message</label>
                <textarea id="farmer-message" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} disabled={busy || isRecording || !sessionId} rows={2} placeholder="Type your message here…" className="min-h-[48px] min-w-0 flex-1 resize-y rounded-xl border border-slate-300 bg-white px-3 py-3 text-sm outline-none placeholder:text-slate-400 focus:border-emerald-700 disabled:bg-slate-100" />
                <button type="submit" disabled={!draft.trim() || busy || isRecording || !sessionId} className="rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40">Send</button>
              </form>
              <p className="mt-2 text-center text-[11px] text-slate-400">Microphone access and a configured Gnani STT key are required for voice input. Text chat works without microphone access.</p>
            </div>
          </section>

          <aside className="space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-semibold text-slate-900">Your mandi trade</h2>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <span className="font-mono text-[11px] text-slate-400">{sessionId ?? "Starting…"}</span>
                  <button
                    type="button"
                    onClick={() => void shareBuyerLink()}
                    disabled={!sessionId}
                    className="rounded-lg bg-emerald-800 px-3 py-2 text-xs font-semibold text-white transition hover:bg-emerald-900 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Share with buyer
                  </button>
                </div>
              </div>
              {buyerLink && (
                <p className="mt-2 break-all text-xs leading-relaxed text-slate-600">
                  Buyer link: <span className="font-medium text-emerald-800">{buyerLink}</span>
                </p>
              )}
              {shareMessage && (
                <p role="status" aria-live="polite" className="mt-2 text-xs font-semibold text-emerald-700">
                  {shareMessage}
                </p>
              )}
              <div className="mt-4">
                <TradeSummary trade={trade} />
              </div>
            </div>

            {health && (
              <div className="rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-600">
                <h3 className="font-semibold text-slate-800">Service status</h3>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <SmallStat label="Gnani voice service" value={health.gnani ? "Configured" : "Not configured"} />
                  <SmallStat label="Mandi data key" value={health.market_data ? "Configured" : "Not configured"} />
                </div>
                {health.voice_final_confirm_and_cancel_enabled === false && (
                  <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 leading-relaxed text-amber-950">
                    Voice deal confirmation and cancellation are disabled by the backend safety setting. For a local, isolated hackathon demo only, the operator may enable the simulated demo actions; do not enable unauthenticated deal actions on a public deployment.
                  </p>
                )}
                {health.unauthenticated_demo_actions_enabled === true && (
                  <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 leading-relaxed text-rose-900">
                    Warning: unauthenticated demo deal actions are enabled. Keep this backend restricted to your local/private demo network.
                  </p>
                )}
                <p className="mt-3 leading-relaxed">Prototype only. It is not production-ready for real trading. A session ID is not user authentication. Any escrow shown here is simulated; actual money transferred is ₹0.</p>
              </div>
            )}

            {timings && (
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <h3 className="text-sm font-semibold text-slate-800">Latest response timing</h3>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <SmallStat label="STT" value={timings.stt == null ? "—" : `${timings.stt} ms`} />
                  <SmallStat label="Assistant" value={timings.agent == null ? "—" : `${timings.agent} ms`} />
                  <SmallStat label="TTS" value={timings.tts == null ? "—" : `${timings.tts} ms`} />
                  <SmallStat label="Total" value={timings.total == null ? "—" : `${timings.total} ms`} />
                </div>
              </div>
            )}
          </aside>
        </div>

        <footer className="mt-6 border-t border-slate-200 pt-4 text-center text-[11px] leading-relaxed text-slate-500">
          SaudaVani hackathon prototype · AGMARKNET values are reported daily market data, not live auction bids · Simulated escrow only · Actual money transferred: ₹0
        </footer>
      </div>
    </main>
  );
}
