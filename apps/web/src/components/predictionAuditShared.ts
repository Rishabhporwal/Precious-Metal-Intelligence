export const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  pending: { text: "In progress", cls: "bg-blue-500/10 text-blue-500" },
  hit_t1: { text: "T1 hit", cls: "bg-emerald-500/10 text-emerald-500" },
  hit_t2: { text: "T1+T2 hit", cls: "bg-emerald-500/15 text-emerald-400" },
  stopped: { text: "Stopped out", cls: "bg-red-500/10 text-red-500" },
  stopped_pre_entry: { text: "Never filled", cls: "bg-amber-500/10 text-amber-500" },
  superseded: { text: "Superseded", cls: "bg-zinc-500/10 text-zinc-400" },
  expired: { text: "Expired", cls: "bg-zinc-500/10 text-zinc-400" },
};

export const fmtUsd = (v: number | null | undefined) =>
  v == null ? "—" : `$${v.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
