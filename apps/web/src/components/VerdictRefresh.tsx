"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Triggers a fresh Daily Verdict, then refreshes the server-rendered page. */
export function VerdictRefresh() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/verdict/generate`, { method: "POST" });
      if (!res.ok) {
        const d = await res.json().catch(() => null);
        setErr(d?.detail ?? `failed (${res.status})`);
      } else {
        router.refresh();
      }
    } catch {
      setErr("network error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {err && <span className="text-[11px] text-down">{err}</span>}
      <button onClick={run} disabled={busy} className="btn btn-sm">
        {busy ? "Analyzing news, economy & charts…" : "Refresh verdict"}
      </button>
    </div>
  );
}
