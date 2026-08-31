"use client";

import { CircleAlert, House, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

import { BrandMark, EvidenceMap } from "@/components/brand-assets";

import "./globals.css";

export default function GlobalError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error("sl3dge global boundary caught an error", {
      digest: error.digest ?? "client-error",
    });
  }, [error]);

  return (
    <html className="h-full antialiased" lang="en">
      <body className="min-h-full">
        <title>Application recovery | sl3dge</title>
        <main className="grid min-h-dvh place-items-center px-4 py-8 sm:px-6">
          <section
            aria-describedby="global-error-description"
            aria-labelledby="global-error-title"
            className="panel grid w-full max-w-[960px] overflow-hidden rounded-xl lg:grid-cols-[minmax(0,1.15fr)_minmax(300px,0.85fr)]"
          >
            <div className="p-6 sm:p-8 lg:p-10">
              <Link
                aria-label="sl3dge overview"
                className="inline-flex items-center gap-3 rounded-md"
                href="/"
              >
                <span className="grid h-10 w-10 place-items-center overflow-hidden rounded-lg border border-[var(--line)] bg-[var(--ink-700)]">
                  <BrandMark className="h-9 w-9 object-contain" size={36} />
                </span>
                <span>
                  <span className="block text-lg font-semibold leading-5 tracking-[-0.04em] text-[var(--paper)]">
                    sl3dge
                  </span>
                  <span className="mt-1 block text-[9px] font-medium uppercase tracking-[0.15em] text-[var(--paper-faint)]">
                    Financial evidence
                  </span>
                </span>
              </Link>

              <div className="mt-9" aria-live="assertive" role="alert">
                <span className="grid h-11 w-11 place-items-center rounded-lg border border-[var(--crimson-line)] bg-[var(--crimson-soft)] text-[var(--crimson-deep)]">
                  <CircleAlert aria-hidden="true" size={20} strokeWidth={1.9} />
                </span>
                <p className="mt-6 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--crimson)]">
                  Application recovery
                </p>
                <h1
                  className="mt-2 text-[clamp(1.75rem,4vw,2.25rem)] font-semibold leading-tight tracking-[-0.04em] text-[var(--paper)]"
                  id="global-error-title"
                >
                  The workspace couldn&apos;t start
                </h1>
                <p
                  className="mt-3 max-w-xl text-sm leading-6 text-[var(--paper-dim)]"
                  id="global-error-description"
                >
                  A required part of the application did not load. Try starting it again, or reopen the overview
                  to begin a fresh session.
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
                  Start again
                </button>
                <Link
                  className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--ink-800)] px-4 py-2.5 text-sm font-semibold text-[var(--paper)] transition-colors hover:bg-[var(--ink-700)]"
                  href="/"
                >
                  <House aria-hidden="true" size={16} />
                  Reopen overview
                </Link>
              </div>

              {error.digest ? (
                <p className="mt-5 text-xs leading-5 text-[var(--paper-faint)]">
                  If the workspace still does not start, share the support reference with your administrator.
                </p>
              ) : null}
            </div>

            <div
              aria-hidden="true"
              className="hidden border-l border-[var(--line)] bg-[var(--ink-700)] p-3 lg:block"
            >
              <div className="h-full min-h-[520px] overflow-hidden rounded-lg border border-[var(--line)] bg-[var(--ink-800)]">
                <EvidenceMap className="h-full w-full object-cover" decorative eager />
              </div>
            </div>
          </section>
        </main>
      </body>
    </html>
  );
}
