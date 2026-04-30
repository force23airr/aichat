# aichat — Idea Bookmark

A running list of future directions, captured so they don't get lost.
Organized by horizon. Add freely; prune when something ships or stops
making sense.

When adding an entry, follow the existing shape:

- **What:** the idea in one sentence.
- **Why:** what user problem or product win it addresses.
- **Effort:** rough size — afternoon / day / week / multi-week / month+.
- **Status:** idea / explored / in-progress / shipped / dropped (+ reason).

---

## Near-term polish (afternoon to a few days each)

### Publish to PyPI
- **What:** Ship `aichat 0.1.0` to PyPI so users can `pip install aichat`.
- **Why:** Removes the biggest accessibility wall. Right now every user has to `git clone && pip install -e .`, which filters out everyone who isn't comfortable on the command line.
- **Effort:** afternoon (build, twine, account setup, smoke test on a clean venv).
- **Status:** idea.

### Codex timeout default
- **What:** Bump the default `timeout` for the `codex` CLI preset in the wizard from 120s to 300s. Codex's `exec` mode regularly takes longer than 120s when reading a codebase.
- **Why:** First-run failure mode for `codex-claude` sessions; users hit it repeatedly today.
- **Effort:** afternoon (change preset, add test).
- **Status:** idea (caught in a real session, 2026-04-29).

### Example transcripts in `examples/transcripts/`
- **What:** Commit 3-4 real transcripts produced by aichat (Codex+Claude bug fix, Ollama+Claude planning, MCP filesystem inspection) under `examples/transcripts/`.
- **Why:** People reading the README need to *see* what aichat produces. A transcript is more convincing than 10 paragraphs of pitch.
- **Effort:** afternoon (run a few sessions, save outputs, light editing).
- **Status:** idea.

### Terminal GIF / screenshot in README
- **What:** Record one ~30s terminal GIF of `aichat new` → live session, embed in README above the install block.
- **Why:** First-impression conversion. People decide in 10 seconds whether to try.
- **Effort:** afternoon (`asciinema` or `vhs`, embed via GIF).
- **Status:** idea.

### Doctor pre-flight: command CLI deep-check
- **What:** Extend `aichat doctor --config <file>` so for command agents, it doesn't just check `shutil.which`; it runs `<command> --version` (or similar) with a short timeout to confirm the binary actually executes.
- **Why:** Currently a binary on PATH passes doctor even if it's broken or unauthenticated. Catches a real failure class earlier.
- **Effort:** day (signature varies per CLI; needs a small "probe" registry).
- **Status:** idea.

### Friendly first-run errors
- **What:** Catch the top 3 first-run failures (missing API key, missing CLI, Ollama not running) at session-start time and turn them into one-line "do this" messages instead of Python tracebacks.
- **Why:** Every traceback is a user bouncing.
- **Effort:** day.
- **Status:** partly done — wizard's doctor pre-flight now catches Ollama; extend to other agents.

---

## Mid-effort product expansion (weeks)

### Desktop app (Tauri preferred, Electron fallback)
- **What:** A Tauri wrapper around the existing `bridge.py` engine. Three killer demos baked in: Codex+Claude on a codebase, Ollama planner + Claude executor, MCP filesystem session. Setup screen, agent picker, live transcript pane.
- **Why:** Largest single audience expansion. Removes the terminal as a barrier and makes "aichat is the local AI hub" feel real.
- **Effort:** multi-week (4-8 weeks for a credible v1).
- **Status:** idea, blocked on PyPI release + clear pitch validation.

### Persistent session memory
- **What:** Sessions survive restart. Each session gets a UUID, transcripts stored under `~/.aichat/sessions/`, `aichat resume <id>` picks one up where it left off. Optional auto-classify on save.
- **Why:** Users repeatedly run the same task with small tweaks. Today they re-explain context every time.
- **Effort:** week (storage + resume command + light UX).
- **Status:** idea.

### MCP server marketplace / template index
- **What:** A small registry under `aichat/mcp_servers/` of first-party MCP servers (filesystem already exists) plus a `aichat mcp install <name>` flow that adds a server to the user's config. Eventually an external index.
- **Why:** Lowers the barrier to giving an agent real capabilities.
- **Effort:** week per server + the install flow (~week).
- **Status:** idea (filesystem MCP server is the first one, shipped).

