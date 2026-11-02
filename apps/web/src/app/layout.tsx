import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Precious Metals Intelligence",
  description: "AI-powered Gold & Silver market intelligence platform",
};

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/markets", label: "Markets" },
  { href: "/status", label: "Status" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-neutral-950 text-neutral-200">
        <nav className="border-b border-neutral-800 bg-neutral-950/95 px-6 py-3">
          <div className="mx-auto flex max-w-4xl items-center justify-between">
            <Link href="/" className="font-mono text-sm font-semibold text-neutral-100">
              PMI · Precious Metals Intelligence
            </Link>
            <div className="flex gap-4 font-mono text-xs text-neutral-400">
              {NAV.map((item) => (
                <Link key={item.href} href={item.href} className="hover:text-neutral-100">
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
        </nav>
        <div className="flex-1">{children}</div>
      </body>
    </html>
  );
}
