"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Job, JobStatus } from "@/lib/api";

const STATUSES: JobStatus[] = ["queued", "running", "succeeded", "failed", "cancelled", "blocked"];

// Worker publishes `progress` into jobs.summary every heartbeat tick. Shape
// matches lib/progress.ts so we don't reparse logs here.
type Progress = {
  phase: "compile" | "compile-done" | "eval" | "done" | "unknown";
  compile?: {
    rolloutsCur: number | null; rolloutsTotal: number | null; rolloutsPct: number | null;
    remaining: string | null; lastIter: number | null;
    bestValset: number | null; paretoFront: number | null; wins: number; budget: number | null;
  };
  eval?: {
    rowsDone: number; rowsTotal: number; rowsPct: number;
    accPct: number; costUsd: number; eta: string;
  };
};

function pctScore(v: number | null | undefined): string {
  if (v == null) return "–";
  return `${(v <= 1 ? v * 100 : v).toFixed(1)}%`;
}

function MiniBar({ pct, tone = "accent" }: { pct: number | null | undefined; tone?: string }) {
  return (
    <div className="mini-bar">
      <span style={{ width: `${Math.min(100, pct ?? 0)}%`, background: `var(--${tone})` }} />
    </div>
  );
}

function RunningCell({ p }: { p: Progress }) {
  if (p.phase === "eval" && p.eval) {
    const e = p.eval;
    return (
      <div className="run-progress">
        <div className="run-line">
          <span className="run-tag">eval</span>
          <span>{e.rowsDone.toLocaleString()}/{e.rowsTotal.toLocaleString()} ({e.rowsPct}%)</span>
          <span>acc {e.accPct}%</span>
          <span className="muted">${e.costUsd.toFixed(2)} · ETA {e.eta}</span>
        </div>
        <MiniBar pct={e.rowsPct} tone="good" />
      </div>
    );
  }
  if (p.compile) {
    const c = p.compile;
    return (
      <div className="run-progress">
        <div className="run-line">
          <span className="run-tag">GEPA</span>
          {c.rolloutsTotal != null && (
            <span>{c.rolloutsCur}/{c.rolloutsTotal} ({c.rolloutsPct ?? 0}%)</span>
          )}
          {c.bestValset != null && <span>best {pctScore(c.bestValset)}</span>}
          {c.lastIter != null && <span className="muted">iter {c.lastIter}{c.remaining && c.remaining !== "?" ? ` · ETA ${c.remaining}` : ""}</span>}
        </div>
        <MiniBar pct={c.rolloutsPct} />
      </div>
    );
  }
  return <span className="muted">…starting</span>;
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [programFilter, setProgramFilter] = useState<string>("");

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const rows = await api.listJobs({
          status: statusFilter || undefined,
          program: programFilter || undefined,
        });
        if (alive) setJobs(rows);
      } catch (e: unknown) {
        if (alive) setErr(String(e));
      }
    };
    tick();
    const h = setInterval(tick, 5000);
    return () => {
      alive = false;
      clearInterval(h);
    };
  }, [statusFilter, programFilter]);

  return (
    <div>
      <h1>Jobs</h1>
      <div className="row-actions">
        <label style={{ marginRight: 12 }}>
          status:&nbsp;
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">all</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          program:&nbsp;
          <input
            value={programFilter}
            onChange={(e) => setProgramFilter(e.target.value)}
            placeholder="any"
          />
        </label>
      </div>

      {err && <p style={{ color: "var(--bad)" }}>error: {err}</p>}
      {jobs === null && !err && <p>loading…</p>}
      {jobs && (
        <table>
          <thead>
            <tr>
              <th>id</th><th>type</th><th>status</th>
              <th>program/version</th><th>dataset/split</th>
              <th>started</th><th>duration</th><th>summary</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td><Link href={`/jobs/${j.id}`}>{j.id.slice(0, 8)}</Link></td>
                <td>{j.type}</td>
                <td className={`status-${j.status}`}>{j.status}</td>
                <td>{j.program ?? "-"}/{j.version ?? "-"}</td>
                <td>{j.dataset ?? "-"}/{j.split ?? "-"}</td>
                <td>{j.started_at?.slice(11, 19) ?? "-"}</td>
                <td>{durationFmt(j.started_at, j.ended_at)}</td>
                <td>{j.status === "running" && j.summary && (j.summary as { progress?: Progress }).progress
                  ? <RunningCell p={(j.summary as { progress: Progress }).progress} />
                  : summaryFmt(j.summary)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function durationFmt(start: string | null, end: string | null): string {
  if (!start) return "-";
  const s = new Date(start).getTime();
  const e = end ? new Date(end).getTime() : Date.now();
  const sec = Math.max(0, Math.round((e - s) / 1000));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const rs = sec - m * 60;
  return `${m}m${rs}s`;
}

function summaryFmt(s: Record<string, unknown> | null): string {
  if (!s) return "";
  const acc = s["acc_pct"];
  const cost = s["cost_usd"];
  const parts: string[] = [];
  if (typeof acc === "number") parts.push(`acc=${acc.toFixed(1)}%`);
  if (typeof cost === "number") parts.push(`$${cost.toFixed(4)}`);
  return parts.join(" ");
}
