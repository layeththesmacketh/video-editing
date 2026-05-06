// Library lifecycle tools.
// A "library" is a directory under ./libraries/<name> with a library.yaml and
// subdirs for raw/, transcripts/, analysis/, exports/.

import { mkdir, readdir, readFile, writeFile, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import YAML from "yaml";

const ROOT = path.resolve(process.cwd(), "libraries");

async function ensureRoot() {
  if (!existsSync(ROOT)) await mkdir(ROOT, { recursive: true });
}

export async function createLibrary({ name, client = "default", target_runtime = 90 }) {
  if (!name || !/^[a-zA-Z0-9_\-]+$/.test(name)) {
    throw new Error("library name must match /^[a-zA-Z0-9_\\-]+$/");
  }
  await ensureRoot();
  const dir = path.join(ROOT, name);
  if (existsSync(dir)) throw new Error(`library already exists: ${name}`);
  for (const sub of ["raw", "transcripts", "analysis", "exports"]) {
    await mkdir(path.join(dir, sub), { recursive: true });
  }
  const cfg = { name, client, target_runtime, created: new Date().toISOString() };
  await writeFile(path.join(dir, "library.yaml"), YAML.stringify(cfg), "utf8");
  return { ok: true, path: dir, config: cfg };
}

export async function listLibraries() {
  await ensureRoot();
  const entries = await readdir(ROOT, { withFileTypes: true });
  const libs = [];
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    const cfgPath = path.join(ROOT, e.name, "library.yaml");
    if (!existsSync(cfgPath)) continue;
    const cfg = YAML.parse(await readFile(cfgPath, "utf8"));
    libs.push({ name: e.name, ...cfg });
  }
  return libs;
}

export async function libraryStatus({ name }) {
  const dir = path.join(ROOT, name);
  if (!existsSync(dir)) throw new Error(`no such library: ${name}`);
  const cfg = YAML.parse(await readFile(path.join(dir, "library.yaml"), "utf8"));
  const counts = {};
  for (const sub of ["raw", "transcripts", "analysis", "exports"]) {
    const subdir = path.join(dir, sub);
    if (!existsSync(subdir)) { counts[sub] = 0; continue; }
    const ents = await readdir(subdir);
    counts[sub] = ents.length;
  }
  const st = await stat(dir);
  return { name, path: dir, config: cfg, counts, mtime: st.mtimeMs };
}

export function libraryRoot() { return ROOT; }
