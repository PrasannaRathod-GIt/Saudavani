"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

export default function BuyerHomePage() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = sessionId.trim();
    if (!id) return;
    router.push(`/buyer/${encodeURIComponent(id)}`);
  }

  return (
    <main className="min-h-screen bg-[#f4f6f7] px-4 py-10 text-slate-900">
      <div className="mx-auto max-w-xl">
        <header className="mb-8 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-800 text-xl font-bold text-white">
            S
          </div>
          <div className="min-w-0">
            <h1 className="text-2xl font-bold">SaudaVani</h1>
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
        </header>

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <p className="text-sm font-semibold text-emerald-800">BUYER PORTAL</p>
          <h2 className="mt-2 text-2xl font-bold">Review a trade</h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">
            Enter the deal session ID shared by the farmer to view the
            proposed crop, quantity, price and quality summary.
          </p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div>
              <label
                htmlFor="session-id"
                className="mb-2 block text-sm font-semibold text-slate-700"
              >
                Deal session ID
              </label>
              <input
                id="session-id"
                type="text"
                value={sessionId}
                onChange={(event) => setSessionId(event.target.value)}
                placeholder="Example: SV-XXXXXXXX"
                required
                autoComplete="off"
                className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none transition focus:border-emerald-700 focus:ring-2 focus:ring-emerald-100"
              />
            </div>

            <button
              type="submit"
              disabled={!sessionId.trim()}
              className="w-full rounded-xl bg-emerald-800 px-4 py-3 font-semibold text-white transition hover:bg-emerald-900 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Load Deal
            </button>
          </form>

          <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900">
            Hackathon prototype: a session ID is not authentication.
            Do not use this demo for public or real trading.
          </div>
        </section>

        <p className="mt-6 text-center text-xs text-slate-500">
          SaudaVani · Simulated escrow only · Actual money transferred: ₹0
        </p>
      </div>
    </main>
  );
}
