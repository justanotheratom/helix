"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, TraceListResponse } from "@/lib/api";
import { formatLocalTime } from "@/lib/time";

const LIMIT = 50;

export default function JobTracesPage({ params }: { params: { id: string } }) {
  const jobId = params.id;
  const [page, setPage] = useState(1);
  const [resp, setResp] = useState<TraceListResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .listJobTraces(jobId, LIMIT, page)
      .then((r) => alive && setResp(r))
      .catch((e) => alive && setErr(String(e)));
    return () => {
      alive = false;
    };
  }, [jobId, page]);

  if (err) return <p style={{ color: "var(--bad)" }}>error: {err}</p>;
  if (!resp) return <p>loading traces…</p>;

  const { data, meta } = resp;
  return (
    <div>
      <h1>
        <Link href={`/jobs/${jobId}`}>← job {jobId.slice(0, 8)}</Link> · Traces
      </h1>
      <p className="muted" style={{ marginTop: -8 }}>
        {meta.totalItems.toLocaleString()} traces · page {meta.page} of {meta.totalPages}
      </p>

      <table>
        <thead>
          <tr>
            <th>id</th>
            <th>name</th>
            <th>started</th>
            <th>latency</th>
            <th>cost</th>
            <th>preview</th>
          </tr>
        </thead>
        <tbody>
          {data.map((t) => (
            <tr key={t.id}>
              <td>
                <Link href={`/jobs/${jobId}/traces/${t.id}`}>{t.id.slice(0, 12)}</Link>
              </td>
              <td>{t.name ?? "-"}</td>
              <td>{formatLocalTime(t.timestamp)}</td>
              <td>{t.latency != null ? `${t.latency.toFixed(2)}s` : "-"}</td>
              <td>{t.totalCost != null ? `$${t.totalCost.toFixed(4)}` : "-"}</td>
              <td className="muted preview">{previewJSON(t.input)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="row-actions" style={{ marginTop: 12 }}>
        <button className="btn" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
          ← prev
        </button>
        <button
          className="btn"
          disabled={page >= meta.totalPages}
          onClick={() => setPage((p) => p + 1)}
        >
          next →
        </button>
      </div>
    </div>
  );
}

function previewJSON(v: unknown): string {
  if (v == null) return "";
  let s: string;
  try {
    s = typeof v === "string" ? v : JSON.stringify(v);
  } catch {
    s = String(v);
  }
  return s.length > 140 ? s.slice(0, 140) + "…" : s;
}
