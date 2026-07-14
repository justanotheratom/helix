"use client";

import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { api, Artifact, Job } from "@/lib/api";
import { BestPromptEvent, CompileProgress, parseProgress, Progress } from "@/lib/progress";
import { formatLocalTimestamp } from "@/lib/time";

function Bar({ pct, tone = "accent" }: { pct: number | null; tone?: string }) {
  return (
    <div className="bar">
      <span style={{ width: `${Math.min(100, pct ?? 0)}%`, background: `var(--${tone})` }} />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}

function ProgressView({ p, status }: { p: Progress; status: string }) {
  const active = status === "running";
  const c = p.compile;
  const e = p.eval;
  if (!c && !e && p.errorCount === 0) return null;
  return (
    <section className="progress">
      <h2>
        Progress <span className="tag">{p.phase}</span>
        {active && <span className="pulse" title="live" />}
      </h2>

      {c && (
        <div className="phase-block">
          <div className="phase-title">GEPA compile</div>
          {c.rolloutsTotal != null && (
            <>
              <div className="bar-row">
                <span>
                  rollouts {c.rolloutsCur}/{c.rolloutsTotal}
                  {c.rolloutsPct != null && ` (${c.rolloutsPct}%)`}
                </span>
                <span className="muted">
                  {c.remaining && c.remaining !== "?" ? `ETA ${c.remaining}` : ""} {c.rate ? `· ${c.rate}` : ""}
                </span>
              </div>
              <Bar pct={c.rolloutsPct} />
            </>
          )}
          <div className="tiles">
            <Stat label="best valset" value={c.bestValset != null ? `${(c.bestValset * (c.bestValset <= 1 ? 100 : 1)).toFixed(1)}%` : "–"} />
            <Stat label="pareto front" value={c.paretoFront != null ? `${(c.paretoFront * (c.paretoFront <= 1 ? 100 : 1)).toFixed(1)}%` : "–"} />
            <Stat label="iteration" value={c.lastIter ?? "–"} />
            <Stat label="new candidates" value={c.wins} />
            {c.budget != null && <Stat label="budget (calls)" value={c.budget.toLocaleString()} />}
          </div>
          {c.bestPrompt && <BestPromptDiff event={c.bestPrompt} />}
        </div>
      )}

      {e && (
        <div className="phase-block">
          <div className="phase-title">Held-out eval</div>
          <div className="bar-row">
            <span>
              rows {e.rowsDone.toLocaleString()}/{e.rowsTotal.toLocaleString()} ({e.rowsPct}%)
            </span>
            <span className="muted">{e.eta !== "0s" ? `ETA ${e.eta}` : "done"}</span>
          </div>
          <Bar pct={e.rowsPct} tone="good" />
          <div className="tiles">
            <Stat label="accuracy" value={`${e.accPct}%`} />
            <Stat label="cost" value={`$${e.costUsd.toFixed(2)}`} />
            {e.costPer1kRows != null && <Stat label="$/1k rows" value={`$${e.costPer1kRows.toFixed(3)}`} />}
            <Stat label="tokens" value={e.tokensTotal.toLocaleString()} />
            <Stat label="latency med" value={`${e.latencyMedMs}ms`} />
          </div>
        </div>
      )}

      {p.errorCount > 0 && (
        <div className="err-banner">
          {p.errorCount} error{p.errorCount > 1 ? "s" : ""} seen — last: <code>{p.lastError}</code>
        </div>
      )}
    </section>
  );
}

type DiffLine = { kind: "same" | "add" | "remove"; text: string };

function lineDiff(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  const dp = Array.from({ length: a.length + 1 }, () => new Uint32Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      out.push({ kind: "same", text: a[i] }); i += 1; j += 1;
    } else if (j < b.length && (i === a.length || dp[i][j + 1] >= dp[i + 1][j])) {
      out.push({ kind: "add", text: b[j] }); j += 1;
    } else {
      out.push({ kind: "remove", text: a[i] }); i += 1;
    }
  }
  return out;
}

