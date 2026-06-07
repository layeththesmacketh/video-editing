#!/usr/bin/env node
// Lattimore MCP server (stdio).
//
// Aggregates ButterCut ingest + our editorial composition + research helpers.
// All tools are registered via @modelcontextprotocol/sdk.

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

import * as lib from "./tools/library.js";
import * as ingest from "./tools/ingest.js";
import * as edit from "./tools/edit.js";
import * as research from "./tools/research.js";
import * as diarize from "./tools/diarize.js";
import { statusOf, resultOf, listJobs } from "./jobs.js";

const tools = [
  // ── library ──
  {
    name: "create_library",
    description: "Create a new library at ./libraries/<name>. Sets client (e.g. 'im8') and target_runtime.",
    schema: z.object({ name: z.string(), client: z.string().optional(), target_runtime: z.number().optional() }),
    handler: (a) => lib.createLibrary(a),
  },
  {
    name: "list_libraries",
    description: "List all libraries with their config.",
    schema: z.object({}),
    handler: () => lib.listLibraries(),
  },
  {
    name: "library_status",
    description: "Status of a library: counts of raw / transcripts / analysis / exports.",
    schema: z.object({ name: z.string() }),
    handler: (a) => lib.libraryStatus(a),
  },
  // ── ingest (ButterCut) ──
  {
    name: "transcribe_video",
    description: "ButterCut transcribe-audio (WhisperX). Returns a jobId; poll job_status / job_result.",
    schema: z.object({ video_path: z.string(), language: z.string().optional() }),
    handler: (a) => ingest.transcribeVideo(a),
  },
  {
    name: "analyze_video",
    description: "ButterCut analyze-video. Returns a jobId.",
    schema: z.object({ video_path: z.string() }),
    handler: (a) => ingest.analyzeVideo(a),
  },
  {
    name: "summarize_video",
    description: "ButterCut summarize-video. Returns a jobId.",
    schema: z.object({ video_path: z.string() }),
    handler: (a) => ingest.summarizeVideo(a),
  },
  // ── diarization (local: whisperx + pyannote, needs HF_TOKEN) ──
  {
    name: "diarize_interview",
    description:
      "Transcribe + diarize speakers (WhisperX + pyannote). Writes diarized.json and speaker_report.json " +
      "into out_dir. Returns a jobId; poll job_status / job_result. Reads HF_TOKEN from env.",
    schema: z.object({
      video_path: z.string(),
      out_dir: z.string(),
      whisper_model: z.string().optional(),
      num_speakers: z.number().int().positive().optional(),
      min_speakers: z.number().int().positive().optional(),
      max_speakers: z.number().int().positive().optional(),
    }),
    handler: (a) => diarize.diarizeInterview(a),
  },
  {
    name: "plan_speaker_cuts",
    description:
      "Given a diarized.json and which speakers to KEEP, emit a cut plan (timeline ranges to DELETE). " +
      "Silences and kept-speaker ranges are preserved. Padding (0.05s inward on each cut) is applied " +
      "by default so the kept speaker's adjacent words don't get clipped. Use this output to drive " +
      "davinci-resolve-mcp's split/delete operations on the active timeline.",
    schema: z.object({
      diarized_path: z.string(),
      keep: z.array(z.string()).min(1),
      merge_gap: z.number().nonnegative().optional(),
      pad_start: z.number().nonnegative().optional(),
      pad_end: z.number().nonnegative().optional(),
      min_cut_duration: z.number().nonnegative().optional(),
      out_path: z.string().optional(),
    }),
    handler: (a) => diarize.planSpeakerCuts(a),
  },
  {
    name: "plan_silence_cuts",
    description:
      "Find silences between spoken words in an interview and emit a cut plan (ranges to DELETE). " +
      "Takes either a WhisperX transcript.json or a video file (will be transcribed). Padding " +
      "(0.05s inward on each cut) is applied by default. Single-speaker interviews — for multi-speaker, " +
      "use diarize_interview + plan_speaker_cuts instead. No HF_TOKEN required.",
    schema: z.object({
      source: z.string(),
      out_path: z.string().optional(),
      transcript_out: z.string().optional(),
      whisper_model: z.string().optional(),
      min_gap: z.number().nonnegative().optional(),
      merge_gap: z.number().nonnegative().optional(),
      pad_start: z.number().nonnegative().optional(),
      pad_end: z.number().nonnegative().optional(),
      min_cut_duration: z.number().nonnegative().optional(),
      cut_leading: z.boolean().optional(),
      cut_trailing: z.boolean().optional(),
    }),
    handler: (a) => diarize.planSilenceCuts(a),
  },
  {
    name: "build_cut_timeline",
    description:
      "From a cuts.json (produced by plan_speaker_cuts or plan_silence_cuts) plus the source clip path, " +
      "build an FCPXML / Premiere XML / EDL / OTIO of just the KEPT ranges (cuts inverted to keeps, " +
      "butted together on V1 + A1). Hand the output to davinci-resolve-mcp's media_pool tool with " +
      "action 'ImportTimelineFromFile' to import as a new timeline in the active project. This is the " +
      "workaround for Resolve's missing SplitClip API — the kept-ranges path stays inside Resolve.",
    schema: z.object({
      source_clip: z.string(),
      cuts_path: z.string(),
      out_path: z.string(),
      source_duration: z.number().positive().optional(),
      rate: z.number().positive().optional(),
      name: z.string().optional(),
      fmt: z.enum(["fcpxml", "xml", "edl", "otio"]).optional(),
      min_keep_duration: z.number().nonnegative().optional(),
    }),
    handler: (a) => diarize.buildCutTimeline(a),
  },
  // ── editorial ──
  {
    name: "paper_edit_starter",
    description: "Returns the prompts + structured input for the interview-paper-edit skill.",
    schema: z.object({
      transcripts: z.array(z.any()),
      target_runtime: z.number(),
      brief: z.string().optional(),
    }),
    handler: (a) => edit.paperEditStarter(a),
  },
  {
    name: "broll_match_starter",
    description: "Returns the prompts + structured input for the broll-overlay skill.",
    schema: z.object({
      paper_edit: z.array(z.any()),
      footage_map: z.record(z.string()),
      music_bed: z.any().optional(),
    }),
    handler: (a) => edit.brollMatchStarter(a),
  },
  {
    name: "compose_timeline",
    description: "Build an OTIO timeline from the multi-track schema. Returns a jobId and the .otio path.",
    schema: z.object({
      schema: z.object({
        aroll: z.array(z.any()),
        broll: z.array(z.any()),
        music: z.array(z.any()),
      }),
      name: z.string().optional(),
      out_dir: z.string().optional(),
    }),
    handler: (a) => edit.composeTimeline(a),
  },
  {
    name: "export_timeline",
    description: "Export an .otio to fcpxml | xml (Premiere) | edl | otio. Returns a jobId.",
    schema: z.object({
      otio_path: z.string(),
      out_path: z.string(),
      fmt: z.enum(["fcpxml", "xml", "edl", "otio"]).optional(),
    }),
    handler: (a) => edit.exportTimeline(a),
  },
  // ── research ──
  {
    name: "score_hooks",
    description: "Score candidate hooks 0-10 on Fear / Desire / Curiosity (mirrors IM8 bot's scoreHooks).",
    schema: z.object({ candidates: z.array(z.union([z.string(), z.object({ text: z.string() })])) }),
    handler: (a) => research.scoreHooks(a),
  },
  {
    name: "talent_dossier",
    description: "Returns the prompt + schema for the taste-research skill to build a talent dossier.",
    schema: z.object({ name: z.string(), notes: z.string().optional() }),
    handler: (a) => research.talentDossier(a),
  },
  // ── jobs ──
  {
    name: "job_status",
    description: "Poll status of a long-running job by id.",
    schema: z.object({ jobId: z.string() }),
    handler: ({ jobId }) => statusOf(jobId) || { error: `no such job: ${jobId}` },
  },
  {
    name: "job_result",
    description: "Get the full stdout/stderr of a job by id.",
    schema: z.object({ jobId: z.string() }),
    handler: ({ jobId }) => resultOf(jobId) || { error: `no such job: ${jobId}` },
  },
  {
    name: "list_jobs",
    description: "List all known jobs.",
    schema: z.object({}),
    handler: () => listJobs(),
  },
];

function zodToJsonSchema(schema) {
  // Minimal JSON-schema shim — we let zod validate at call time.
  // For tool listing, we describe inputs as an open object.
  return { type: "object", additionalProperties: true };
}

const server = new Server(
  { name: "lattimore-mcp", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: tools.map((t) => ({
    name: t.name,
    description: t.description,
    inputSchema: zodToJsonSchema(t.schema),
  })),
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const tool = tools.find((t) => t.name === req.params.name);
  if (!tool) throw new Error(`unknown tool: ${req.params.name}`);
  const args = tool.schema.parse(req.params.arguments || {});
  const result = await tool.handler(args);
  return {
    content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
  };
});

const transport = new StdioServerTransport();
await server.connect(transport);
