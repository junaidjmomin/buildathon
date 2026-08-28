"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, LoaderCircle, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { Badge, EmptyState, ErrorState, PageHeader } from "@/components/ui/primitives";
import { api } from "@/lib/api";

export default function ControlsPage() {
  const controls = useQuery({ queryKey: ["controls"], queryFn: api.controls });

  return (
    <main className="mx-auto max-w-[1160px] px-5 py-8 md:px-8 md:py-10">
      <PageHeader
        eyebrow={
          <>
            <ShieldCheck size={14} /> Approved control registry
          </>
        }
        title="Controls"
        subtitle="Effective-dated rules used by the deterministic engine. Rates and money tolerances remain Decimal strings."
      />

      {controls.isPending ? (
        <LoaderCircle className="mx-auto mt-20 animate-spin text-[var(--evergreen)]" />
      ) : controls.isError ? (
        <div className="mt-7">
          <ErrorState what="Controls" onRetry={() => void controls.refetch()} />
        </div>
      ) : controls.data?.length === 0 ? (
        <div className="mt-7">
          <EmptyState
            title="No controls have been approved yet"
            body="Approve proposals on the Agreements page to populate the registry."
          />
        </div>
      ) : (
        <section className="mt-7 space-y-3">
          {controls.data?.map((control) => (
            <article key={control.id} className="panel rounded-2xl p-5">
              <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                <div>
                  <p className="font-mono text-[10px] text-[var(--paper-faint)]">
                    {control.id} · v{control.version}
                  </p>
                  <h2 className="mt-1 text-base font-semibold text-[var(--paper)]">
                    <Link
                      href={`/controls/${control.logical_control_key}`}
                      className="inline-flex items-center gap-1 transition-colors duration-150 hover:underline"
                    >
                      {control.name} <ArrowRight size={13} className="text-[var(--evergreen)]" />
                    </Link>
                  </h2>
                  <p className="mt-2 text-xs text-[var(--paper-dim)]">
                    {control.scope} · {control.expected}
                  </p>
                  <p className="mt-2 text-[11px] text-[var(--paper-faint)]">
                    {control.source} · {control.source_clause}
                  </p>
                </div>
                <Badge
                  status={control.status === "APPROVED" ? "PASS" : "DRAFT"}
                  label={control.status}
                />
              </div>
              <pre className="number-tabular mt-4 overflow-x-auto rounded-xl border border-[var(--line)] bg-[var(--ink-700)] p-3 font-mono text-[10px] leading-5 text-[var(--paper-dim)]">
                {JSON.stringify(control.parameters, null, 2)}
              </pre>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