function BestPromptDiff({ event }: { event: BestPromptEvent }) {
  const components = Object.keys(event.current.prompts).sort();
  const [selected, setSelected] = useState(components[0] ?? "");
  const component = components.includes(selected) ? selected : components[0] ?? "";
  const previousPrompt = event.previous?.prompts[component] ?? "";
  const currentPrompt = event.current.prompts[component] ?? "";
  const diff = useMemo(
    () => (event.previous ? lineDiff(previousPrompt, currentPrompt) : []),
    [event.previous, previousPrompt, currentPrompt],
  );
  const score = (value: number) => `${(value <= 1 ? value * 100 : value).toFixed(2)}%`;

  return (
    <div className="prompt-diff">
      <div className="prompt-diff-head">
        <div>
          <strong>Best valset system-prompt diff</strong>
          <span className="muted">
            {event.previous
              ? `candidate ${event.previous.candidateIdx} → ${event.current.candidateIdx} · ${score(event.previous.score)} → ${score(event.current.score)}`
              : `seed candidate ${event.current.candidateIdx} · ${score(event.current.score)}`}
            {` · iteration ${event.current.iteration}`}
            {event.scoreDelta != null && ` (${event.scoreDelta >= 0 ? "+" : ""}${score(event.scoreDelta)})`}
          </span>
        </div>
        {components.length > 1 && (
          <select value={component} onChange={(e) => setSelected(e.target.value)}>
            {components.map((name) => <option key={name}>{name}</option>)}
          </select>
        )}
      </div>
      <div className="phase-title">{component || "predictor"}</div>
      {!event.previous ? (
        <p className="muted">Seed prompt recorded. The first improvement will show its diff here.</p>
      ) : (
        <pre className="prompt-diff-body" aria-label="Best prompt unified diff">
          {diff.map((line, index) => (
            <span key={`${index}-${line.kind}`} className={`diff-${line.kind}`}>
              {line.kind === "add" ? "+ " : line.kind === "remove" ? "- " : "  "}{line.text}{"\n"}
            </span>
          ))}
        </pre>
      )}
    </div>
  );
}

function summaryProgress(job: Job | null): Progress | null {
  const value = job?.summary?.progress;
  return value && typeof value === "object" ? (value as Progress) : null;
}

function mergeProgress(stored: Progress | null, live: Progress): Progress {
  if (!stored) return live;
  if (!live.compile && !live.eval) return stored;
  const compile = live.compile
    ? ({ ...stored.compile, ...live.compile, bestPrompt: live.compile.bestPrompt ?? stored.compile?.bestPrompt ?? null } as CompileProgress)
    : stored.compile;
  return { ...stored, ...live, compile, eval: live.eval ?? stored.eval };
}

