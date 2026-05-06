// Research / editorial-helper tools: hook scoring + talent dossier.
// score_hooks mirrors the IM8 bot's scoreHooks(): rates 0-10 on
// Fear / Desire / Curiosity, sums for total, picks dominant + risk note.

const RUBRIC = {
  fear: [
    [/never|lose|losing|risk|miss|too late|wrong|fail|broken|nobody/i, 3],
    [/danger|threat|cost|price|stake/i, 2],
  ],
  desire: [
    [/want|wanted|finally|earn|deserve|first|new|launch|moment|legacy/i, 3],
    [/love|beautiful|powerful|best|win/i, 2],
  ],
  curiosity: [
    [/secret|nobody tells|truth|why|how|the thing|here'?s what/i, 4],
    [/realize|figured out|turns out|funny thing/i, 3],
    [/—|\.\.\./, 2],
  ],
};

function scoreAxis(text, rules) {
  let s = 0;
  for (const [re, w] of rules) if (re.test(text)) s += w;
  return Math.min(10, s);
}

function dominant(f, d, c) {
  const arr = [["curiosity", c], ["desire", d], ["fear", f]];
  arr.sort((a, b) => b[1] - a[1]);
  return arr[0][0];
}

function riskNote(dom, total) {
  if (total < 12) return "Total < 12 — hook is thin. Look for an alternate.";
  if (dom === "fear") return "Fear-led — Lattimore work rarely opens on fear; verify it doesn't read commercial / ominous.";
  if (dom === "desire") return "Desire-led — confirm the desire is named in the talent's voice, not the brief's.";
  if (dom === "curiosity") return "Curiosity-led — plant the payoff in the next 10s or it under-delivers.";
  return "";
}

export function scoreHooks({ candidates }) {
  if (!Array.isArray(candidates) || !candidates.length) {
    throw new Error("candidates (array of strings or {text}) required");
  }
  return candidates.map((c) => {
    const text = typeof c === "string" ? c : (c.text || "");
    const fear = scoreAxis(text, RUBRIC.fear);
    const desire = scoreAxis(text, RUBRIC.desire);
    const curiosity = scoreAxis(text, RUBRIC.curiosity);
    const total = fear + desire + curiosity;
    const dom = dominant(fear, desire, curiosity);
    return { text, fear, desire, curiosity, total, dominant: dom, risk: riskNote(dom, total) };
  });
}

export function talentDossier({ name, notes }) {
  if (!name) throw new Error("name required");
  return {
    instructions: [
      "Use WebSearch / WebFetch to find recent interviews, profiles, on-camera appearances.",
      "Note delivery, not just content. Fill the dossier schema in skill `taste-research`.",
    ].join(" "),
    skill: "taste-research",
    inputs: { name, notes: notes || "" },
    schema: {
      name: "string", voice: "string", physical: "string",
      stakes: "string", landmines: "string", openings: "string",
      references: "string[]",
    },
  };
}
