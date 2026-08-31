"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarRange, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Badge, ErrorState, PageHeader } from "@/components/ui/primitives";
import {
  EmptySection,
  InlineNotice,
  SectionHeader,
  SummaryStrip,
  WorkspaceLoading,
} from "@/components/ui/workspace";
import { ApiError, api } from "@/lib/api";
import type { Control } from "@/types/api";

export default function ControlDetailPage() {
  const { controlKey } = useParams<{ controlKey: string }>();
  const controls = useQuery({ queryKey: ["controls"], queryFn: api.controls });
  const versions = useQuery({
    queryKey: ["control-versions", controlKey],
    queryFn: () => api.controlVersions(controlKey),
  });

  if (controls.isPending || versions.isPending) {
    return <WorkspaceLoading label="Loading control provenance" />;
  }

  const record = (controls.data ?? []).find((control) => control.logical_control_key === controlKey);
  const history = (versions.data ?? []).slice().sort((a, b) => a.version - b.version);
  const current = record ?? history.at(-1);

  if (!current && controls.isError && versions.isError) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
        <ErrorState
          what="Control provenance"
          onRetry={() => {
            void controls.refetch();
            void versions.refetch();
          }}
        />
      </main>
    );
  }

  if (!current) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
        <PageHeader
          back={{ href: "/controls", label: "Controls" }}
          eyebrow="Control provenance"
          title="Control not found"
          subtitle={
            <>
              No definition is available for <span className="font-mono">{controlKey}</span>.
            </>
          }
        />
        <InlineNotice>
          <button
            className="font-semibold text-[var(--evergreen)] underline underline-offset-2"
            onClick={() => {
              void controls.refetch();
              void versions.refetch();
            }}
            type="button"
          >
            Check again
          </button>
        </InlineNotice>
      </main>
    );
  }

  const parameterEntries = Object.entries(current.parameters);

  return (
    <main className="mx-auto max-w-[1160px] px-5 py-8 md:px-8 md:py-10">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <PageHeader
          back={{ href: "/controls", label: "Controls" }}
          eyebrow={
            <>
              <ShieldCheck size={14} /> Control provenance
            </>
          }
          title={current.name}
          subtitle={
            <span className="font-mono text-[var(--paper-dim)]">
              {current.logical_control_key} · {current.id}
            </span>
          }
        />
        <Badge
          label={current.status.replaceAll("_", " ")}
          status={current.status === "APPROVED" ? "PASS" : "DRAFT"}
        />
      </div>

      <SummaryStrip
        className="mb-6"
        label="Current control definition"
        items={[
          { label: "Expected", value: current.expected },
          { label: "Scope", value: current.scope },
          { label: "Version", value: `v${current.version}`, detail: current.control_type.replaceAll("_", " ") },
          {
            label: "Effective window",
            value: current.effective_from,
            detail: `through ${current.effective_to ?? "open"}`,
          },
        ]}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(20rem,0.95fr)]">
        <section className="panel overflow-hidden rounded-xl">
          <SectionHeader
            title="Executable rule"
            description="Typed parameters and applicability conditions used by the deterministic evaluator."
          />
          {parameterEntries.length ? (
            <dl className="divide-y divide-[var(--line)]">
              {parameterEntries.map(([key, value]) => (
                <div className="grid gap-1 px-5 py-3.5 sm:grid-cols-[12rem_minmax(0,1fr)] sm:gap-4" key={key}>
                  <dt className="font-mono text-[10px] font-semibold text-[var(--paper-faint)]">{key}</dt>
                  <dd className="break-words font-mono text-xs text-[var(--paper)]">
                    {typeof value === "string" ? value : JSON.stringify(value)}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <EmptySection body="This definition does not expose typed parameters." title="No parameters" />
          )}
          <div className="border-t border-[var(--line)] px-5 py-4">
            <h3 className="text-[10px] font-semibold uppercase tracking-[0.11em] text-[var(--paper-faint)]">
              Applicability conditions
            </h3>
            {current.conditions.length ? (
              <ul className="mt-2 space-y-1.5 font-mono text-[10px] text-[var(--paper-dim)]">
                {current.conditions.map((condition) => (
                  <li className="flex gap-2" key={condition}>
                    <span aria-hidden="true" className="text-[var(--evergreen)]">•</span> {condition}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-[var(--paper-dim)]">Applies without an additional condition.</p>
            )}
          </div>
        </section>

        <section className="panel self-start overflow-hidden rounded-xl">
          <SectionHeader
            title="Source and approval"
            description="The agreement evidence and governance record behind this definition."
          />
          <dl className="divide-y divide-[var(--line)]">
            <ProvenanceRow label="Source" value={current.source} />
            <ProvenanceRow label="Source clause" value={current.source_clause} />
            <ProvenanceRow label="Approved at" value={current.approved_at ?? "Not approved"} mono />
            <ProvenanceRow label="Supersedes" value={current.supersedes_control_id ?? "No prior version"} mono />
          </dl>
          <div className="border-t border-[var(--line)] px-5 py-4">
            {current.agreement_id ? (
              <Link
                className="group inline-flex items-center gap-2 text-xs font-semibold text-[var(--evergreen)]"
                href={`/agreements/${current.agreement_id}`}
              >
                Open source agreement
                <ArrowRight aria-hidden="true" className="transition-transform group-hover:translate-x-0.5" size={14} />
              </Link>
            ) : (
              <p className="text-xs text-[var(--paper-dim)]">No agreement is linked to this control.</p>
            )}
          </div>
        </section>
      </div>

      <section className="panel mt-6 overflow-hidden rounded-xl">
        <SectionHeader
          title="Immutable version history"
          description="Effective-dated versions remain available for historical evaluation and replay."
          meta={
            <span className="flex items-center gap-1.5">
              <CalendarRange aria-hidden="true" size={13} /> {history.length.toLocaleString("en-IN")} versions
            </span>
          }
        />
        {versions.isError ? (
          versions.error instanceof ApiError && versions.error.status === 404 ? (
            <EmptySection
              body="This candidate has not produced an approved version history yet."
              title="No approved versions"
            />
          ) : (
            <div className="p-5">
              <ErrorState what="Version history" onRetry={() => versions.refetch()} />
            </div>
          )
        ) : history.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[44rem] text-left text-xs">
              <thead className="bg-[var(--ink-600)] text-[10px] uppercase tracking-[0.1em] text-[var(--paper-faint)]">
                <tr>
                  <th className="px-5 py-3" scope="col">Version</th>
                  <th className="px-4 py-3" scope="col">Expected</th>
                  <th className="px-4 py-3" scope="col">Effective</th>
                  <th className="px-4 py-3" scope="col">Source clause</th>
                  <th className="px-5 py-3 text-right" scope="col">State</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--line)]">
                {history.map((version) => (
                  <ControlVersionRow currentId={current.id} key={version.id} version={version} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptySection body="No version records were returned for this logical control." title="No version history" />
        )}
      </section>
    </main>
  );
}

function ProvenanceRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="grid gap-1 px-5 py-3.5 sm:grid-cols-[7rem_minmax(0,1fr)] sm:gap-3">
      <dt className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--paper-faint)]">{label}</dt>
      <dd className={`break-words text-xs text-[var(--paper)] ${mono ? "font-mono" : ""}`}>{value}</dd>
    </div>
  );
}

function ControlVersionRow({ version, currentId }: { version: Control; currentId: string }) {
  const isCurrent = version.id === currentId;
  return (
    <tr>
      <td className="number-tabular px-5 py-3.5 font-mono font-semibold text-[var(--paper)]">
        v{version.version}{isCurrent ? <span className="ml-2 text-[9px] text-[var(--evergreen)]">CURRENT</span> : null}
      </td>
      <td className="number-tabular px-4 py-3.5 font-mono text-[var(--paper)]">{version.expected}</td>
      <td className="number-tabular px-4 py-3.5 font-mono text-[var(--paper-dim)]">
        {version.effective_from} → {version.effective_to ?? "open"}
      </td>
      <td className="max-w-72 truncate px-4 py-3.5 text-[var(--paper-dim)]">{version.source_clause}</td>
      <td className="px-5 py-3.5 text-right">
        <Badge label={version.status} status={version.status === "APPROVED" ? "PASS" : "DRAFT"} />
      </td>
    </tr>
  );
}
