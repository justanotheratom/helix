"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, Artifact, Job } from "@/lib/api";

export default function JobDetail({ params }: { params: { id: string } }) {
  const jobId = params.id;
  const [job, setJob] = useState<Job | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  const logRef = useRef<HTMLPreElement>(null);

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

  // Live log SSE.
  useEffect(() => {
    if (!job || job.status === "queued") return;
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

  if (err) return <p style={{ color: "var(--bad)" }}>error: {err}</p>;
  if (!job) return <p>loading…</p>;

  const cancel = async () => {
    await api.cancelJob(jobId);
  };
  const openTraces = () => {
    window.location.href = job.traces_url;
  };

  return (
    <div>
      <h1>
        <span className="tag">{job.type}</span>
        <span className={`status-${job.status}`}>{job.status}</span>{" "}
        <code>{job.id}</code>
      </h1>

      <div className="row-actions">
        <button className="btn" onClick={openTraces}>open in langfuse</button>
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

      <h2>Metadata</h2>
      <dl className="kv">
        <dt>program/version</dt><dd>{job.program}/{job.version}</dd>
        <dt>dataset/split</dt><dd>{job.dataset}/{job.split}</dd>
        <dt>config_path</dt><dd>{job.config_path ?? "-"}</dd>
        <dt>run_label</dt><dd>{job.run_label}</dd>
        <dt>baked_sha</dt><dd>{job.baked_sha ?? "(imported)"}</dd>
        <dt>worker_id</dt><dd>{job.worker_id ?? "-"}</dd>
        <dt>emitted_run_number</dt><dd>{job.emitted_run_number ?? "-"}</dd>
        <dt>attempt</dt><dd>{job.attempt}</dd>
        <dt>created_at</dt><dd>{job.created_at}</dd>
        <dt>started_at</dt><dd>{job.started_at ?? "-"}</dd>
        <dt>ended_at</dt><dd>{job.ended_at ?? "-"}</dd>
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
