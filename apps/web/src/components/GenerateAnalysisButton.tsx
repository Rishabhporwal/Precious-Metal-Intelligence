"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Button that triggers a fresh analysis run (LLM cost is cached/deduped upstream). */
export function GenerateAnalysisButton() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/analysis/generate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ symbol: "XAUUSD", interval: "1day" }),
      });
      const data = await res.json();
      setMsg(
        res.ok
          ? `Done (${data.status ?? "ok"}${data.llm_meta?.cache_hit ? ", cache hit" : ""}) — reloading…`
          : `Failed: ${data.detail ?? res.status}`,
      );
      if (res.ok) setTimeout(() => window.location.reload(), 1200);
    } catch (e) {
      setMsg(`Failed: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={run}
        disabled={busy}
        className="rounded border border-neutral-600 px-3 py-1.5 font-mono text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
      >
        {busy ? "generating…" : "Generate fresh analysis"}
      </button>
      {msg && <span className="text-[10px] text-neutral-500">{msg}</span>}
      <p className="text-[10px] text-neutral-600">
        Identical evidence = zero LLM spend (Redis cache + DB dedupe).
      </p>
    </div>
  );
}
