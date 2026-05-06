// Ingest tools: thin wrappers over ButterCut's transcribe / analyze / summarize
// skills. Long-running — return a job id; client polls job_status / job_result.

import path from "node:path";
import { existsSync } from "node:fs";
import { createJob } from "../jobs.js";

const BUTTERCUT = path.resolve(process.cwd(), "vendor", "buttercut");

function ensureButtercut() {
  if (!existsSync(BUTTERCUT)) {
    throw new Error(
      "vendor/buttercut not initialized — run `git submodule update --init --recursive`"
    );
  }
}

// We invoke ButterCut via `claude` CLI (assumed on PATH) so its skills run.
// The user can override with BUTTERCUT_CMD env var.
function buttercutCommand(skill, args) {
  const cmd = process.env.BUTTERCUT_CMD || "claude";
  const skillFlag = ["--skill", skill];
  return { cmd, args: [...skillFlag, ...args], cwd: BUTTERCUT };
}

export function transcribeVideo({ video_path, language = "en" }) {
  ensureButtercut();
  if (!video_path) throw new Error("video_path required");
  const { cmd, args, cwd } = buttercutCommand("transcribe-audio", [
    "--input", video_path, "--language", language,
  ]);
  return { jobId: createJob({ cmd, args, cwd, label: `transcribe ${path.basename(video_path)}` }) };
}

export function analyzeVideo({ video_path }) {
  ensureButtercut();
  if (!video_path) throw new Error("video_path required");
  const { cmd, args, cwd } = buttercutCommand("analyze-video", [
    "--input", video_path,
  ]);
  return { jobId: createJob({ cmd, args, cwd, label: `analyze ${path.basename(video_path)}` }) };
}

export function summarizeVideo({ video_path }) {
  ensureButtercut();
  if (!video_path) throw new Error("video_path required");
  const { cmd, args, cwd } = buttercutCommand("summarize-video", [
    "--input", video_path,
  ]);
  return { jobId: createJob({ cmd, args, cwd, label: `summarize ${path.basename(video_path)}` }) };
}
