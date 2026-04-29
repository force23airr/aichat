# aichat

Let your AI models collaborate from the terminal.

## Setup

1. Install:
   ```bash
   pip install -e .
   ```

2. Configure providers:
   ```bash
   aichat setup
   ```

   You can also use a local `.env` file:

   ```bash
   ANTHROPIC_API_KEY=sk-ant-...
   OPENAI_API_KEY=sk-...
   DEEPSEEK_API_KEY=sk-...
   ```

3. Check setup:
   ```bash
   aichat doctor
   ```

For Docker, pass the same keys with `--env-file .env`.

## Usage

```bash
aichat task "Create a 3-point plan to cut cloud costs" --starter claude --participants claude gpt
```

See the conversation unfold in your terminal. Use Ctrl+C to stop early, or add `--max-turns 6` to limit exchanges. Save the transcript with `--output plan.md`.

## Config-Driven Agents

Define named agents with roles in YAML:

```yaml
task: "Design a launch plan for a university AI lab"
starter: planner
max_turns: 8

mcp_servers:
  filesystem:
    command: "mcp-server-filesystem"
    args: ["/workspace"]
    description: "Read and inspect mounted workspace files."
    allowed_tools:
      - list_directory
      - read_file

agents:
  - name: planner
    model: claude
    role: "Coordinate the collaboration and break the task into steps."

  - name: critic
    model: gpt
    role: "Challenge weak assumptions and identify risks."

  - name: quantum_explorer
    model: ollama:llama3
    provider: ollama
    role: "Explore non-obvious alternatives and optimization angles."

  - name: researcher
    model: gpt
    role: "Gather evidence using approved tools."
    mcp_servers:
      - filesystem
```

Run it:

```bash
aichat task --config config.example.yaml --output launch-plan.md
```

You can override the task from the command line:

```bash
aichat task "Review this trading research workflow" --config config.example.yaml
```

`mcp_servers` declares the tool surface assigned to each agent. In the current version, this is validated, included in the agent prompt, and written into transcript metadata. Actual MCP process execution is the next runtime layer.

The mental model is:

```text
agent = model + role + allowed MCP tools + transcript context
```

The model is the reasoning engine, while MCP servers define what tools that agent may eventually use.

Install MCP support when you want to inspect live MCP servers:

```bash
pip install -e ".[mcp]"
```

List configured MCP tools:

```bash
aichat mcp list --config config.example.yaml
```

Run a task and include discovered tools in each assigned agent prompt:

```bash
aichat task --config config.example.yaml --discover-tools
```

Discovery is opt-in because stdio MCP servers execute local commands from config.

Allow agents to execute assigned MCP tools during their turns:

```bash
aichat task --config config.example.yaml --enable-tool-calls
```

Tool execution is explicit and permissioned:

```text
model asks for a tool using <tool_call>{...}</tool_call>
aichat checks the agent's assigned MCP servers and allowed tools
aichat validates arguments against the discovered input schema when available
aichat calls the MCP server
aichat writes the tool call and result into the transcript
aichat gives the result back to the same agent so it can continue
```

The provider-neutral tool call format is:

```text
<tool_call>{"server":"filesystem","tool":"read_file","arguments":{"path":"README.md"}}</tool_call>
```

`--enable-tool-calls` implies MCP tool discovery. Use `--max-tool-calls-per-turn` to cap tool activity.

## Human-Supervised Relay

Use relay mode when one AI needs to draft a message for another AI assistant or external interface, but the human should approve before anything is sent.

```bash
aichat task \
  "Help me prepare CAD instructions for the Fusion assistant" \
  --starter claude \
  --participants claude gpt \
  --human-relay
```

When an agent needs a handoff, it can propose:

```text
<relay>{"to":"fusion_assistant","message":"Create a parametric 40mm bracket sketch with two M4 holes.","reason":"CAD assistant needs exact modeling instructions"}</relay>
```

The CLI pauses with approval options:

```text
[1] send as-is  [2] edit before sending  [3] ask for clarification  [4] reject
```

Every proposed relay and human decision is written into the transcript. This is the safe path for connecting a project-aware model to another assistant, CAD tool, MCP server, or human-operated workflow.

Use a local Ollama model for relay testing:

```bash
ollama run gemma4:e2b "Say ready."

aichat task \
  --config examples/relay/fusion-ollama.yaml \
  --human-relay
```

## Local Command Agents

Use a command-backed agent when you want `aichat` to talk to another local CLI program without copy/paste. The command receives the conversation prompt on stdin unless one of its args contains `{prompt}`.

```yaml
agents:
  - name: local_code_assistant
    model: command:codex
    provider: command
    command: codex
    args: ["exec", "-"]
    timeout: 120
    role: "A local command-line coding assistant."
```

For CLIs that take the prompt as an argument:

```yaml
agents:
  - name: local_code_assistant
    model: command:assistant
    provider: command
    command: assistant-cli
    args: ["run", "{prompt}"]
    timeout: 120
```

Try the built-in demo that uses Python as the local command:

```bash
aichat task --config examples/relay/local-command.yaml
```

Check local command agents before running them:

```bash
aichat doctor --config examples/relay/codex-claude-local.yaml
```

Connect local Codex CLI and local Claude Code:

```bash
aichat task --config examples/relay/codex-claude-local.yaml
```

Connect local Ollama and local Codex CLI:

```bash
ollama run gemma4:e2b "Say ready."
aichat task --config examples/relay/codex-ollama-local.yaml
```

This is the non-copy/paste bridge for local tools. Fully live terminal attachment depends on whether the target app exposes a stable CLI, API, MCP server, or stdio mode.

### Filesystem MCP Smoke Test

This repo includes a tiny read-only filesystem MCP server for local testing. It only exposes files under the configured root.

Install MCP support:

```bash
pip install -e ".[mcp]"
```

List tools from the smoke server:

```bash
aichat mcp list --config examples/mcp/filesystem-smoke.yaml
```

Check the configured MCP servers:

```bash
aichat mcp doctor --config examples/mcp/filesystem-smoke.yaml
```

Call a tool directly before handing it to an agent:

```bash
aichat mcp call \
  --config examples/mcp/filesystem-smoke.yaml \
  --server smoke_filesystem \
  --tool read_file \
  --arguments '{"path":"README.md"}'
```

Run a tool-enabled session:

```bash
aichat task --config examples/mcp/filesystem-smoke.yaml --enable-tool-calls
```

Docker version:

```bash
docker build --build-arg EXTRAS=mcp -t aichat:mcp .

docker run --rm \
  --env-file .env \
  -v "$PWD:/workspace" \
  aichat:mcp \
  task --config examples/mcp/filesystem-smoke.yaml --enable-tool-calls
```

## Docker

Build the image:

```bash
docker build -t aichat .
```

Build with MCP SDK support:

```bash
docker build --build-arg EXTRAS=mcp -t aichat:mcp .
```

Run a session with local files mounted:

```bash
docker run --rm \
  --env-file .env \
  -v "$PWD:/workspace" \
  aichat \
  task --config config.example.yaml --output output/session.md
```

The container uses `/workspace` as its working directory, so mounted configs and transcripts behave like local files.

## Classification

Classify an existing transcript by epistemic type:

```bash
aichat classify haiku.md
```

This writes `haiku.md.classified.jsonl` and prints a summary of factual assertions, opinions, predictions, recommendations, hypotheticals, questions, and meta-commentary.