export default function JobDetail({ params }: { params: { id: string } }) {
  const jobId = params.id;
  const [job, setJob] = useState<Job | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  const logRef = useRef<HTMLPreElement>(null);
  const seededRef = useRef(false);

  // Poll job + artifacts.
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const j = await api.getJob(jobId);
        if (alive) setJob(j);
        const a = await api.listArtifacts(jobId);
        if (alive) setArtifacts(a);
      } catch (e) {
        if (alive) setErr(String(e));
      }
    };
    tick();
    const h = setInterval(tick, 3000);
    return () => {
      alive = false;
      clearInterval(h);
    };
  }, [jobId]);

  // For terminal jobs the SSE stream has no replay, so seed the parsed
  // progress + log view once from the uploaded helix/stdout.log artifact.
  useEffect(() => {
    const terminal = job && ["succeeded", "failed", "cancelled"].includes(job.status);
    if (!terminal || seededRef.current || !artifacts || logLines.length > 0) return;
    const log = artifacts.find((a) => a.relative_path === "helix/stdout.log");
    if (!log) return;
    seededRef.current = true;
    fetch(api.artifactUrl(jobId, log.id))
      .then((r) => (r.ok ? r.text() : ""))
      .then((t) => {
        if (t) setLogLines(t.split("\n"));
      })
      .catch(() => {});
  }, [job?.status, artifacts, jobId, logLines.length]);

  // Live log SSE — only while running (terminal jobs are seeded above).
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const es = new EventSource(`/api/jobs/${jobId}/logs?follow=true`);
    es.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        const line: string = payload.line ?? ev.data;
        setLogLines((prev) => {
          const next = [...prev, line];
          return next.length > 5000 ? next.slice(-5000) : next;
        });
      } catch {
        setLogLines((prev) => [...prev, ev.data]);
      }
    };
    es.onerror = () => {
      // Auto-reconnect handled by EventSource; ignore.
    };
    return () => es.close();
  }, [jobId, job?.status]);

  // Auto-scroll log tail.
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logLines]);

  const progress = useMemo(
    () => mergeProgress(summaryProgress(job), parseProgress(logLines)),
    [job, logLines],
  );

  if (err) return <p style={{ color: "var(--bad)" }}>error: {err}</p>;
  if (!job) return <p>loading…</p>;

  const cancel = async () => {
    await api.cancelJob(jobId);
  };

  return (
    <div>
      <h1>
        <span className="tag">{job.type}</span>
        <span className={`status-${job.status}`}>{job.status}</span>{" "}
        <code>{job.id}</code>
      </h1>

      <div className="row-actions">
        <Link className="btn" href={`/jobs/${jobId}/traces`}>view traces →</Link>
        <a className="btn" href={api.artifactsTarUrl(jobId)}>download artifacts.tar.gz</a>
        {(job.status === "queued" || job.status === "running") && (
          <button className="btn danger" onClick={cancel}>cancel</button>
        )}
        {job.parent_job_id && (
          <Link className="btn" href={`/jobs/${job.parent_job_id}`}>
            parent compile →
          </Link>
        )}
      </div>

      <ProgressView p={progress} status={job.status} />

      <h2>Metadata</h2>
      <dl className="kv">
        <dt>program/version</dt><dd>{job.program}/{job.version}</dd>
        <dt>dataset/split</dt><dd>{job.dataset}/{job.split}</dd>
        <dt>config_path</dt><dd>{job.config_path ?? "-"}</dd>
        <dt>user_id</dt><dd>{job.user_id ?? "-"}</dd>
        <dt>run_label</dt><dd>{job.run_label}</dd>
        <dt>snapshot_id</dt><dd>{job.snapshot_id ?? "(imported)"}</dd>
        {job.blocked_reason && (<><dt>blocked_reason</dt><dd>{job.blocked_reason}</dd></>)}
        <dt>worker_id</dt><dd>{job.worker_id ?? "-"}</dd>
        <dt>emitted_run_number</dt><dd>{job.emitted_run_number ?? "-"}</dd>
        <dt>attempt</dt><dd>{job.attempt}</dd>
        <dt>created_at</dt><dd>{formatLocalTimestamp(job.created_at)}</dd>
        <dt>started_at</dt><dd>{formatLocalTimestamp(job.started_at)}</dd>
        <dt>ended_at</dt><dd>{formatLocalTimestamp(job.ended_at)}</dd>
        <dt>exit_code</dt><dd>{job.exit_code ?? "-"}</dd>
      </dl>

      <h2>Summary</h2>
      <pre style={{ fontSize: 12 }}>{JSON.stringify(job.summary ?? {}, null, 2)}</pre>

      <h2>Logs</h2>
      <pre className="logs" ref={logRef}>
        {logLines.length === 0 ? "(no log lines yet)" : logLines.join("\n")}
      </pre>

      <h2>Artifacts ({artifacts?.length ?? 0})</h2>
      {artifacts && (
        <table>
          <thead>
            <tr><th>relative_path</th><th>kind</th><th>size</th><th>sha256</th><th></th></tr>
          </thead>
          <tbody>
            {artifacts.map((a) => (
              <tr key={a.id}>
                <td><code>{a.relative_path}</code></td>
                <td>{a.kind}</td>
                <td>{a.size_bytes.toLocaleString()}</td>
                <td title={a.sha256}>{a.sha256.slice(0, 12)}…</td>
                <td><a href={api.artifactUrl(jobId, a.id)} target="_blank" rel="noreferrer">download</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
