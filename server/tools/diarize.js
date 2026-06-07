// Speaker diarization + cut-plan tools. Both shell out to `python -m
// lattimore.cli` (the local Python module), NOT to ButterCut. Diarization
// uses WhisperX + pyannote and needs HF_TOKEN in the environment.

import path from "node:path";
import { createJob } from "../jobs.js";

const REPO_ROOT = path.resolve(process.cwd());
const PYTHON = process.env.PYTHON || "python3";

function ensureHfToken() {
  if (!process.env.HF_TOKEN && !process.env.HUGGINGFACE_TOKEN) {
    throw new Error(
      "HF_TOKEN not set — pyannote diarization needs a HuggingFace token. " +
      "Get one at https://huggingface.co/settings/tokens, accept the model " +
      "terms at https://hf.co/pyannote/speaker-diarization-3.1 and " +
      "https://hf.co/pyannote/segmentation-3.0, then export HF_TOKEN=hf_..."
    );
  }
}

export function diarizeInterview({
  video_path,
  out_dir,
  whisper_model = "small.en",
  num_speakers,
  min_speakers,
  max_speakers,
}) {
  if (!video_path) throw new Error("video_path required");
  if (!out_dir) throw new Error("out_dir required");
  ensureHfToken();

  const args = [
    "-m", "lattimore.cli", "diarize",
    video_path, out_dir,
    "--whisper-model", whisper_model,
  ];
  if (num_speakers != null) args.push("--num-speakers", String(num_speakers));
  if (min_speakers != null) args.push("--min-speakers", String(min_speakers));
  if (max_speakers != null) args.push("--max-speakers", String(max_speakers));

  return {
    jobId: createJob({
      cmd: PYTHON,
      args,
      cwd: REPO_ROOT,
      label: `diarize ${path.basename(video_path)}`,
    }),
  };
}

export function planSpeakerCuts({
  diarized_path,
  keep,
  merge_gap = 0.3,
  pad_start = 0.0,
  pad_end = 0.0,
  min_cut_duration = 0.1,
  out_path,
}) {
  if (!diarized_path) throw new Error("diarized_path required");
  if (!Array.isArray(keep) || keep.length === 0) {
    throw new Error("keep must be a non-empty array of speaker labels");
  }

  const args = [
    "-m", "lattimore.cli", "speaker-cut",
    diarized_path,
    "--keep", keep.join(","),
    "--merge-gap", String(merge_gap),
    "--pad-start", String(pad_start),
    "--pad-end", String(pad_end),
    "--min-cut-duration", String(min_cut_duration),
  ];
  if (out_path) args.push("--out", out_path);

  return {
    jobId: createJob({
      cmd: PYTHON,
      args,
      cwd: REPO_ROOT,
      label: `speaker-cut keep=${keep.join(",")}`,
    }),
  };
}
