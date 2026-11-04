import { NewsEventsView } from "@/components/NewsEventsView";

export const metadata = { title: "Global Intelligence — PMI" };

export default function NewsPage() {
  return (
    <main className="page rise">
      <div className="mx-auto max-w-4xl">
        <header className="mb-5">
          <h1 className="page-title">Global Intelligence</h1>
          <p className="page-sub">
            World events clustered and verified — many articles about one event count as one event.
          </p>
        </header>
        <NewsEventsView />
        <footer className="mt-8 border-t border-line-subtle pt-4 text-[10.5px] leading-relaxed text-faint">
          Verification: CONFIRMED = ≥2 independent sources · REPORTED = single source · DEVELOPING =
          actively updating. A major unverified event never triggers a high-confidence signal by
          itself. Headlines link to their original sources.
        </footer>
      </div>
    </main>
  );
}
