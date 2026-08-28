import { ArrowLeft, SearchX } from "lucide-react";
import Link from "next/link";

export default function NotFound() {
  return (
    <main className="grid min-h-[calc(100vh-4rem)] place-items-center px-5 py-12">
      <section aria-labelledby="not-found-title" className="panel w-full max-w-xl rounded-2xl p-7 text-center sm:p-10">
        <span className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]">
          <SearchX aria-hidden="true" size={22} />
        </span>
        <p className="mt-5 text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--evergreen)]">
          404 · Resource not found
        </p>
        <h1 id="not-found-title" className="mt-2 text-2xl font-semibold tracking-[-0.035em] text-[var(--paper)]">
          This evidence view does not exist
        </h1>
        <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-[var(--paper-dim)]">
          The link may be outdated, or the requested run, control, or case is not available in this workspace.
        </p>
        <Link
          className="mt-7 inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-sm font-semibold text-[#06120c] transition duration-150 hover:brightness-110"
          href="/"
        >
          <ArrowLeft aria-hidden="true" size={15} />
          Return to control overview
        </Link>
      </section>
    </main>
  );
}
