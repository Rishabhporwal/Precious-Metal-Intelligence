import { Suspense } from "react";
import Link from "next/link";
import { TodayPlan, TodayPlanSkeleton } from "@/components/TodayPlan";

function QuickActions() {
  const actions = [
    {
      href: "/strategies",
      title: "See the strategies",
      detail: "Every pattern the engine watches — its signals, right on the chart.",
      emoji: "📈",
    },
    {
      href: "/news",
      title: "World news",
      detail: "What's happening around the world that moves gold.",
      emoji: "🌍",
    },
    {
      href: "/learn",
      title: "Learn the basics",
      detail: "Gold-market words explained in plain English.",
      emoji: "🎓",
    },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {actions.map((a) => (
        <Link key={a.href} href={a.href} className="card card-hover block p-5">
          <div className="text-[22px] leading-none">{a.emoji}</div>
          <div className="mt-2.5 text-[13.5px] font-semibold text-ink">{a.title}</div>
          <div className="mt-1 text-[12px] leading-relaxed text-muted">{a.detail}</div>
        </Link>
      ))}
    </div>
  );
}

export default function HomePage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-3xl">
        <header className="mb-6">
          <h1 className="page-title">What should I do with gold today?</h1>
          <p className="page-sub">One clear answer — the call, the plan, and the reasons.</p>
        </header>

        <Suspense fallback={<TodayPlanSkeleton />}>
          <TodayPlan />
        </Suspense>

        <div className="section-gap" />
        <QuickActions />

        <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] leading-relaxed text-faint">
          All data comes from real market feeds. Aurex is not a broker and never places live orders.
        </footer>
      </div>
    </main>
  );
}
