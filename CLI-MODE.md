Yes, that is exactly the right boundary: no UI scraping, only connect to systems that expose a CLI, API, MCP server, or local model
  endpoint.

  The benefit of this config:

  agents:
    - name: codex_local
      model: command:codex
      provider: command
      command: codex
      args: ["exec", "-"]
      timeout: 300
      role: "Local Codex CLI agent working inside this repo."

  is that aichat can treat your local Codex CLI as one participant in the collaboration.

  What happens:

  aichat builds the conversation context
  aichat sends it to codex exec - through stdin
  Codex thinks/runs in the repo
  Codex prints a response
  aichat captures that response
  aichat gives it to the next agent
  the transcript records everything

  Main benefits:

  - No copy/paste: aichat sends the prompt and captures the answer automatically.
  - Uses local configuration: Codex uses your existing Codex login, model settings, permissions, repo context, and local environment.
  - Works inside the repo: Codex can reason over the current codebase from the same working directory.
  - Composable with other agents: Codex can talk to Claude, GPT, Ollama, Fusion MCP, or another command-backed assistant.
  - Auditable transcript: every turn is saved by aichat, so you can review what each model said.
  - Safer than UI automation: no screen scraping, no simulated typing, no brittle window control.
  - Provider-neutral: the same pattern works for claude -p, ollama, future Fusion CLI/MCP tools, or company-internal CLIs.

  For Claude Code, same idea:

  agents:
    - name: claude_code_local
      model: command:claude
      provider: command
      command: claude
      args: ["-p"]
      timeout: 300
      role: "Local Claude Code agent working inside this repo."

  For Codex + Claude Code together, eventually you can do:

  agents:
    - name: codex_local
      model: command:codex
      provider: command
      command: codex
      args: ["exec", "-"]
      timeout: 300
      role: "Inspect the repo and propose implementation steps."

    - name: claude_code_local
      model: command:claude
      provider: command
      command: claude
      args: ["-p"]
      timeout: 300
      role: "Critique Codex's plan and suggest safer alternatives."

  Then:

  aichat task --config examples/relay/codex-claude-local.yaml --max-turns 4

  