"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileCheck2, FileText, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/app-shell";
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
      <AppShell>
        <div className="grid min-h-[calc(100vh-64px)] place-items-center">
          <LoaderCircle className="animate-spin text-[#1e6b51]" />
        </div>
      </AppShell>
    );
  }

  if (agreement.isError) {
    return (
      <AppShell>
        <main className="mx-auto max-w-3xl px-5 py-10 md:px-8">
          <div className="panel rounded-2xl p-8 text-sm text-[#a43d32]" role="alert">
            The agreement could not be loaded.{" "}
            <button
              type="button"
              onClick={() => agreement.refetch()}
              className="font-semibold underline"
            >
              Retry
            </button>
          </div>
        </main>
      </AppShell>
    );
  }

  const record = agreement.data;
  const approvedControls = (proposals.data ?? [])
    .filter((proposal) => proposal.status === "APPROVED")
    .sort((a, b) => a.proposed_control.logical_control_key.localeCompare(
      b.proposed_control.logical_control_key,
    ));

  return (
    <AppShell>
      <main className="mx-auto max-w-[1160px] px-5 py-8 md:px-8 md:py-10">
        <Link
          href="/agreements"
          className="mb-6 inline-flex items-center gap-1.5 text-xs font-semibold text-[#1e6b51] hover:underline"
        >
          <ArrowLeft size={13} /> All agreements
        </Link>

        <p className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]">
          <FileCheck2 size={14} /> Agreement provenance
        </p>
        <h1 className="text-3xl font-semibold tracking-[-0.035em]">{record.title}</h1>
        <p className="mt-2 text-sm text-[#66716b]">
          {record.merchant} · Effective {record.effective_from}
          {record.effective_to ? ` → ${record.effective_to}` : " → open"}
        </p>

        <section className="panel mt-7 rounded-2xl p-5">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
            <div className="flex items-start gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#e5f2eb] text-[#1e6b51]">
                <FileText size={18} />
              </span>
              <div>
                <h2 className="text-sm font-semibold">Contract record</h2>
                <p className="mt-1 font-mono text-[10px] text-[#758079]">{record.id}</p>
              </div>
            </div>
            <span className="w-fit rounded-full bg-[#dff2e8] px-2.5 py-1 text-[10px] font-bold text-[#1e6b51]">
              {record.status}
            </span>
          </div>
          <div className="mt-4 grid gap-3 border-t border-[#e4e8e2] pt-4 text-[10px] text-[#6d7872] sm:grid-cols-3">
            <div>
              <span className="block uppercase tracking-[0.1em]">Source</span>
              <strong className="mt-1 block text-xs text-[#202b26]">{record.source_type}</strong>
            </div>
            <div>
              <span className="block uppercase tracking-[0.1em]">Clauses indexed</span>
              <strong className="mt-1 block text-xs text-[#202b26]">{record.clauses.length}</strong>
            </div>
            <div>
              <span className="block uppercase tracking-[0.1em]">Content fingerprint</span>
              <strong className="mt-1 block truncate font-mono text-xs text-[#202b26]">
                {record.content_hash}
              </strong>
            </div>
          </div>
        </section>

        <section className="panel mt-6 overflow-hidden rounded-2xl">
          <div className="border-b border-[#e2e5df] px-5 py-4">
            <h2 className="text-sm font-semibold">Clauses with full provenance</h2>
            <p className="mt-1 text-xs text-[#78827d]">
              Exact source text, page reference, and effective window for every clause
            </p>
          </div>
          {record.clauses.length === 0 ? (
            <p className="p-5 text-xs text-[#66716b]">No clauses have been indexed for this agreement yet.</p>
          ) : (
            <div className="divide-y divide-[#e8ebe6]">
              {record.clauses.map((clause) => (
                <div key={clause.id} className="p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#1e6b51]">
                      Clause {clause.reference} ·{" "}
                      {clause.source_type === "MANUAL_ENTRY" ? "Manual entry" : `Page ${clause.page}`}
                    </p>
                    <span className="text-[9px] text-[#7a847e]">
                      {clause.effective_from}
                      {clause.effective_to ? ` → ${clause.effective_to}` : ""}
                    </span>
                  </div>
                  <h3 className="mt-1.5 text-xs font-semibold">{clause.heading}</h3>
                  <p className="mt-2 text-[11px] leading-5 text-[#66716b]">{clause.text}</p>
                  <p className="mt-2 font-mono text-[9px] text-[#8a938e]">{clause.id}</p>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="panel mt-6 overflow-hidden rounded-2xl">
          <div className="border-b border-[#e2e5df] px-5 py-4">
            <h2 className="text-sm font-semibold">Approved controls sourced from this agreement</h2>
            <p className="mt-1 text-xs text-[#78827d]">
              Every control links back to the clause it was derived from
            </p>
          </div>
          {proposals.isPending ? (
            <div className="grid place-items-center py-10">
              <LoaderCircle size={20} className="animate-spin text-[#1e6b51]" />
            </div>
          ) : proposals.isError ? (
            <div className="p-5 text-xs text-[#a43d32]" role="alert">
              Control proposals could not be loaded.{" "}
              <button
                type="button"
                onClick={() => proposals.refetch()}
                className="font-semibold underline"
              >
                Retry
              </button>
            </div>
          ) : approvedControls.length === 0 ? (
            <p className="p-5 text-xs text-[#66716b]">
              No approved controls have been derived from this agreement yet. Extract and approve
              proposals on the Agreements page.
            </p>
          ) : (
            <div className="divide-y divide-[#e8ebe6]">
              {approvedControls.map((proposal) => {
                const control = proposal.proposed_control;
                const clause = record.clauses.find((item) => item.id === proposal.clause_id);
                return (
                  <Link
                    key={proposal.id}
                    href={`/controls/${control.logical_control_key}`}
                    className="flex flex-col justify-between gap-3 p-4 transition hover:bg-[#f7faf8] sm:flex-row sm:items-center"
                  >
                    <div>
                      <p className="text-[9px] font-bold uppercase tracking-[0.13em] text-[#68746d]">
                        {control.logical_control_key} · v{control.version}
                      </p>
                      <h3 className="mt-1 text-xs font-semibold">{control.name}</h3>
                      <p className="mt-1 text-[11px] text-[#66716b]">
                        Clause {clause?.reference ?? proposal.clause_id} · {control.source_clause}
                      </p>
                    </div>
                    <span className="w-fit rounded-full bg-[#dff2e8] px-2.5 py-1 text-[9px] font-bold text-[#1e6b51] sm:ml-auto">
                      APPROVED
                    </span>
                  </Link>
                );
              })}
            </div>
          )}
        </section>
      </main>
    </AppShell>
  );
}
