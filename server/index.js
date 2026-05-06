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
