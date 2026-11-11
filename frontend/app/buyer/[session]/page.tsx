"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";

type ActiveOffer = {
  price_per_quintal?: number | null;
  quantity_quintals?: number | null;
  gross_value?: number | null;
  proposed_by?: string;
  source_label?: string;
  status?: string;
  offer_version?: number | null;
  expires_at?: string | null;
  seconds_left?: number | null;
};

type BuyerDeal = {
  session_id: string;
  crop: string;
  variety: string | null;

  // Current backend response fields
  quantity_quintals?: number | null;
  active_offer?: ActiveOffer | null;

  // Legacy fields retained as fallbacks
  quantity?: number | null;
  price_per_quintal?: number | null;
  total_value?: number | null;
  expiry?: string | null;

  quality: unknown;
  deal_status: string;
  negotiation_round: number | null;
  offer_version: number | null;
};

type Responded = { version: number; accepted: boolean };

const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");
const WS_BASE = API_BASE.replace(/^http/i, "ws");

const currency = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const quantityFormat = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 2,
});

function displayQualityValue(value: unknown): string {
  if (value == null) return "—";

  if (value === "dry_self_reported") return "Dry (farmer-reported)";
  if (value === "moist_self_reported") return "Moist (farmer-reported)";

  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }

  if (Array.isArray(value)) {
    return value.map(displayQualityValue).join(", ");
  }

  if (typeof value === "object") {
    const item = value as Record<string, unknown>;

    const answer =
      item.answer ??
      item.value ??
      item.response ??
      item.selected ??
      item.text ??
      item.label;

    if (answer !== undefined) {
      return displayQualityValue(answer);
    }

    return Object.entries(item)
      .map(
        ([key, child]) =>
          `${displayQualityLabel(key)}: ${displayQualityValue(child)}`
      )
      .join(" · ");
  }

  return "—";
}

function displayQualityLabel(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function normalizeQualityEntries(
  quality: unknown
): Array<[string, unknown]> {
  if (Array.isArray(quality)) {
    return quality.map((item, index) => {
      if (item && typeof item === "object") {
        const obj = item as Record<string, unknown>;

        const label =
          obj.label ??
          obj.question ??
          obj.prompt ??
          obj.key ??
          obj.name ??
          `Quality answer ${index + 1}`;

        const value =
          obj.value ??
          obj.answer ??
          obj.response ??
          obj.selected ??
          obj.text ??
          "—";

        return [displayQualityValue(label), value];
      }

      return [`Quality answer ${index + 1}`, item];
    });
  }

  if (quality && typeof quality === "object") {
    return Object.entries(quality as Record<string, unknown>).map(
      ([key, value]) => {
        return [displayQualityLabel(key), value];
      }
    );
  }

  return [];
}

function normalizeStatus(status: string): string {
  return status.trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function isPendingStatus(status: string): boolean {
  return [
    "pending",
    "pending_buyer_confirmation",
    "pending_buyer_response",
    "pending_buyer",
    "awaiting_buyer",
    "awaiting_buyer_confirmation",
    "buyer_pending",
    "negotiating",
  ].includes(normalizeStatus(status));
}

function isAwaitingFarmerStatus(status: string): boolean {
  return normalizeStatus(status) === "pending_farmer_confirmation";
}

function isLockedStatus(status: string): boolean {
  const s = normalizeStatus(status);
  return s === "locked" || s === "locked_demo";
}

function isRejectedStatus(status: string): boolean {
  return normalizeStatus(status) === "offer_rejected";
}

function errorDetail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) =>
          item && typeof item === "object" && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : String(item)
        )
        .join("; ");
    }
  }
  return fallback;
}

