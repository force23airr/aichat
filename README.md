# aichat

**The local-first hub for AI models and tools.**

aichat lets multiple AI models — Claude, Codex CLI, Ollama, GPT, and any
MCP-compatible tool — collaborate on real work from a single coordinator
that runs on your machine. Every message is logged. Every tool call is
permissioned. No SaaS, no vendor lock-in, no API keys required for the
local-only path.

If you've wanted Codex and Claude to work on your codebase together, an
Ollama planner to hand off to a Claude executor, or a swarm of agents that
can use MCP tools under your supervision — that is what aichat is for.

## Why aichat

- **Local-first.** Runs on your laptop. Your data does not leave your
  machine unless you point it at a remote API.
- **Multi-vendor.** Same hub talks to Anthropic, OpenAI, Ollama, local CLIs
  (Codex, Claude Code), and MCP tool servers.
- **Config-first.** Define an agent in YAML, not Python. One file, one
  command, full session.
- **Permissioned and auditable.** Per-agent server allowlists, per-server
  tool allowlists, schema validation, and a full transcript of every
  message and tool call. See [docs/TRUST_MODEL.md](docs/TRUST_MODEL.md)
  for the exact list of files, processes, and network calls aichat makes.
- **Human-in-the-loop ready.** Optional relay mode pauses for your
  approval before any cross-model handoff.

## Quick start (interactive): `aichat new`

The fastest path. The wizard walks you through picking models, naming
agents, configuring API keys inline, and previews the YAML before saving.

```bash
pip install -e ".[wizard]"
aichat new
```

You'll be asked how many agents you want, which models or local CLIs to
use, and what the task is. The wizard saves a YAML config, runs a
pre-flight readiness check, and offers to launch the session immediately.
Use this when you don't know yet which template fits.

## Quick start (deterministic): Codex + Claude on your codebase

```bash
pip install -e .
aichat init codex-claude --fresh
aichat doctor --config aichat.codex-claude-fresh.yaml
aichat task --config aichat.codex-claude-fresh.yaml
```

Two local CLIs, one shared task, full transcript. Edit the YAML to point
each agent at the project you want them to work on.

## Quick start (deterministic): 100% local with Ollama and the filesystem tool

No API keys. No cloud. Read-only filesystem access for the agent.

```bash
pip install -e ".[mcp]"
ollama run gemma4:e2b "Say ready."
aichat task --config examples/mcp/filesystem-smoke.yaml --enable-tool-calls
```

The agent inspects the bundled smoke-test workspace using a sandboxed,
permissioned MCP server and summarizes what it finds. Every tool call is
recorded.

## Install

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e ".[mcp]"      # MCP SDK for tool discovery and execution
pip install -e ".[wizard]"   # questionary, used by `aichat new`
pip install -e ".[mcp,wizard]"  # both
```

Configure providers (any subset is fine — only the ones you'll use):

```bash
aichat setup
```

Or via `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...
```

Verify your environment:

```bash
aichat doctor
```

## Templates

Skip writing YAML by hand:

```bash
aichat init --list
aichat init codex-claude --fresh        # local Codex + local Claude Code
aichat init codex-claude --resume       # continue an existing session
aichat init ollama-codex --fresh        # local Ollama + local Codex
aichat init fusion-mcp                  # CAD/MCP starter
```

## What else aichat can do

- **Two workflow shapes** — fully automated (aichat drives both agents)
  or human-supervised relay (aichat drafts handoffs to your existing
  Claude Code / Cursor / other tool, you approve every message). See
  [docs/WORKFLOWS.md](docs/WORKFLOWS.md) to pick the right one.
- **Permissioned MCP tool execution** with audit trail — see
  [docs/USAGE.md](docs/USAGE.md#mcp-tools).
- **Local command-backed agents** for any CLI, with per-agent working
  directories — see [docs/USAGE.md](docs/USAGE.md#local-command-agents).
- **Human-supervised relay mode** for handing off between models you
  approve — see [docs/USAGE.md](docs/USAGE.md#human-supervised-relay).
- **Docker support** for reproducible runs — see
  [docs/USAGE.md](docs/USAGE.md#docker).
- **Transcript classification** by epistemic type — see
  [docs/USAGE.md](docs/USAGE.md#classification).

## Project direction

aichat is positioned as the **household / team / company hub** for
multi-agent collaboration: a local coordinator that owns the audit trail,
runs across vendors, and federates outward as the agent ecosystem matures.
For the full positioning, see [docs/POSITIONING.md](docs/POSITIONING.md).
For capabilities and the kinds of services people can build on top of
aichat, see [docs/USE_CASES.md](docs/USE_CASES.md).

Future directions and bookmarked ideas live in
[docs/IDEAS.md](docs/IDEAS.md).

## License

MIT — see [LICENSE](LICENSE).
