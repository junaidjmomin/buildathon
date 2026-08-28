export default function Loading() {
  return (
    <main aria-busy="true" aria-live="polite" className="mx-auto max-w-[1480px] px-5 py-8 md:px-8" role="status">
      <span className="sr-only">Loading verified financial evidence…</span>
      <div aria-hidden="true">
        <div className="skeleton mb-8 h-3 w-36" />
        <div className="skeleton h-8 w-full max-w-md" />
        <div className="skeleton mt-3 h-4 w-full max-w-2xl" />
        <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div className="panel h-32 rounded-xl p-4" key={index}>
              <div className="skeleton h-8 w-8 rounded-lg" />
              <div className="skeleton mt-4 h-5 w-24" />
              <div className="skeleton mt-2 h-3 w-32" />
            </div>
          ))}
        </div>
        <div className="panel mt-6 overflow-hidden rounded-2xl p-5">
          <div className="skeleton h-4 w-44" />
          <div className="mt-5 space-y-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <div className="skeleton h-12 rounded-xl" key={index} />
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
