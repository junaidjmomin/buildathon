function Skeleton({ className }: { className: string }) {
  return <span className={`skeleton block ${className}`} />;
}

function SummaryPlaceholder() {
  return (
    <div className="px-5 py-4">
      <Skeleton className="h-2.5 w-20" />
      <Skeleton className="mt-3 h-6 w-28" />
      <Skeleton className="mt-2 h-3 w-36 max-w-full" />
    </div>
  );
}

export default function Loading() {
  return (
    <main
      aria-busy="true"
      aria-live="polite"
      className="mx-auto w-full max-w-[1400px] px-5 py-7 md:px-8 md:py-9"
      role="status"
    >
      <span className="sr-only">Loading workspace content.</span>

      <div aria-hidden="true">
        <header className="mb-6 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
          <div className="w-full max-w-2xl">
            <Skeleton className="h-2.5 w-28" />
            <Skeleton className="mt-3 h-9 w-72 max-w-[85%]" />
            <Skeleton className="mt-3 h-3.5 w-full max-w-xl" />
          </div>
          <Skeleton className="h-11 w-40" />
        </header>

        <section className="panel overflow-hidden rounded-xl">
          <div className="border-b border-[var(--line)] bg-[var(--ink-700)] px-5 py-4">
            <Skeleton className="h-3.5 w-40" />
            <Skeleton className="mt-2 h-3 w-full max-w-md" />
          </div>
          <div className="grid divide-y divide-[var(--line)] sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-4">
            <SummaryPlaceholder />
            <SummaryPlaceholder />
            <SummaryPlaceholder />
            <SummaryPlaceholder />
          </div>
        </section>

        <div className="mt-5 grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
          <section className="panel overflow-hidden rounded-xl">
            <div className="flex items-center justify-between gap-4 border-b border-[var(--line)] px-5 py-4">
              <Skeleton className="h-3.5 w-36" />
              <Skeleton className="h-7 w-20" />
            </div>
            <div className="space-y-3 p-5">
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          </section>

          <aside className="panel overflow-hidden rounded-xl">
            <div className="border-b border-[var(--line)] bg-[var(--ink-700)] px-5 py-4">
              <Skeleton className="h-2.5 w-24" />
              <Skeleton className="mt-3 h-5 w-44 max-w-full" />
              <Skeleton className="mt-2 h-3 w-full" />
              <Skeleton className="mt-2 h-3 w-4/5" />
            </div>
            <div className="p-5">
              <Skeleton className="h-11 w-full" />
              <Skeleton className="mt-3 h-11 w-full" />
            </div>
          </aside>
        </div>
      </div>
    </main>
  );
}
