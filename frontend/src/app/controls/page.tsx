"use client";

import { useQuery } from "@tanstack/react-query";
import { LoaderCircle, ShieldCheck } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { api } from "@/lib/api";

export default function ControlsPage() {
  const controls = useQuery({ queryKey: ["controls"], queryFn: api.controls });

  return (
    <AppShell>
      <main className="mx-auto max-w-[1160px] px-5 py-8 md:px-8 md:py-10">
        <p className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#1e6b51]">
          <ShieldCheck size={14} /> Approved control registry
        </p>
        <h1 className="text-3xl font-semibold tracking-[-0.035em]">Controls</h1>
        <p className="mt-2 text-sm text-[#66716b]">
          Effective-dated rules used by the deterministic engine. Rates and money tolerances remain Decimal strings.
        </p>

        {controls.isPending ? (
          <LoaderCircle className="mx-auto mt-20 animate-spin text-[#1e6b51]" />
        ) : controls.isError ? (
          <div className="panel mt-7 rounded-2xl p-8 text-sm text-[#a43d32]" role="alert">
            Controls could not be loaded.
          </div>
        ) : (
          <section className="mt-7 space-y-3">
            {controls.data?.map((control) => (
              <article key={control.id} className="panel rounded-2xl p-5">
                <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                  <div>
                    <p className="font-mono text-[10px] text-[#758079]">{control.id} · v{control.version}</p>
                    <h2 className="mt-1 text-base font-semibold">{control.name}</h2>
                    <p className="mt-2 text-xs text-[#66716b]">{control.scope} · {control.expected}</p>
                    <p className="mt-2 text-[11px] text-[#78827d]">{control.source} · {control.source_clause}</p>
                  </div>
                  <span className={`w-fit rounded-full px-2.5 py-1 text-[9px] font-bold ${control.status === "APPROVED" ? "bg-[#dff2e8] text-[#1e6b51]" : "bg-[#eceeed] text-[#66716b]"}`}>
                    {control.status}
                  </span>
                </div>
                <pre className="mt-4 overflow-x-auto rounded-xl bg-[#f3f5f1] p-3 text-[10px] leading-5 text-[#52615a]">
                  {JSON.stringify(control.parameters, null, 2)}
                </pre>
              </article>
            ))}
          </section>
        )}
      </main>
    </AppShell>
  );
}