function BuyerDealPageContent() {
  const params = useParams<{ session: string }>();
  const router = useRouter();
  const sessionId = params.session;

  const [deal, setDeal] = useState<BuyerDeal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionNotice, setActionNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [submitting, setSubmitting] = useState<"accept" | "reject" | null>(
    null
  );
  const [responded, setResponded] = useState<Responded | null>(null);
  const [liveConnected, setLiveConnected] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  const submittingRef = useRef(false);
  const requestSeqRef = useRef(0);
  const playerRef = useRef<HTMLAudioElement | null>(null);
    useEffect(() => {
    return () => {
      const player = playerRef.current;

      if (player) {
        player.pause();
        player.removeAttribute("src");
        player.load();
        playerRef.current = null;
      }
    };
  }, []);

  // Keep the last good deal visible during background refreshes.
  const loadDeal = useCallback(
    async (opts: { silent?: boolean; signal?: AbortSignal } = {}) => {
      const { silent = false, signal } = opts;
      const seq = ++requestSeqRef.current;

      if (!silent) {
        setLoading(true);
        setError("");
        setDeal(null);
        setActionNotice("");
        setActionError("");
      }

      try {
        const response = await fetch(
          `${API_BASE}/api/buyer/session/${encodeURIComponent(sessionId)}`,
          {
            method: "GET",
            headers: { Accept: "application/json" },
            signal,
            cache: "no-store",
          }
        );

        const data = await response.json().catch(() => null);

        if (response.status === 404) {
          throw new Error(
            "Deal not found. Check the session ID and try again."
          );
        }

        if (!response.ok) {
          throw new Error(
            typeof data?.detail === "string"
              ? data.detail
              : `Unable to load deal (HTTP ${response.status}).`
          );
        }

        if (!data || data.session_id !== sessionId) {
          throw new Error("The server returned an invalid deal response.");
        }

        // Ignore out-of-order responses.
        if (seq !== requestSeqRef.current) return;
        setDeal(data as BuyerDeal);
      } catch (err) {
        if (signal?.aborted) return;
        if (seq !== requestSeqRef.current) return;
        if (silent) return; // keep showing the last good data

        setError(
          err instanceof Error
            ? err.message
            : "Unable to connect to the SaudaVani backend."
        );
      } finally {
        if (!silent && !signal?.aborted && seq === requestSeqRef.current) {
          setLoading(false);
        }
      }
    },
    [sessionId]
  );

  // Initial load (and retry).
  useEffect(() => {
    if (!sessionId) return;
    const controller = new AbortController();
    void loadDeal({ signal: controller.signal });
    return () => controller.abort();
  }, [sessionId, retryKey, loadDeal]);

  // Refetch the buyer-safe endpoint; never render raw socket payloads.
  useEffect(() => {
    if (!sessionId) return;

    let disposed = false;
    let retryTimer: number | undefined;
    let refreshTimer: number | undefined;
    let socket: WebSocket | null = null;
    const controller = new AbortController();

    const scheduleRefresh = () => {
      if (refreshTimer !== undefined) window.clearTimeout(refreshTimer);
      refreshTimer = window.setTimeout(() => {
        void loadDeal({ silent: true, signal: controller.signal });
      }, 150);
    };

    const connect = () => {
      if (disposed) return;
      socket = new WebSocket(
        `${WS_BASE}/ws/buyer/${encodeURIComponent(sessionId)}`
      );

      socket.onopen = () => {
        setLiveConnected(true);
        scheduleRefresh();
      };
      socket.onmessage = () => scheduleRefresh();
      socket.onclose = () => {
        setLiveConnected(false);
        if (!disposed) retryTimer = window.setTimeout(connect, 2500);
      };
      socket.onerror = () => socket?.close();
    };

    connect();

    return () => {
      disposed = true;
      controller.abort();
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      if (refreshTimer !== undefined) window.clearTimeout(refreshTimer);
      socket?.close();
    };
  }, [sessionId, loadDeal]);

  const respond = useCallback(
    async (accepted: boolean) => {
      if (submittingRef.current || !deal) return;

      const version = deal.active_offer?.offer_version ?? deal.offer_version;
      if (version == null || !Number.isFinite(version)) {
        setActionError(
          "This deal has no offer version yet, so it cannot be confirmed."
        );
        return;
      }

      submittingRef.current = true;
      setSubmitting(accepted ? "accept" : "reject");
      setActionError("");
      setActionNotice("");

      try {
        const response = await fetch(
          `${API_BASE}/api/deals/${encodeURIComponent(sessionId)}/confirm`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Accept: "application/json",
            },
            body: JSON.stringify({
              party: "buyer",
              accepted,
              offer_version: version,
            }),
          }
        );

        const body = await response.json().catch(() => null);

        if (!response.ok) {
          setActionError(
            errorDetail(
              body,
              `The server could not record your response (HTTP ${response.status}).`
            )
          );
          // The offer may have changed or expired; show the latest state.
          void loadDeal({ silent: true });
          return;
        }

                setResponded({ version, accepted });

        const spokenText =
          typeof body?.agent_text === "string"
            ? body.agent_text
            : accepted
              ? "Your acceptance has been sent."
              : "Your rejection has been sent.";

        setActionNotice(spokenText);

        const audioBase64 =
          typeof body?.audio_base64 === "string"
            ? body.audio_base64
            : "";

        if (audioBase64) {
          const previousPlayer = playerRef.current;

          if (previousPlayer) {
            previousPlayer.pause();
            previousPlayer.removeAttribute("src");
            previousPlayer.load();
          }

          const mime =
            typeof body.audio_mime_type === "string"
              ? body.audio_mime_type
              : "audio/wav";

          const player = new Audio(
            `data:${mime};base64,${audioBase64}`
          );

          // Same normal browser playback rate as the farmer page.
          player.playbackRate = 1.0;

          playerRef.current = player;

          player.onended = () => {
            if (playerRef.current === player) {
              playerRef.current = null;
            }
          };

          player.onerror = () => {
            if (playerRef.current === player) {
              playerRef.current = null;
            }
          };

          // Audio failure must not undo a successful buyer action.
          try {
            await player.play();
          } catch {
            if (playerRef.current === player) {
              playerRef.current = null;
            }
          }
        }

        await loadDeal({ silent: true });
      } catch (err) {
        setActionError(
          err instanceof TypeError
            ? "Cannot reach the SaudaVani backend. Please try again."
            : err instanceof Error
              ? err.message
              : "Something went wrong. Please try again."
        );
      } finally {
        submittingRef.current = false;
        setSubmitting(null);
      }
    },
    [deal, sessionId, loadDeal]
  );

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center overflow-x-hidden bg-[#f4f6f7] px-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-emerald-100 border-t-emerald-800" />
          <p className="mt-4 text-sm text-slate-600">
            Loading deal details...
          </p>
        </div>
      </main>
    );
  }

  if (error || !deal) {
    return (
      <main className="min-h-screen overflow-x-hidden bg-[#f4f6f7] px-4 py-12">
        <div className="mx-auto max-w-xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-xl font-bold text-slate-900">
            Unable to load deal
          </h1>

          <p role="alert" className="mt-3 break-words text-sm text-rose-700">
            {error || "No deal information is available."}
          </p>

          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => setRetryKey((value) => value + 1)}
              className="min-h-[44px] rounded-xl bg-emerald-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-900"
            >
              Try Again
            </button>

            <button
              type="button"
              onClick={() => router.push("/buyer")}
              className="min-h-[44px] rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              Back to Buyer Portal
            </button>
          </div>
        </div>
      </main>
    );
  }

  // Read the actual active offer returned by the backend.
  const activeOffer = deal.active_offer ?? null;

  // Prefer active offer values, then fall back to legacy fields.
  const displayQuantity =
    activeOffer?.quantity_quintals ??
    deal.quantity_quintals ??
    deal.quantity ??
    null;

  const displayPrice =
    activeOffer?.price_per_quintal ?? deal.price_per_quintal ?? null;

  const totalValue =
    activeOffer?.gross_value ??
    deal.total_value ??
    (displayQuantity != null && displayPrice != null
      ? displayQuantity * displayPrice
      : null);

  const offerExpiry = activeOffer?.expires_at ?? deal.expiry ?? null;

  const displayOfferVersion = activeOffer?.offer_version ?? deal.offer_version;

  const expiryTime = offerExpiry ? Date.parse(offerExpiry) : null;

  const expired =
    expiryTime !== null &&
    Number.isFinite(expiryTime) &&
    expiryTime <= Date.now();

  const invalidExpiry = Boolean(
    offerExpiry && expiryTime !== null && !Number.isFinite(expiryTime)
  );

  const locked = isLockedStatus(deal.deal_status);
  const awaitingFarmer = isAwaitingFarmerStatus(deal.deal_status);
  const rejectedByStatus = isRejectedStatus(deal.deal_status);

  // A response is only relevant to the offer version it was sent for.
  const respondedForThisOffer =
    responded !== null && responded.version === displayOfferVersion
      ? responded
      : null;

  const pending = isPendingStatus(deal.deal_status);

  const actionsDisabled =
    !pending ||
    expired ||
    invalidExpiry ||
    submitting !== null ||
    respondedForThisOffer !== null ||
    displayOfferVersion == null;

  const knownNonPendingState =
    locked || awaitingFarmer || rejectedByStatus;

  const qualityEntries = normalizeQualityEntries(deal.quality);

  return (
    <main className="min-h-screen overflow-x-hidden bg-[#f4f6f7] px-4 py-6 text-slate-900 sm:px-6 sm:py-10">
      <div className="mx-auto max-w-3xl">
        <header className="mb-6 flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-emerald-800 text-xl font-bold text-white">
              S
            </div>

            <div className="min-w-0">
              <h1 className="truncate text-xl font-bold">SaudaVani</h1>
              <p className="text-xs text-slate-500">Buyer deal review</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="inline-flex rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-[10px] font-bold tracking-[0.12em] text-slate-900">
                  DEMO MODE
                </span>
                <span className="text-[11px] leading-4 text-slate-500">
                  Demonstration only · No real money transferred
                </span>
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={() => router.push("/buyer")}
            className="min-h-[44px] shrink-0 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            New search
          </button>
        </header>

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-5 py-5 sm:px-7">
            <p className="text-xs font-semibold tracking-wide text-emerald-800">
              DEAL DETAILS
            </p>

            <h2 className="mt-1 text-2xl font-bold">Review proposed trade</h2>

            <p className="mt-2 break-all font-mono text-xs text-slate-500">
              Session: {deal.session_id}
            </p>
            <p className="mt-3 inline-flex flex-wrap items-center gap-x-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-slate-700">
              <span className="font-bold uppercase tracking-wide text-slate-900">
                Simulated escrow
              </span>
              <span>· No funds are held or transferred.</span>
            </p>
          </div>

          <div className="space-y-6 p-5 sm:p-7">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-sm text-slate-500">Deal status</span>

              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                    liveConnected
                      ? "bg-emerald-50 text-emerald-800"
                      : "bg-slate-100 text-slate-500"
                  }`}
                >
                  <span
                    aria-hidden
                    className={`h-1.5 w-1.5 rounded-full ${
                      liveConnected ? "bg-emerald-600" : "bg-slate-400"
                    }`}
                  />
                  {liveConnected ? "Live updates on" : "Reconnecting…"}
                </span>

                <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-700">
                  {deal.deal_status || "Unknown"}
                </span>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="min-w-0 rounded-xl bg-[#f7faf8] p-4">
                <p className="text-xs text-slate-500">Crop</p>
                <p className="mt-1 break-words text-lg font-bold">
                  {deal.crop || "—"}
                </p>
              </div>

              <div className="min-w-0 rounded-xl bg-[#f7faf8] p-4">
                <p className="text-xs text-slate-500">Variety</p>
                <p className="mt-1 break-words text-lg font-bold">
                  {deal.variety || "Not specified"}
                </p>
              </div>

              <div className="min-w-0 rounded-xl bg-[#f7faf8] p-4">
                <p className="text-xs text-slate-500">Quantity</p>
                <p className="mt-1 break-words text-lg font-bold">
                  {displayQuantity == null
                    ? "—"
                    : `${quantityFormat.format(displayQuantity)} quintals`}
                </p>
              </div>

              <div className="min-w-0 rounded-xl bg-[#f7faf8] p-4">
                <p className="text-xs text-slate-500">Price per quintal</p>

                <p className="mt-1 break-words text-lg font-bold">
                  {displayPrice == null ? "—" : currency.format(displayPrice)}
                </p>
              </div>
            </div>

            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
              <p className="text-sm font-medium text-emerald-900">
                Total proposed value
              </p>

              <p className="mt-1 break-words text-3xl font-bold text-emerald-900">
                {totalValue == null
                  ? "Not available"
                  : currency.format(totalValue)}
              </p>

              {activeOffer?.source_label && (
                <p className="mt-2 text-xs leading-relaxed text-emerald-800">
                  {activeOffer.source_label}
                </p>
              )}
            </div>

            <section>
              <h3 className="font-semibold text-slate-900">Quality summary</h3>

              <p className="mt-1 text-xs text-slate-500">
                Farmer-reported information; not independently verified.
              </p>

              {qualityEntries.length === 0 ? (
                <p className="mt-3 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
                  No quality summary was provided.
                </p>
              ) : (
                <dl className="mt-3 space-y-2">
                  {qualityEntries.map(([key, value], index) => (
                    <div
                      key={`${key}-${index}`}
                      className="flex flex-wrap justify-between gap-2 rounded-lg border border-slate-100 px-4 py-3"
                    >
                      <dt className="text-sm text-slate-600">{key}</dt>

                      <dd className="break-words text-sm font-semibold text-slate-900">
                        {displayQualityValue(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </section>

            <section className="grid gap-3 border-t border-slate-100 pt-5 sm:grid-cols-3">
              <div>
                <p className="text-xs text-slate-500">Offer version</p>
                <p className="mt-1 text-sm font-semibold">
                  {displayOfferVersion ?? "—"}
                </p>
              </div>

              <div>
                <p className="text-xs text-slate-500">Negotiation round</p>
                <p className="mt-1 text-sm font-semibold">
                  {deal.negotiation_round ?? "—"}
                </p>
              </div>

              <div>
                <p className="text-xs text-slate-500">Offer expiry</p>

                <p className="mt-1 text-sm font-semibold">
                  {offerExpiry
                    ? new Date(offerExpiry).toLocaleString("en-IN")
                    : "Not provided"}
                </p>
              </div>
            </section>

            {expired && (
              <p
                role="status"
                className="rounded-lg bg-rose-50 p-3 text-sm text-rose-800"
              >
                This offer has expired. Buyer actions are disabled.
              </p>
            )}

            {locked && (
              <p
                role="status"
                className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900"
              >
                Both parties have confirmed this offer. The agreement record is
                locked.
              </p>
            )}

            {awaitingFarmer && !locked && (
              <p
                role="status"
                className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900"
              >
                You accepted this offer. Waiting for the farmer to confirm.
              </p>
            )}

            {rejectedByStatus && (
              <p
                role="status"
                className="rounded-lg bg-rose-50 p-3 text-sm text-rose-800"
              >
                This offer was rejected. A fresh offer is required before any
                further action.
              </p>
            )}

            {!pending && !expired && !knownNonPendingState && (
              <p
                role="status"
                className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900"
              >
                This deal is not in a recognized pending buyer-response state.
                Buyer actions are disabled.
              </p>
            )}

            {invalidExpiry && (
              <p
                role="alert"
                className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900"
              >
                The expiry value could not be understood. Buyer actions are
                disabled.
              </p>
            )}

            {actionNotice && (
              <p
                role="status"
                className="rounded-lg bg-blue-50 p-3 text-sm text-blue-900"
              >
                {actionNotice}
              </p>
            )}

            {actionError && (
              <p
                role="alert"
                className="break-words rounded-lg bg-rose-50 p-3 text-sm text-rose-800"
              >
                {actionError}
              </p>
            )}

            <div className="grid gap-3 border-t border-slate-100 pt-5 sm:grid-cols-2">
              <button
                type="button"
                disabled={actionsDisabled}
                aria-busy={submitting === "accept"}
                onClick={() => void respond(true)}
                className="min-h-[48px] rounded-xl bg-emerald-800 px-4 py-3 text-sm font-bold text-white hover:bg-emerald-900 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {submitting === "accept" ? "Sending…" : "Accept Deal"}
              </button>

              <button
                type="button"
                disabled={actionsDisabled}
                aria-busy={submitting === "reject"}
                onClick={() => void respond(false)}
                className="min-h-[48px] rounded-xl border border-rose-300 bg-white px-4 py-3 text-sm font-bold text-rose-700 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {submitting === "reject" ? "Sending…" : "Reject Deal"}
              </button>
            </div>

            <p className="text-center text-xs leading-relaxed text-slate-500">
              Prototype only. A deal is locked only when both parties confirm
              the same offer version. Escrow is simulated; no funds are held or
              transferred. Actual money transferred: ₹0.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}

// Suspense wrapper for Next.js prerendering
export default function BuyerDealPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-[#f4f6f7] text-sm text-slate-600">
          Loading buyer session...
        </div>
      }
    >
      <BuyerDealPageContent />
    </Suspense>
  );
}