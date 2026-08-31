"use client";

import { CircleAlert, House, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

import { EvidenceMap } from "@/components/brand-assets";

export default function ErrorBoundary({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error("sl3dge route boundary caught an error", {
      digest: error.digest ?? "client-error",
    });
  }, [error]);

  return (
    <main className="grid min-h-[calc(100dvh-4rem)] place-items-center px-4 py-8 sm:px-6 lg:px-8">
      <section
        aria-describedby="route-error-description"
        aria-labelledby="route-error-title"
        className="panel grid w-full max-w-[920px] overflow-hidden rounded-xl lg:grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)]"
      >
        <div className="p-6 sm:p-8 lg:p-10">
          <div aria-live="assertive" role="alert">
            <span className="grid h-11 w-11 place-items-center rounded-lg border border-[var(--crimson-line)] bg-[var(--crimson-soft)] text-[var(--crimson-deep)]">
              <CircleAlert aria-hidden="true" size={20} strokeWidth={1.9} />
            </span>
            <p className="mt-6 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--crimson)]">
              Page load interrupted
            </p>
            <h1
              className="mt-2 text-[clamp(1.75rem,4vw,2.25rem)] font-semibold leading-tight tracking-[-0.04em] text-[var(--paper)]"
              id="route-error-title"
            >
              We couldn&apos;t load this page
            </h1>
            <p
              className="mt-3 max-w-xl text-sm leading-6 text-[var(--paper-dim)]"
              id="route-error-description"
            >
              The workspace stopped before this page finished loading. Try the request again, or return to the
              overview and continue from there.
            </p>
          </div>

          {error.digest ? (
            <div className="mt-5 rounded-lg border border-[var(--line)] bg-[var(--ink-700)] px-4 py-3">
              <p className="text-[10px] font-semibold uppercase tracking-[0.11em] text-[var(--paper-faint)]">
                Support reference
              </p>
              <code className="mt-1.5 block break-all font-mono text-[11px] text-[var(--paper-dim)]">
                {error.digest}
              </code>
            </div>
          ) : null}

          <div className="mt-7 flex flex-col gap-3 sm:flex-row">
            <button
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-[var(--evergreen)] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[var(--evergreen-deep)]"
              onClick={() => retry()}
              type="button"
            >
              <RotateCcw aria-hidden="true" size={16} />
              Try loading again
            </button>
            <Link
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-4 py-2.5 text-sm font-semibold text-[var(--paper)] transition-colors hover:bg-[var(--ink-700)]"
              href="/"
            >
              <House aria-hidden="true" size={16} />
              Go to overview
            </Link>
          </div>

          {error.digest ? (
            <p className="mt-5 text-xs leading-5 text-[var(--paper-faint)]">
              If this keeps happening, share the support reference with your workspace administrator.
            </p>
          ) : null}
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
