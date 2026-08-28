"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CalendarRange, LoaderCircle, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Badge, ErrorState, PageHeader } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { Control } from "@/types/api";

export default function ControlDetailPage() {
  const { controlKey } = useParams<{ controlKey: string }>();
  const controls = useQuery({ queryKey: ["controls"], queryFn: api.controls });
  const versions = useQuery({
    queryKey: ["control-versions", controlKey],
    queryFn: () => api.controlVersions(controlKey),
  });

  if (controls.isPending || versions.isPending) {
    return (
      <div className="grid min-h-[calc(100vh-64px)] place-items-center">
        <LoaderCircle className="animate-spin text-[var(--evergreen)]" />
      </div>
    );
  }

  const record = (controls.data ?? []).find((control) => control.logical_control_key === controlKey);
  const history = (versions.data ?? [])
    .slice()
    .sort((a, b) => a.version - b.version);
  const current = record ?? history[history.length - 1];

  if (!current) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
        <Link
          href="/controls"
          className="mb-6 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--evergreen)] transition-colors duration-150 hover:underline"
        >
          <ArrowLeft size={13} /> All controls
        </Link>
        <div className="panel rounded-2xl p-8 text-sm text-[var(--paper-dim)]" role="alert">
          No control was found for <span className="font-mono">{controlKey}</span>.{" "}
          <button
            type="button"
            onClick={() => {
              controls.refetch();
              versions.refetch();
            }}
            className="font-semibold underline underline-offset-2"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-[1160px] px-5 py-8 md:px-8 md:py-10">
      <PageHeader
        back={{ href: "/controls", label: "All controls" }}
        eyebrow={
          <>
            <ShieldCheck size={14} /> Control provenance
          </>
        }
        title={current.name}
        subtitle={
          <span className="font-mono text-[var(--paper-faint)]">
            {current.logical_control_key} · v{current.version} · {current.id}
          </span>
        }
      />

      <section className="panel rounded-2xl p-5">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
          <div>
            <p className="text-xs text-[var(--paper-dim)]">
              {current.control_type} · {current.scope} · {current.expected}
            </p>
          </div>
          <Badge
            status={current.status === "APPROVED" ? "PASS" : "DRAFT"}
            label={current.status}
          />
        </div>
        <div className="mt-4 grid gap-3 border-t border-[var(--line)] pt-4 text-[10px] text-[var(--paper-faint)] sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <span className="block uppercase tracking-[0.1em]">Effective window</span>
            <strong className="mt-1 block text-xs text-[var(--paper)]">
              {current.effective_from} → {current.effective_to ?? "open"}
            </strong>
          </div>
          <div>
            <span className="block uppercase tracking-[0.1em]">Extraction method</span>
            <strong className="mt-1 block text-xs text-[var(--paper)]">{current.extraction_method}</strong>
          </div>
          <div>
            <span className="block uppercase tracking-[0.1em]">Approved at</span>
            <strong className="mt-1 block text-xs text-[var(--paper)]">
              {current.approved_at ?? "not approved"}
            </strong>
          </div>
          <div>
            <span className="block uppercase tracking-[0.1em]">Supersedes</span>
            <strong className="mt-1 block font-mono text-xs text-[var(--paper)]">
              {current.supersedes_control_id ?? "none"}
            </strong>
          </div>
        </div>
      </section>

      <section className="mt-6 grid gap-5 lg:grid-cols-2">
        <div className="panel overflow-hidden rounded-2xl">
          <div className="border-b border-[var(--line)] px-5 py-4">
            <h2 className="text-sm font-semibold text-[var(--paper)]">Typed parameters</h2>
            <p className="mt-1 text-xs text-[var(--paper-dim)]">
              Rates and tolerances remain decimal strings
            </p>
          </div>
          <pre className="number-tabular overflow-x-auto p-5 font-mono text-[10px] leading-5 text-[var(--paper-dim)]">
            {JSON.stringify(current.parameters, null, 2)}
          </pre>
          <div className="border-t border-[var(--line)] px-5 py-4">
            <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--paper-faint)]">Applicability conditions</p>
            <p className="mt-1 font-mono text-[10px] text-[var(--paper-dim)]">
              {current.conditions.join(" · ") || "none"}
            </p>
          </div>
        </div>

        <div className="panel overflow-hidden rounded-2xl">
          <div className="border-b border-[var(--line)] px-5 py-4">
            <h2 className="text-sm font-semibold text-[var(--paper)]">Contract provenance</h2>
            <p className="mt-1 text-xs text-[var(--paper-dim)]">
              Where this control came from, clause by clause
            </p>
          </div>
          <div className="divide-y divide-[var(--line)]">
            <div className="p-4">
              <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--paper-faint)]">Source</p>
              <p className="mt-1 text-xs text-[var(--paper)]">{current.source}</p>
            </div>
            <div className="p-4">
              <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--paper-faint)]">Source clause</p>
              <p className="mt-1 text-xs text-[var(--paper)]">{current.source_clause}</p>
            </div>
            <div className="p-4">
              <p className="text-[10px] uppercase tracking-[0.1em] text-[var(--paper-faint)]">Agreement</p>
              {current.agreement_id ? (
                <Link
                  href={`/agreements/${current.agreement_id}`}
                  className="mt-1 inline-flex items-center gap-1 font-mono text-xs font-semibold text-[var(--evergreen)] transition-colors duration-150 hover:underline"
                >
                  {current.agreement_id}
                </Link>
              ) : (
                <p className="mt-1 text-xs text-[var(--paper)]">not linked to an agreement</p>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="panel mt-6 rounded-2xl p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-[var(--paper)]">
          <CalendarRange size={16} className="text-[var(--evergreen)]" /> Immutable version timeline
        </div>
        {versions.isError ? (
          <div className="mt-4">
            <ErrorState what="Version history" onRetry={() => versions.refetch()} />
          </div>
        ) : (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {history.map((version) => (
              <ControlVersionCard key={version.id} version={version} isCurrent={version.id === current.id} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function ControlVersionCard({ version, isCurrent }: { version: Control; isCurrent: boolean }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--ink-700)] p-4">
      <div className="flex justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.12em] text-[var(--paper-faint)]">
            Version {version.version}
            {isCurrent ? " · current" : ""}
          </p>
          <p className="number-tabular mt-1 font-mono text-lg font-semibold text-[var(--paper)]">{version.expected}</p>
        </div>
        {version.status === "APPROVED" ? (
          <ShieldCheck size={16} className="text-[var(--evergreen)]" />
        ) : (
          <Badge status="DRAFT" label={version.status} />
        )}
      </div>
      <p className="mt-3 text-xs text-[var(--paper-dim)]">
        {version.effective_from} → {version.effective_to ?? "open"}
      </p>
      <p className="mt-1 text-[10px] text-[var(--paper-faint)]">{version.source_clause}</p>
      {version.supersedes_control_id ? (
        <p className="mt-2 font-mono text-[9px] text-[var(--paper-faint)]">
          supersedes {version.supersedes_control_id}
        </p>
      ) : null}
    </div>
  );
}
