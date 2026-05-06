// Editorial composition tools: paper-edit kickoff, B-roll match kickoff,
// timeline composition, and timeline export. The "starter" tools just
// return the prompt + structured input the editorial skill needs; the
// actual creative work is done by the model running the skill.
//
// compose_timeline / export_timeline shell out to a small Python CLI
// (`python -m lattimore.cli`) which calls into lib/lattimore/.

import path from "node:path";
import { writeFile, mkdir, readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { createJob, getJob } from "../jobs.js";

const PROMPTS = path.resolve(process.cwd(), "prompts");

async function readPrompt(name) {
  return readFile(path.join(PROMPTS, name), "utf8");
}

export async function paperEditStarter({ transcripts, target_runtime, brief }) {
  if (!Array.isArray(transcripts) || !transcripts.length) {
    throw new Error("transcripts (array) required");
  }
  if (!target_runtime) throw new Error("target_runtime (seconds) required");
  const taste = await readPrompt("lattimore_taste.md");
  const cutdown = await readPrompt("interview_cutdown.md");
  return {
    instructions: [
      "Read the two prompts below in order, then produce the paper edit.",
      "Output schema: see interview_cutdown.md (JSON array of selects).",
    ].join(" "),
    prompts: { lattimore_taste: taste, interview_cutdown: cutdown },
    inputs: { transcripts, target_runtime, brief: brief || "" },
    skill: "interview-paper-edit",
  };
}

export async function brollMatchStarter({ paper_edit, footage_map, music_bed }) {
  if (!Array.isArray(paper_edit)) throw new Error("paper_edit (array) required");
  if (!footage_map || typeof footage_map !== "object") {
    throw new Error("footage_map (object) required");
  }
  const taste = await readPrompt("lattimore_taste.md");
  const matching = await readPrompt("broll_matching.md");
  return {
    instructions: "Read the two prompts, then place lay-overs per the schema in broll_matching.md.",
    prompts: { lattimore_taste: taste, broll_matching: matching },
    inputs: { paper_edit, footage_map, music_bed: music_bed || null },
    skill: "broll-overlay",
  };
}

export async function composeTimeline({ schema, name = "lattimore_roughcut", out_dir }) {
  if (!schema) throw new Error("schema required");
  out_dir = out_dir || path.resolve(process.cwd(), "libraries", "_compose");
  if (!existsSync(out_dir)) await mkdir(out_dir, { recursive: true });
  const inputPath = path.join(out_dir, `${name}.input.json`);
  const otioPath = path.join(out_dir, `${name}.otio`);
  await writeFile(inputPath, JSON.stringify(schema, null, 2), "utf8");
  const jobId = createJob({
    cmd: "python",
    args: ["-m", "lattimore.cli", "build", inputPath, otioPath, "--name", name],
    label: `compose ${name}`,
  });
  return { jobId, inputPath, otioPath };
}

export async function exportTimeline({ otio_path, out_path, fmt }) {
  if (!otio_path) throw new Error("otio_path required");
  if (!out_path) throw new Error("out_path required");
  const args = ["-m", "lattimore.cli", "export", otio_path, out_path];
  if (fmt) args.push("--fmt", fmt);
  const jobId = createJob({ cmd: "python", args, label: `export ${path.basename(out_path)}` });
  return { jobId, out_path };
}

// Helpful sync re-export so server can wait briefly when desired.
export { getJob };
