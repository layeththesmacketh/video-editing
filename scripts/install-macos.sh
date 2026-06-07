#!/usr/bin/env bash
# Lattimore video-editing — macOS one-shot install.
#
# Wires up:
#   - vendored submodules (ButterCut, cutlass)
#   - Node deps for the lattimore MCP server
#   - Python lattimore package + WhisperX + Anthropic SDK (ingest path)
#   - davinci-resolve-mcp (registered with Claude Code)
#   - lattimore MCP (registered with Claude Code, user scope)
#
# Re-running is safe.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
warn()  { printf "\033[33m%s\033[0m\n" "$*"; }
fail()  { printf "\033[31m%s\033[0m\n" "$*"; exit 1; }

require_cmd() {
  local cmd="$1" hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    fail "missing: $cmd — $hint"
  fi
}

bold "==> Checking prerequisites"
require_cmd brew    "install Homebrew from https://brew.sh"
require_cmd git     "xcode-select --install"
require_cmd node    "brew install node@20"
require_cmd npm     "ships with node"
require_cmd python3 "macOS bundles it; or brew install python@3.12"
require_cmd pip3    "python3 -m ensurepip --upgrade"
require_cmd ffmpeg  "brew install ffmpeg"
require_cmd claude  "see https://docs.claude.com/en/docs/agents-and-tools/claude-code/setup"

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$NODE_MAJOR" -lt 20 ]; then
  fail "node $NODE_MAJOR is too old — need 20+"
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  warn "ANTHROPIC_API_KEY is not set in this shell."
  warn "ButterCut's vision-analysis step needs it. Add to ~/.zshrc:"
  warn "    export ANTHROPIC_API_KEY=sk-ant-..."
fi

if [ -z "${HF_TOKEN:-}" ] && [ -z "${HUGGINGFACE_TOKEN:-}" ]; then
  warn "HF_TOKEN is not set in this shell."
  warn "Speaker diarization (pyannote) needs a HuggingFace token. To set up:"
  warn "    1. https://huggingface.co/settings/tokens -> create a read token"
  warn "    2. Accept terms at https://hf.co/pyannote/speaker-diarization-3.1"
  warn "    3. Accept terms at https://hf.co/pyannote/segmentation-3.0"
  warn "    4. Add to ~/.zshrc:  export HF_TOKEN=hf_..."
fi

bold "==> Initializing submodules (vendor/buttercut, vendor/cutlass)"
git submodule update --init --recursive

bold "==> Installing Node deps (lattimore MCP server)"
npm install

bold "==> Installing Python lattimore + ingest extras (WhisperX, Anthropic SDK)"
pip3 install -e '.[dev,ingest]'

bold "==> Resolve Studio preflight"
cat <<EOF
Before the next step, make sure:
  1. DaVinci Resolve Studio is installed (the free edition has no scripting API).
  2. Resolve is OPEN.
  3. Preferences > General > "External scripting using" = Local.

Press Enter to continue once Resolve is open and configured, or Ctrl-C to abort.
EOF
read -r _

bold "==> Installing davinci-resolve-mcp (auto-configures Claude Code)"
npx -y davinci-resolve-mcp setup

bold "==> Registering lattimore MCP with Claude Code (user scope)"
if claude mcp list 2>/dev/null | grep -q "^lattimore"; then
  warn "lattimore MCP already registered — skipping"
else
  claude mcp add lattimore --scope user -- node "$REPO_ROOT/server/index.js"
fi

bold "==> Done."
cat <<EOF

Verify with:
  claude mcp list

You should see both:
  - davinci-resolve   (direct Resolve control)
  - lattimore         (transcribe / paper-edit / compose / export)

End-to-end smoke test — speaker-aware cut (interview open in Resolve):

  "Run the speaker-cut skill on the V1 clip in the active Resolve timeline."

(The skill drives: diarize -> speaker report -> you pick the keep speakers
 -> plan cuts -> build FCPXML of keeps -> import as a new timeline in
 Resolve. The original timeline stays intact for comparison.)

EOF