### Federation protocol between hubs
- **What:** Define the wire protocol for two aichat hubs to talk to each other. JSON over WebSocket or HTTP, signed messages, capability advertisement, message routing across hubs. Mental model: like email between mail servers.
- **Why:** Lets organizations run private hubs that interoperate. Enables the "household / team / company hub" vision in `POSITIONING.md`. Foundation for the iOS-tap demo below.
- **Effort:** multi-week (specification + reference implementation in `bridge.py`).
- **Status:** idea, but the abstraction in adapters is already directionally compatible.

### Mid-session controls
- **What:** Pause / resume / inject a human message / stop a specific agent / branch the session. Currently you can only Ctrl+C.
- **Why:** Real workflows have human steering moments — today aichat is all-or-nothing.
- **Effort:** week (signal handling + a small TUI control plane).
- **Status:** idea.

---

## Long-term vision (multi-month projects)

### iOS app: phone-to-phone hub federation with multimodal tools
- **What:** Native iOS app where two phones tap (NFC trigger or local discovery), establish a peer-to-peer channel via Apple's MultipeerConnectivity, and run local AI agents that collaborate over that channel. Each phone exposes its mic (Speech framework) and camera (Vision + a multimodal model) as MCP-style tools, so the agents can hear and see what's happening in the room.
- **Why:** *The* viral demo for the federation vision. Two people in a room, devices tap, their AI agents trade observations and coordinate work using local hardware as input. It's "AirDrop, but for collaborative AI."
- **Architecture map:** Each phone is a hub. Hubs federate via MultipeerConnectivity instead of HTTP. Mic and camera are tools, exposed via the same permission/audit pattern as MCP servers today. Same coordinator design as the desktop hub — just a different transport and a different tool surface.
- **Building blocks:** Apple Foundation Models (iOS 18.2+) or MLX-hosted open models for on-device inference. AVAudioEngine + Speech for mic. AVCaptureSession + Vision + a multimodal model for camera. MultipeerConnectivity for peer transport. Swift/SwiftUI for the app.
- **Effort:** 2-4 months for a credible prototype, 6-12 months for production. Requires iOS expertise.
- **Status:** vision, parked. Should not start until: (1) PyPI release done, (2) federation protocol specified, (3) at least one credible group of users on the desktop CLI.
- **Dependencies:** federation protocol (above), tool-surface abstraction must support non-MCP tools cleanly.

### Web / hosted hub variant
- **What:** SaaS deployment of the aichat hub for teams who don't want to install anything. Shares the same engine; runs on a server they trust (or the user's own VPS).
- **Why:** Captures the team / small-business audience that won't run a desktop app or CLI.
- **Effort:** month+ (auth, multi-tenant, billing if monetized).
- **Status:** idea, secondary to the desktop app.

### Edge / IoT hardware peers
- **What:** Lightweight MCP/A2A clients for embedded targets (drones, sensors, cameras) so any device with an IP can be a peer. Likely Rust or C ports of a minimal subset of the protocol.
- **Why:** Long-term: agents coordinate across software *and* hardware. A drone publishes telemetry; an agent subscribes; another agent acts on it.
- **Effort:** month+ per platform; requires hardware partner or use case.
- **Status:** vision, downstream of federation.

### Agent identity, signed tool calls, capability tokens
- **What:** Each agent gets a stable identity (DID or public key). Tool calls are signed. Capability grants (which servers, which tools, which arguments) are issued as tokens with TTL.
- **Why:** Required when sessions cross trust boundaries (federation, enterprise, cross-org). Today's permission model is good for single-user; not enough for multi-org.
- **Effort:** multi-week to design, week+ to implement.
- **Status:** vision, surfaces when federation lands.

---

## Dropped or deprioritized (kept for memory)

### Peer-to-peer agent mesh without a coordinator
- **Why dropped:** Discussed and rejected in the positioning doc. A shared WebSocket between agents becomes a message bus the moment you want addressing, ordering, audit, or auth — and a message bus needs a coordinator. The federation-of-hubs model is the right shape.
