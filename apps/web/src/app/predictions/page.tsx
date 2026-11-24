import { Suspense } from "react";
import PredictionAuditView from "@/components/PredictionAuditView";

function AuditSkeleton() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-ink">Prediction Audit</h1>
      <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded-lg border border-line-subtle bg-card" />
        ))}
      </div>
      <div className="mt-6 space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-28 animate-pulse rounded-lg border border-line-subtle bg-card" />
        ))}
      </div>
    </div>
  );
}

export default function PredictionsPage() {
  return (
    <Suspense fallback={<AuditSkeleton />}>
      <PredictionAuditView />
    </Suspense>
  );
}
