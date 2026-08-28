"use client";

import { useQuery } from "@tanstack/react-query";
import { FileCheck2, FileText, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Badge, ErrorState, PageHeader } from "@/components/ui/primitives";
import { api } from "@/lib/api";

export default function AgreementDetailPage() {
  const { agreementId } = useParams<{ agreementId: string }>();
  const agreement = useQuery({
    queryKey: ["agreement", agreementId],
    queryFn: () => api.agreement(agreementId),
  });
  const proposals = useQuery({
    queryKey: ["agreement-proposals", agreementId],
    queryFn: () => api.agreementProposals(agreementId),
  });

  if (agreement.isPending) {
    return (
      <div className="grid min-h-[calc(100vh-64px)] place-items-center">
        <LoaderCircle className="animate-spin text-[var(--evergreen)]" />
      </div>
    );
  }

  if (agreement.isError) {
    return (
      <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
        <ErrorState what="The agreement" onRetry={() => agreement.refetch()} />
      </main>
    );
  }

  const record = agreement.data;
  const approvedControls = (proposals.data ?? [])
    .filter((proposal) => proposal.status === "APPROVED")
    .sort((a, b) => a.proposed_control.logical_control_key.localeCompare(
      b.proposed_control.logical_control_key,
    ));

  return (
    <main className="mx-auto max-w-[1160px] px-5 py-8 md:px-8 md:py-10">
      <PageHeader
        back={{ href: "/agreements", label: "All agreements" }}
        eyebrow={
          <>
            <FileCheck2 size={14} /> Agreement provenance
          </>
        }
        title={record.title}
        subtitle={
          <>
            {record.merchant} · Effective {record.effective_from}
            {record.effective_to ? ` → ${record.effective_to}` : " → open"}
          </>
        }
      />

      <section className="panel rounded-2xl p-5">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-[rgba(47,189,127,0.14)] text-[var(--evergreen)]">
              <FileText size={18} />
            </span>
            <div>
              <h2 className="text-sm font-semibold text-[var(--paper)]">Contract record</h2>
              <p className="mt-1 font-mono text-[10px] text-[var(--paper-faint)]">{record.id}</p>
            </div>
          </div>
          <Badge status="PASS" label={record.status} />
        </div>
        <div className="mt-4 grid gap-3 border-t border-[var(--line)] pt-4 text-[10px] text-[var(--paper-faint)] sm:grid-cols-3">
          <div>
            <span className="block uppercase tracking-[0.1em]">Source</span>
            <strong className="mt-1 block text-xs text-[var(--paper)]">{record.source_type}</strong>
          </div>
          <div>
            <span className="block uppercase tracking-[0.1em]">Clauses indexed</span>
            <strong className="number-tabular mt-1 block font-mono text-xs text-[var(--paper)]">
              {record.clauses.length}
            </strong>
          </div>
          <div>
            <span className="block uppercase tracking-[0.1em]">Content fingerprint</span>
            <strong className="mt-1 block truncate font-mono text-xs text-[var(--paper)]">
              {record.content_hash}
            </strong>
          </div>
        </div>
      </section>

      <section className="panel mt-6 overflow-hidden rounded-2xl">
        <div className="border-b border-[var(--line)] px-5 py-4">
          <h2 className="text-sm font-semibold text-[var(--paper)]">Clauses with full provenance</h2>
          <p className="mt-1 text-xs text-[var(--paper-dim)]">
            Exact source text, page reference, and effective window for every clause
          </p>
        </div>
        {record.clauses.length === 0 ? (
          <p className="p-5 text-xs text-[var(--paper-dim)]">No clauses have been indexed for this agreement yet.</p>
        ) : (
          <div className="divide-y divide-[var(--line)]">
            {record.clauses.map((clause) => (
              <div key={clause.id} className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--evergreen)]">
                    Clause {clause.reference} ·{" "}
                    {clause.source_type === "MANUAL_ENTRY" ? "Manual entry" : `Page ${clause.page}`}
                  </p>
                  <span className="font-mono text-[9px] text-[var(--paper-faint)]">
                    {clause.effective_from}
                    {clause.effective_to ? ` → ${clause.effective_to}` : ""}
                  </span>
                </div>
                <h3 className="mt-1.5 text-xs font-semibold text-[var(--paper)]">{clause.heading}</h3>
                <p className="mt-2 text-[11px] leading-5 text-[var(--paper-dim)]">{clause.text}</p>
                <p className="mt-2 font-mono text-[9px] text-[var(--paper-faint)]">{clause.id}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel mt-6 overflow-hidden rounded-2xl">
        <div className="border-b border-[var(--line)] px-5 py-4">
          <h2 className="text-sm font-semibold text-[var(--paper)]">Approved controls sourced from this agreement</h2>
          <p className="mt-1 text-xs text-[var(--paper-dim)]">
            Every control links back to the clause it was derived from
          </p>
        </div>
        {proposals.isPending ? (
          <div className="grid place-items-center py-10">
            <LoaderCircle size={20} className="animate-spin text-[var(--evergreen)]" />
          </div>
        ) : proposals.isError ? (
          <div className="p-5">
            <ErrorState what="Control proposals" onRetry={() => proposals.refetch()} />
          </div>
        ) : approvedControls.length === 0 ? (
          <p className="p-5 text-xs text-[var(--paper-dim)]">
            No approved controls have been derived from this agreement yet. Extract and approve
            proposals on the Agreements page.
          </p>
        ) : (
          <div className="divide-y divide-[var(--line)]">
            {approvedControls.map((proposal) => {
              const control = proposal.proposed_control;
              const clause = record.clauses.find((item) => item.id === proposal.clause_id);
              return (
                <Link
                  key={proposal.id}
                  href={`/controls/${control.logical_control_key}`}
                  className="flex flex-col justify-between gap-3 p-4 transition-colors duration-150 hover:bg-[var(--ink-600)] sm:flex-row sm:items-center"
                >
                  <div>
                    <p className="font-mono text-[9px] font-bold uppercase tracking-[0.13em] text-[var(--paper-faint)]">
                      {control.logical_control_key} · v{control.version}
                    </p>
                    <h3 className="mt-1 text-xs font-semibold text-[var(--paper)]">{control.name}</h3>
                    <p className="mt-1 text-[11px] text-[var(--paper-dim)]">
                      Clause {clause?.reference ?? proposal.clause_id} · {control.source_clause}
                    </p>
                  </div>
                  <span className="sm:ml-auto">
                    <Badge status="PASS" label="APPROVED" />
                  </span>
                </Link>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
