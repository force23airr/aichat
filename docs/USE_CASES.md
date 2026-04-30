# aichat — Capabilities and Use Cases

What aichat enables, who it's for, and the kinds of services people can
build on top of it. This is the public capabilities reference — for
strategic positioning see [POSITIONING.md](POSITIONING.md), for the
exact runtime surface see [TRUST_MODEL.md](TRUST_MODEL.md).

## What users around the world can do today

Once aichat is installed:

1. **Run any 2+ AI models in a coordinated conversation** — Claude, GPT,
   Gemini, Ollama, DeepSeek, Groq, Together, Perplexity, plus local CLIs
   (Codex, Claude Code).
2. **Mix cloud and local models in the same session** — pay-per-token API
   for hard problems, free local models for cheap thinking.
3. **Give agents real tools through MCP** — filesystem, custom servers,
   anything that speaks the protocol, with per-agent permissions and an
   audit trail on every call.
4. **Run fully automated multi-agent workflows** or **human-supervised
   relay** to existing tools — see [WORKFLOWS.md](WORKFLOWS.md).
5. **Save and replay sessions** with a reproducible YAML config.
6. **Audit every message and tool call** in a transcript that lives on
   the user's machine — no telemetry, no exfiltration.
7. **Run 100% locally** with no cloud dependency (Ollama + local CLI
   agents).

## Who aichat is for

Concrete audiences who get a real answer from this product:

- **Developers** running multi-model code review, planning, and
  refactoring sessions on their own machines.
- **Teams in regulated industries** (healthcare, finance, government,
  legal) who can't ship data to vendor clouds and need a local-first
  hub with full audit.
- **Researchers** studying how multiple models reason together, training
  new model behaviors, generating multi-agent training data.
- **Prosumers** who want a polished local AI workstation — Codex,
  Claude Code, Ollama, MCP tools — coordinating in one place.
- **Open-source maintainers** building agent-driven CI, code review
  bots, and triage workflows.
- **Educators** teaching multi-agent reasoning and agent system design.

## Services others can build on top of aichat

aichat is infrastructure. Real product shapes that ride on it:

| Service shape | Example |
|---|---|
| Multi-model code review pipeline | Two AIs review every PR (one finds bugs, one critiques style) and post results back to GitHub. |
| Domain-specific agent teams | Pre-configured agent rosters for legal review, medical triage, financial analysis, biotech literature, CAD, customer support. |
| Cost-optimized AI gateway | Smart router that uses cheap local models for first drafts and expensive APIs only for the hard parts. |
| Internal enterprise agent hub | Private aichat deployments where teams plug in their own tools, docs, and approved models. |
| Local-first AI workstation | A polished desktop UX combining Codex, Claude Code, Ollama, and MCP tools for individual professionals. |
| MCP tool marketplace | A registry of trusted, audited MCP servers that any aichat session can import on demand. |
| Educational / research platform | Studying how multiple models reason together, generating multi-agent training data. |
| Compliance-friendly deployment | Sectors that can't ship data to vendor clouds get a local-first hub with full audit by default. |
| Human-in-the-loop workflow tool | Agents draft, humans approve, end product is reliable for high-stakes domains. |

The unifying truth: **anywhere "more than one model needs to collaborate
with audit and control" is a real need, aichat is infrastructure
people can build on.**

## What aichat is *not*

- **Not a chatbot** — users don't talk to aichat; AIs talk to each other through it.
- **Not a code generator** — it coordinates; the agents do the work.
- **Not a SaaS-only tool** — runs on the user's machine. No vendor lock-in.
- **Not a single-agent IDE** — for that, use Cursor or Claude Code directly.
- **Not a peer-to-peer mesh** — it's a coordinator hub by design (see [POSITIONING.md](POSITIONING.md)).

## Why aichat is different from other agent frameworks

- **Local-first.** Runs on your laptop. Most competing platforms ship
  your data to their cloud.
- **Multi-vendor by default.** Same hub talks to Anthropic, OpenAI,
  Ollama, local CLIs — no lock-in.
- **Config-first, not code-first.** Define an agent in YAML, not Python
  classes. Lower barrier than CrewAI or LangGraph.
- **MCP tool execution with real permission layers.** Per-agent server
  allowlist, per-server tool allowlist, schema validation, audit on
  every call. Most frameworks treat tools as a code-level concern.
- **First-class local CLI agents.** Codex CLI and Claude Code can
  participate as agents — most frameworks assume API access.

See [POSITIONING.md](POSITIONING.md) for the full strategic picture.

## Getting started

The fastest path is the wizard:

```bash
pip install -e ".[wizard]"
aichat new
```

For deterministic templates:

```bash
aichat init codex-claude --fresh
aichat task --config aichat.codex-claude-fresh.yaml
```

For a fully reproducible reference session, see the smoke test in
[USAGE.md](USAGE.md#mcp-tools).

## Where to go next

- [WORKFLOWS.md](WORKFLOWS.md) — pick the right workflow shape for your
  task.
- [USAGE.md](USAGE.md) — full reference for every command and option.
- [TRUST_MODEL.md](TRUST_MODEL.md) — exactly what aichat does and does
  not do on your machine.
- [POSITIONING.md](POSITIONING.md) — strategic positioning and the
  long-term direction.
- [IDEAS.md](IDEAS.md) — bookmarked ideas, organized by horizon.
