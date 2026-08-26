export default function Loading() {
  return (
    <main aria-busy="true" aria-live="polite" className="mx-auto max-w-[1480px] px-5 py-8 md:px-8" role="status">
      <span className="sr-only">Loading verified financial evidence…</span>
      <div aria-hidden="true" className="animate-pulse">
        <div className="mb-8 h-3 w-36 rounded-full bg-[#d9ded9]" />
        <div className="h-8 w-full max-w-md rounded-lg bg-[#dfe4de]" />
        <div className="mt-3 h-4 w-full max-w-2xl rounded bg-[#e5e9e4]" />
        <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div className="panel h-32 rounded-xl p-4" key={index}>
              <div className="h-8 w-8 rounded-lg bg-[#e4e9e3]" />
              <div className="mt-4 h-5 w-24 rounded bg-[#dde3dd]" />
              <div className="mt-2 h-3 w-32 rounded bg-[#e8ebe7]" />
            </div>
          ))}
        </div>
        <div className="panel mt-6 overflow-hidden rounded-2xl p-5">
          <div className="h-4 w-44 rounded bg-[#dfe4de]" />
          <div className="mt-5 space-y-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <div className="h-12 rounded-xl bg-[#eef1ed]" key={index} />
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
