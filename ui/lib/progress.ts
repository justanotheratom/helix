// Parse the live log stream into GEPA-aware progress, mirroring the old
// ai-utils progress_viewer. The job-detail page already receives every log
// line over SSE; this derives a structured view (phase, compile rollouts +
// best/pareto valset, eval rows + acc/cost/ETA) so the UI shows real progress
// instead of a raw tail.

export type Phase = "compile" | "compile-done" | "eval" | "done" | "unknown";

export interface CompileProgress {
  rolloutsCur: number | null;
  rolloutsTotal: number | null;
  rolloutsPct: number | null;
  elapsed: string | null;
  remaining: string | null;
  rate: string | null;
  budget: number | null;
  lastIter: number | null;
  bestValset: number | null;
  paretoFront: number | null;
  wins: number;
}

export interface EvalProgress {
  rowsDone: number;
  rowsTotal: number;
  rowsPct: number;
  accPct: number;
  tokensTotal: number;
  tokensIn: number;
  tokensOut: number;
  costUsd: number;
  latencyAvgMs: number;
  latencyMedMs: number;
  eta: string;
  costPer1kRows: number | null;
}

export interface Progress {
  phase: Phase;
  compile: CompileProgress | null;
  eval: EvalProgress | null;
  errorCount: number;
  lastError: string | null;
}

const RE_TQDM =
  /(\d+)\/(\d+)\s*\[(\d+:\d+(?::\d+)?|\?)<(\d+:\d+(?::\d+)?|\?),\s*([\d.?]+)([a-zA-Z/]+)\]/g;
const RE_ITER_SELECTED = /Iteration (\d+):\s*Selected/g;
const RE_ITER_NEW = /Iteration (\d+):\s*New program candidate index/g;
const RE_BEST_VAL = /Best valset aggregate score so far:\s*([\d.]+)/g;
const RE_PARETO = /Valset pareto front aggregate score:?\s*([\d.]+)/g;
const RE_GEPA_BUDGET = /Running GEPA for approx (\d+) metric calls/;
const RE_COMPILE_DONE = /Compilation complete|=== eval start/;
const RE_EVAL_DONE = /=== done|Eval complete|Saved results/;
const RE_EVAL_STATUS =
  /\[(\d+)\/(\d+)\]\s*Acc:\s*([\d.]+)%\s*\|\s*Tokens:\s*([\d,]+)\s*\(in:([\d,]+)\/out:([\d,]+)\)\s*\|\s*Cost:\s*\$([\d.]+)\s*\|\s*Latency:\s*avg=(\d+)ms,\s*med=(\d+)ms(?:,\s*var=(\d+)ms²)?\s*\|\s*ETA:\s*(\S+)/g;
const RE_ERROR = /ERROR [^\n]+|Traceback[^\n]+|AdapterParseError[^\n]+/g;

const num = (s: string) => parseInt(s.replace(/,/g, ""), 10);

export function parseProgress(lines: string[]): Progress {
  const text = lines.join("\n");

  const evalMatches = [...text.matchAll(RE_EVAL_STATUS)];
  const evalDone = RE_EVAL_DONE.test(text);
  const hasEval = evalMatches.length > 0 || text.includes("=== eval start");
  const compileDone = RE_COMPILE_DONE.test(text) || hasEval;

  let phase: Phase = "compile";
  if (hasEval && !evalDone) phase = "eval";
  else if (evalDone) phase = "done";
  else if (compileDone) phase = "compile-done";
  else if (!text.trim()) phase = "unknown";

  // --- compile (GEPA) ---
  let rolloutsMatch: RegExpMatchArray | null = null;
  let lastTqdm: RegExpMatchArray | null = null;
  for (const m of text.matchAll(RE_TQDM)) {
    lastTqdm = m;
    if (m[6] && m[6].includes("rollout")) rolloutsMatch = m;
  }
  const chosen = rolloutsMatch ?? lastTqdm;

  const budgetM = text.match(RE_GEPA_BUDGET);
  const iters = [...text.matchAll(RE_ITER_SELECTED)].map((m) => parseInt(m[1], 10));
  const bestVals = [...text.matchAll(RE_BEST_VAL)];
  const paretos = [...text.matchAll(RE_PARETO)];
  const wins = [...text.matchAll(RE_ITER_NEW)].length;

  let compile: CompileProgress | null = null;
  if (chosen || iters.length || budgetM) {
    const cur = chosen ? parseInt(chosen[1], 10) : null;
    const total = chosen ? parseInt(chosen[2], 10) : null;
    compile = {
      rolloutsCur: cur,
      rolloutsTotal: total,
      rolloutsPct: cur && total ? Math.round((1000 * cur) / total) / 10 : null,
      elapsed: chosen ? chosen[3] : null,
      remaining: chosen ? chosen[4] : null,
      rate: chosen ? `${chosen[5]}${chosen[6]}` : null,
      budget: budgetM ? parseInt(budgetM[1], 10) : null,
      lastIter: iters.length ? Math.max(...iters) : null,
      bestValset: bestVals.length ? parseFloat(bestVals[bestVals.length - 1][1]) : null,
      paretoFront: paretos.length ? parseFloat(paretos[paretos.length - 1][1]) : null,
      wins,
    };
  }

  // --- eval ---
  let evalP: EvalProgress | null = null;
  if (evalMatches.length) {
    const m = evalMatches[evalMatches.length - 1];
    const rowsDone = num(m[1]);
    const rowsTotal = num(m[2]);
    const costUsd = parseFloat(m[7]);
    evalP = {
      rowsDone,
      rowsTotal,
      rowsPct: rowsTotal ? Math.round((1000 * rowsDone) / rowsTotal) / 10 : 0,
      accPct: parseFloat(m[3]),
      tokensTotal: num(m[4]),
      tokensIn: num(m[5]),
      tokensOut: num(m[6]),
      costUsd,
      latencyAvgMs: num(m[8]),
      latencyMedMs: num(m[9]),
      eta: m[11],
      costPer1kRows: rowsDone > 0 ? Math.round((costUsd * 1000 * 10000) / rowsDone) / 10000 : null,
    };
  }

  const errors = [...text.matchAll(RE_ERROR)].map((m) => m[0]);

  return {
    phase,
    compile,
    eval: evalP,
    errorCount: errors.length,
    lastError: errors.length ? errors[errors.length - 1].slice(0, 240) : null,
  };
}
