// In-memory job queue: spawn child processes, capture stdout/stderr,
// return a job id that the MCP client polls via job_status / job_result.

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";

const jobs = new Map();

export function createJob({ cmd, args = [], cwd, env, label }) {
  const id = randomUUID();
  const job = {
    id,
    label: label || cmd,
    cmd,
    args,
    cwd,
    status: "running",
    code: null,
    startedAt: Date.now(),
    finishedAt: null,
    stdout: "",
    stderr: "",
  };
  jobs.set(id, job);

  const child = spawn(cmd, args, {
    cwd,
    env: { ...process.env, ...(env || {}) },
    stdio: ["ignore", "pipe", "pipe"],
  });
  job.pid = child.pid;
  child.stdout.on("data", (b) => { job.stdout += b.toString(); });
  child.stderr.on("data", (b) => { job.stderr += b.toString(); });
  child.on("error", (err) => {
    job.status = "error";
    job.stderr += `\n[spawn error] ${err.message}`;
    job.finishedAt = Date.now();
  });
  child.on("close", (code) => {
    job.code = code;
    job.status = code === 0 ? "ok" : "failed";
    job.finishedAt = Date.now();
  });

  return id;
}

export function getJob(id) {
  return jobs.get(id) || null;
}

export function statusOf(id) {
  const j = jobs.get(id);
  if (!j) return null;
  return {
    id: j.id,
    label: j.label,
    status: j.status,
    code: j.code,
    startedAt: j.startedAt,
    finishedAt: j.finishedAt,
    stdoutBytes: j.stdout.length,
    stderrBytes: j.stderr.length,
  };
}

export function resultOf(id) {
  const j = jobs.get(id);
  if (!j) return null;
  return {
    ...statusOf(id),
    stdout: j.stdout,
    stderr: j.stderr,
  };
}

export function listJobs() {
  return [...jobs.values()].map((j) => statusOf(j.id));
}
