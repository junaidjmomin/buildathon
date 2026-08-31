import { FileQuestion, House } from "lucide-react";
import Link from "next/link";

import { EvidenceMap } from "@/components/brand-assets";

export default function NotFound() {
  return (
    <main className="grid min-h-[calc(100dvh-4rem)] place-items-center px-4 py-8 sm:px-6 lg:px-8">
      <section
        aria-describedby="not-found-description"
        aria-labelledby="not-found-title"
        className="panel grid w-full max-w-[920px] overflow-hidden rounded-xl lg:grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)]"
      >
        <div className="p-6 sm:p-8 lg:p-10">
          <span className="grid h-11 w-11 place-items-center rounded-lg border border-[var(--sky-line)] bg-[var(--sky-soft)] text-[var(--sky)]">
            <FileQuestion aria-hidden="true" size={20} strokeWidth={1.9} />
          </span>
          <p className="mt-6 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--sky)]">
            404 · Page not found
          </p>
          <h1
            className="mt-2 text-[clamp(1.75rem,4vw,2.25rem)] font-semibold leading-tight tracking-[-0.04em] text-[var(--paper)]"
            id="not-found-title"
          >
            We can&apos;t find this page
          </h1>
          <p
            className="mt-3 max-w-xl text-sm leading-6 text-[var(--paper-dim)]"
            id="not-found-description"
          >
            The address may be outdated, or this resource is no longer available in the current workspace. Use
            the overview to open a current run, control, or evidence view.
          </p>

          <Link
            className="mt-7 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[var(--evergreen-deep)] sm:w-auto"
            href="/"
          >
            <House aria-hidden="true" size={16} />
            Go to overview
          </Link>
        </div>

        <div
          aria-hidden="true"
          className="hidden border-l border-[var(--line)] bg-[var(--ink-700)] p-3 lg:block"
        >
          <div className="h-full min-h-80 overflow-hidden rounded-lg border border-[var(--line)] bg-[var(--ink-800)]">
            <EvidenceMap className="h-full w-full object-cover" decorative />
          </div>
        </div>
      </section>
    </main>
  );
}
