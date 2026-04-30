# aichat — Positioning & Marketing Notes

This document captures the strategic positioning for aichat: what it is, who
it is for, why it is defensible, and how to talk about it. It is meant as a
working reference for marketing copy, README pitches, investor decks, and
conversations with collaborators.

## One-line pitch

aichat is a **local-first hub for orchestrating AI models and tools** — a
single coordinator that lets Claude, Codex, Ollama, and any MCP-compatible
tool collaborate on real work, on your machine, with full audit and
permission control.

## What aichat actually is

A **hub**. Not a chat app, not an agent framework, not a wrapper around one
provider. The hub has two kinds of connections, and they share the same
architecture:

- **Models** — Claude, Codex CLI, Ollama, GPT, Gemini, local LLMs. Different
  vendors, different transports, one interface.
- **Tools** — MCP servers (filesystem, browser, internal APIs, custom
  servers). Standardized via the Model Context Protocol.

The hub does not care which is which at the routing layer. It routes
messages: model ↔ model, model ↔ tool, and eventually agent ↔ agent across
hubs.

## Why a coordinator (not peer-to-peer)

Direct peer-to-peer agent communication sounds futuristic but is the wrong
default. Without a coordinator you must independently solve: addressing,
discovery, wire protocol, authentication, authorization, turn-taking,
persistence, and failure handling. A shared WebSocket between two agents
becomes a message bus the moment you want any of those, and a message bus
needs a router.

Every multi-agent platform that has succeeded sits between agents, not
between the user and a peer mesh: AutoGen, LangGraph, CrewAI, and MCP itself
all use a coordinator model. aichat does the same, deliberately.

The futuristic version of "agents talking" is **federation**: many
coordinators that speak a shared protocol to each other, like email or
Matrix. aichat's role in that future is the **household / team / company
hub** — the local coordinator that owns the audit trail and federates
outward when needed.

## The wedge — what makes aichat distinctive today

Three things, in priority order:

1. **Local CLI agents as first-class participants.** Most agent frameworks
   assume API keys. aichat runs `codex`, `ollama`, and similar local CLIs as
   real participants via a command adapter. No API key required for the
   local-only path.

2. **Config-first, not code-first.** CrewAI and LangGraph want you to write
   Python. aichat lets you write a YAML config and run. Lower barrier, faster
   iteration, easier to share.

3. **MCP-first with permission layers and audit trail.** Per-agent server
   allowlists, per-server tool allowlists, schema validation, and a full
   transcript that records every call. Most frameworks treat tools as a
   code-level concern. aichat treats them as a permissioned, auditable
   surface.

A fourth, emerging differentiator: **human-supervised relay mode** for
models you cannot reach via API.

## Defensibility — the honest version

The protocols (MCP, A2A) are open. The orchestration code is not hard to
write. The technology itself is not the moat.

What is defensible:

- **Trust and audit reputation.** "aichat is the hub people use when they
  care about safety." Earned, not bought, durable. The exact trust
  surface is documented in [TRUST_MODEL.md](TRUST_MODEL.md).
- **UX polish.** The first hub that makes "Codex + Claude collaborating on
  my codebase" a one-click experience wins that mind share.
- **Ecosystem of templates and first-party MCP servers.** Templates like
  `codex-claude-fresh.yaml` and the read-only filesystem MCP server are
  early seeds.
- **Local-first privacy story.** Most agent platforms ship your data to
  their cloud. aichat runs on the user's machine. That is real and cannot
  be retrofitted by competitors.
- **Being early and being right.** Being the obvious choice when the wave
  hits.

What is **not** defensible:

- The router code itself.
- The MCP protocol (open standard).
- The "multi-model" idea (everyone has it).

The implication: **how you ship matters more than what you ship.** Brand,
UX, and ecosystem are the moat.

## Audience and packaging

The same `bridge.py` core can ship in three packagings:

1. **CLI** — what exists today. Audience: developers, researchers, power
   users.
2. **Desktop app** (Tauri or Electron wrapper) — local-first, runs on the
   user's laptop, talks to local models and remote APIs. Audience:
   prosumers, privacy-focused users, individual professionals.
3. **Web / hosted hub** — SaaS for teams who do not want to install
   anything. Audience: teams, small businesses, internal enterprise
   deployments.

All three are thin UIs over the same engine. Write the engine once, ship
three products.

## Service categories enabled by open-sourcing

If aichat ships as open infrastructure, the realistic service shapes that
can be built on top of it:

- Multi-model collaboration platforms for coding, writing, research,
  planning, and critique.
- Local-first desktop agents combining Ollama, Codex CLI, Claude Code, and
  MCP tools.
- Enterprise internal agent hubs where firms plug in private tools, docs,
  and approved models.
- Domain-specific agent packs (CAD, finance, legal review, biotech,
  customer support, ops).
- MCP tool marketplaces where third parties publish reusable, safe tools
  that agents can discover and call.
- Human-in-the-loop workflow services where agents draft and humans
  approve.
- Education and research tools for studying how multiple models reason
  together.

The most valuable thing aichat enables is not "chat." It is **coordination,
tool use, shared state, human approval, and multi-agent interoperability**.

## The future surface — federation and edge

These are *later* directions, not v1:

- **Federation across hubs.** Each org runs its own aichat hub; hubs
  interoperate via A2A or a similar protocol. Mental model: like email
  servers, not like Slack.
- **Edge and hardware peers.** Anything with an IP address and a runtime
  can become an MCP/A2A peer — drones, sensors, cameras, embedded systems.
  Practical caveat: most edge hardware does not run Python and would need
  lightweight clients in C/Rust. Real, but not the v1 wedge.

Design implication today: keep the adapter and transport layers pluggable.
The current adapters (stdio, HTTP, command CLI) should be extensible to
WebSocket, MQTT, and A2A without rewriting the bridge.

## What to ship next (4–6 weeks)

The single most valuable thing right now is **a sharp v1 demo** that makes
someone say *"this is the best local AI hub I've seen."*

Concrete shape:

- Desktop app (Tauri preferred) wrapping the existing `bridge.py`.
- Three killer demos baked in:
  - "Codex + Claude collaborating on my codebase."
  - "Ollama planner + Claude executor."
  - "MCP filesystem + browser tools, agent-driven."
- One-click install, no API keys required for the local-only demo.
- Visible audit / transcript pane — the safety story made visceral.
- Open-source on GitHub, MIT license, README that nails the pitch in one
  paragraph.

That ships, earns stars, and creates the right to talk about federation,
hardware, and bigger visions afterward.

## What *not* to do

- Do **not** pivot to "agent operating system" framing. The space is
  crowded (Anthropic, Google A2A, OpenAI Swarm, AutoGen) and the framing
  is too vague to win.
- Do **not** build the peer-to-peer mesh. It solves no current user
  problem and adds enormous protocol surface area.
- Do **not** add features faster than they can be polished. Polish is the
  moat; feature count is not.
- Do **not** abandon local-first. That is the most differentiated thing
  about aichat.

## Tagline candidates

For experimentation:

- "The local-first hub for AI models and tools."
- "Run Codex, Claude, and Ollama in one conversation — on your machine."
- "Multi-agent collaboration with audit you can read."
- "Your AI hub. Your machine. Your rules."

## Summary

aichat is a coordinator-shaped hub for AI models and MCP tools. Its wedge
is local-first, config-first, and audit-first. Its moat is brand, UX, and
ecosystem — not code. Its v1 ship target is a polished desktop app with
three killer demos and a one-paragraph pitch. Its long-term direction is
federation of hubs, with edge and hardware peers as eventual extensions.
