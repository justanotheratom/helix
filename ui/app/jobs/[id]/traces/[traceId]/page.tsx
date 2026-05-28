"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Observation, TraceDetail } from "@/lib/api";

export default function TraceDetailPage({
  params,
}: {
  params: { id: string; traceId: string };
}) {
  const { id: jobId, traceId } = params;
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getTrace(traceId)
      .then((t) => alive && setTrace(t))
      .catch((e) => alive && setErr(String(e)));
    return () => {
      alive = false;
    };
  }, [traceId]);

  if (err) return <p style={{ color: "var(--bad)" }}>error: {err}</p>;
  if (!trace) return <p>loading trace…</p>;

  return (
    <div>
      <h1>
        <Link href={`/jobs/${jobId}/traces`}>← traces</Link> · {trace.name ?? trace.id.slice(0, 12)}
      </h1>
      <dl className="kv">
        <dt>id</dt><dd><code>{trace.id}</code></dd>
        <dt>started</dt><dd>{trace.timestamp}</dd>
        <dt>latency</dt><dd>{trace.latency != null ? `${trace.latency.toFixed(3)}s` : "-"}</dd>
        <dt>total cost</dt><dd>{trace.totalCost != null ? `$${trace.totalCost.toFixed(6)}` : "-"}</dd>
        <dt>environment</dt><dd>{trace.environment ?? "-"}</dd>
        <dt>observations</dt><dd>{trace.observations?.length ?? 0}</dd>
      </dl>

      <h2>Input</h2>
      <JsonView value={trace.input} />
      <h2>Output</h2>
      <JsonView value={trace.output} />

      <h2>Observations</h2>
      <ObservationTree observations={trace.observations || []} />
    </div>
  );
}

function ObservationTree({ observations }: { observations: Observation[] }) {
  // Build parent → children map; root nodes have parentObservationId == null.
  const byParent = new Map<string | null, Observation[]>();
  for (const o of observations) {
    const k = o.parentObservationId ?? null;
    const list = byParent.get(k);
    if (list) list.push(o);
    else byParent.set(k, [o]);
  }
  for (const list of byParent.values()) {
    list.sort((a, b) => (a.startTime || "").localeCompare(b.startTime || ""));
  }
  const roots = byParent.get(null) || [];
  if (!roots.length && observations.length) {
    // Fallback: flat list if parent links are missing.
    return (
      <div>
        {[...observations]
          .sort((a, b) => (a.startTime || "").localeCompare(b.startTime || ""))
          .map((o) => (
            <ObservationRow key={o.id} obs={o} depth={0} />
          ))}
      </div>
    );
  }
  return (
    <div>
      {roots.map((o) => (
        <ObservationSubtree key={o.id} obs={o} depth={0} byParent={byParent} />
      ))}
    </div>
  );
}

function ObservationSubtree({
  obs,
  depth,
  byParent,
}: {
  obs: Observation;
  depth: number;
  byParent: Map<string | null, Observation[]>;
}) {
  const children = byParent.get(obs.id) || [];
  return (
    <>
      <ObservationRow obs={obs} depth={depth} />
      {children.map((c) => (
        <ObservationSubtree key={c.id} obs={c} depth={depth + 1} byParent={byParent} />
      ))}
    </>
  );
}

function ObservationRow({ obs, depth }: { obs: Observation; depth: number }) {
  const [open, setOpen] = useState(false);
  const isErr = (obs.level || "").toUpperCase() === "ERROR";
  return (
    <div className={`obs-row ${isErr ? "obs-err" : ""}`} style={{ paddingLeft: depth * 16 }}>
      <div className="obs-line">
        <button className="obs-toggle" onClick={() => setOpen((o) => !o)} aria-label="expand">
          {open ? "▾" : "▸"}
        </button>
        <span className={`obs-tag obs-${obs.type.toLowerCase()}`}>{obs.type}</span>
        <span className="obs-name">{obs.name ?? "-"}</span>
        {obs.model && <span className="muted">{obs.model}</span>}
        {obs.latency != null && <span className="muted">{(obs.latency * 1000).toFixed(0)}ms</span>}
        {obs.usage?.total != null && <span className="muted">{obs.usage.total} tok</span>}
        {obs.totalCost != null && obs.totalCost > 0 && (
          <span className="muted">${obs.totalCost.toFixed(6)}</span>
        )}
        {isErr && <span className="bad">{obs.statusMessage || "error"}</span>}
      </div>
      {open && (
        <div className="obs-detail">
          <div className="obs-detail-half">
            <div className="phase-title">input</div>
            <JsonView value={obs.input} />
          </div>
          <div className="obs-detail-half">
            <div className="phase-title">output</div>
            <JsonView value={obs.output} />
          </div>
        </div>
      )}
    </div>
  );
}

function JsonView({ value }: { value: unknown }) {
  if (value == null) return <pre className="json-view muted">null</pre>;
  let text: string;
  if (typeof value === "string") {
    text = value;
  } else {
    try {
      text = JSON.stringify(value, null, 2);
    } catch {
      text = String(value);
    }
  }
  return <pre className="json-view">{text}</pre>;
}
