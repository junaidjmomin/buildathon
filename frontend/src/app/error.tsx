"use client";

import { CircleAlert, House, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

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
    <main className="grid min-h-[calc(100vh-4rem)] place-items-center px-5 py-12">
      <section
        aria-labelledby="route-error-title"
        className="panel w-full max-w-xl rounded-2xl p-7 text-center sm:p-10"
        role="alert"
      >
        <span className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-[#fff0e8] text-[#bd4e24]">
          <CircleAlert aria-hidden="true" size={22} />
        </span>
        <p className="mt-5 text-[10px] font-bold uppercase tracking-[0.15em] text-[#bd522a]">
          Safe recovery mode
        </p>
        <h1 id="route-error-title" className="mt-2 text-2xl font-semibold tracking-[-0.035em]">
          This view could not be loaded
        </h1>
        <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-[#66716b]">
          No financial decision was changed. Retry the request, or return to the control overview.
        </p>
        {error.digest ? (
          <p className="mt-4 font-mono text-[10px] text-[#7b857f]">
            Reference: {error.digest}
          </p>
        ) : null}
        <div className="mt-7 flex flex-col justify-center gap-3 sm:flex-row">
          <button
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#112a2b] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#19393a] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1e6b51]"
            onClick={() => retry()}
            type="button"
          >
            <RotateCcw aria-hidden="true" size={15} />
            Try again
          </button>
          <Link
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-[#cfd9d1] bg-white px-4 py-2.5 text-sm font-semibold text-[#24332c] transition hover:bg-[#f7f8f5] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1e6b51]"
            href="/"
          >
            <House aria-hidden="true" size={15} />
            Control overview
          </Link>
        </div>
      </section>
    </main>
  );
}
