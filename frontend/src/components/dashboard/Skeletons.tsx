const Bone = ({ className }: { className: string }) => <div aria-hidden="true" className={`animate-pulse rounded-lg bg-zinc-200/80 ${className}`} />;

const KpiSkeleton = () => (
  <div className="card p-5 sm:p-6 flex flex-col gap-3">
    <div className="flex items-center justify-between"><Bone className="h-4 w-24" /><Bone className="h-9 w-9 rounded-xl" /></div>
    <Bone className="h-11 w-20" />
    <Bone className="h-3 w-40" />
  </div>
);

export const DashboardSkeleton = () => (
  <div data-testid="dashboard-skeleton" role="status" aria-live="polite" aria-label="Memuat data" className="space-y-6">
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 md:gap-6">
      {[0, 1, 2, 3].map((i) => <KpiSkeleton key={i} />)}
    </div>
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
      <div className="card lg:col-span-2 p-5 sm:p-6">
        <div className="mb-6 flex items-start justify-between"><Bone className="h-5 w-40" /><Bone className="h-4 w-32" /></div>
        <div className="flex h-56 items-end gap-2">
          {Array.from({ length: 24 }, (_, i) => <Bone key={i} className={`flex-1 ${i % 3 === 0 ? "h-1/2" : i % 3 === 1 ? "h-1/4" : "h-1/3"}`} />)}
        </div>
      </div>
      <div className="card p-5 sm:p-6">
        <div className="mb-4 flex items-start gap-3"><Bone className="h-9 w-9 rounded-xl" /><Bone className="h-5 w-28" /></div>
        {[0, 1].map((i) => (
          <div key={i} className="flex items-center justify-between gap-3 border-t border-line py-3">
            <div className="space-y-2"><Bone className="h-4 w-28" /><Bone className="h-3 w-44" /></div>
            <Bone className="h-6 w-24 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  </div>
);
