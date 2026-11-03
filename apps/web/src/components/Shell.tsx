"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { LivePriceChip } from "./LivePriceChip";
import { ThemeToggle } from "./ThemeToggle";

/** Consumer-first nav. Technical tools live under "Advanced" for power users. */
const NAV: { group: string; items: { href: string; label: string; icon: ReactNode }[] }[] = [
  {
    group: "For you",
    items: [
      { href: "/", label: "Home", icon: <IconHome /> },
      { href: "/paper", label: "My Practice", icon: <IconBook /> },
      { href: "/alerts", label: "Alerts", icon: <IconBell /> },
    ],
  },
  {
    group: "Strategy intelligence",
    items: [
      { href: "/chart", label: "Chart", icon: <IconCandle /> },
      { href: "/strategies", label: "Strategy Analysis", icon: <IconTarget /> },
      { href: "/performance", label: "Performance", icon: <IconPulse /> },
      { href: "/confluence", label: "Confluence", icon: <IconTarget /> },
      { href: "/setups", label: "Trade Ideas", icon: <IconZap /> },
    ],
  },
  {
    group: "Market data",
    items: [
      { href: "/markets", label: "Prices", icon: <IconCandle /> },
      { href: "/macro", label: "Economy", icon: <IconGlobe /> },
      { href: "/learn", label: "Learn", icon: <IconSpark /> },
    ],
  },
  {
    group: "Advanced",
    items: [
      { href: "/analyst", label: "AI Analyst", icon: <IconSpark /> },
      { href: "/backtests", label: "Backtests", icon: <IconClock /> },
      { href: "/settings", label: "Settings", icon: <IconTarget /> },
      { href: "/status", label: "System", icon: <IconPulse /> },
    ],
  },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-56 flex-col border-r border-line-subtle bg-panel lg:flex">
        <Brand />
        <nav className="flex-1 overflow-y-auto pb-4">
          {NAV.map((g) => (
            <div key={g.group}>
              <div className="nav-group">{g.group}</div>
              {g.items.map((item) => {
                const active = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`nav-item ${active ? "nav-item-active" : ""}`}
                  >
                    <span className="opacity-70">{item.icon}</span>
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="flex items-center justify-between gap-2 border-t border-line-subtle p-4">
          <LivePriceChip />
          <ThemeToggle />
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="fixed inset-x-0 top-0 z-40 border-b border-line-subtle bg-panel/95 backdrop-blur lg:hidden">
        <div className="flex items-center justify-between px-4 py-2.5">
          <Brand compact />
          <div className="flex items-center gap-2">
            <LivePriceChip compact />
            <ThemeToggle />
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2">
          {NAV.flatMap((g) => g.items).map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`pill shrink-0 ${active ? "pill-gold" : ""}`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <main className="min-w-0 flex-1 pt-[104px] lg:pt-0 lg:pl-56">{children}</main>
    </div>
  );
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5 px-4 py-4">
      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-b from-[#f0c04a] to-[#c99414] text-[13px] font-bold text-[#4a3503] shadow-[0_1px_3px_rgba(120,90,0,0.35)] dark:text-[#231a02]">
        ◆
      </span>
      <span className="leading-tight">
        <span className="block text-[13.5px] font-semibold tracking-tight text-ink">PMI</span>
        {!compact && (
          <span className="block text-[9.5px] font-medium uppercase tracking-[0.14em] text-faint">
            Gold Insights
          </span>
        )}
      </span>
    </Link>
  );
}

/* --- 16px stroke icons (geometric, 1.5px stroke) --- */
function IconBase({ children }: { children: ReactNode }) {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}
function IconHome() {
  return (
    <IconBase>
      <path d="M2.5 7L8 2.5 13.5 7v6a1 1 0 01-1 1h-9a1 1 0 01-1-1V7z" />
      <path d="M6.5 14v-4h3v4" />
    </IconBase>
  );
}
function IconCandle() {
  return (
    <IconBase>
      <path d="M4 6.5v6M2.5 8h3M12 3.5v6M10.5 5h3" />
      <path d="M4 3v1.5M12 11.5V13" />
    </IconBase>
  );
}
function IconSpark() {
  return (
    <IconBase>
      <path d="M8 1.5l1.6 4.3L14 7.2l-4.4 1.6L8 13.5 6.4 8.8 2 7.2l4.4-1.4L8 1.5z" />
    </IconBase>
  );
}
function IconTarget() {
  return (
    <IconBase>
      <circle cx="8" cy="8" r="6" />
      <circle cx="8" cy="8" r="2.8" />
      <circle cx="8" cy="8" r="0.4" fill="currentColor" />
    </IconBase>
  );
}
function IconZap() {
  return (
    <IconBase>
      <path d="M8.7 1.5L3 9h4l-.7 5.5L12 7H8l.7-5.5z" />
    </IconBase>
  );
}
function IconBook() {
  return (
    <IconBase>
      <path d="M2.5 2.5h9a2 2 0 012 2v9h-9a2 2 0 01-2-2v-9z" />
      <path d="M2.5 11.5a2 2 0 012-2h9" />
    </IconBase>
  );
}
function IconClock() {
  return (
    <IconBase>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4.5V8l2.5 1.5" />
    </IconBase>
  );
}
function IconBell() {
  return (
    <IconBase>
      <path d="M4 7a4 4 0 018 0c0 3 1.2 4 1.2 4H2.8S4 10 4 7z" />
      <path d="M6.8 13a1.3 1.3 0 002.4 0" />
    </IconBase>
  );
}
function IconGlobe() {
  return (
    <IconBase>
      <circle cx="8" cy="8" r="6" />
      <path d="M2 8h12M8 2c1.8 1.6 2.7 3.7 2.7 6S9.8 12.4 8 14c-1.8-1.6-2.7-3.7-2.7-6S6.2 3.6 8 2z" />
    </IconBase>
  );
}
function IconPulse() {
  return (
    <IconBase>
      <path d="M1.5 8.5h3l1.5-4 2.5 7 1.7-3h4.3" />
    </IconBase>
  );
}
