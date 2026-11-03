import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Shell } from "@/components/Shell";
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
  title: "PMI — Precious Metals Intelligence",
  description:
    "AI-powered Gold market intelligence: SMC/ICT strategy detection, macro analysis, risk-validated setups, paper trading and reproducible backtesting.",
};

export const viewport: Viewport = {
  themeColor: "#08090a",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem("pmi-theme");if(t==="dark")document.documentElement.dataset.theme="dark";}catch(e){}`,
          }}
        />
      </head>
      <body className="min-h-full bg-canvas text-ink">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
