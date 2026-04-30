# aichat — Workflows

aichat supports two main workflow shapes. Pick the one that matches how
you want to work; both are real, both are documented, both are tested.

| If you want... | Use this workflow |
|---|---|
| Two AI models to collaborate hands-off in one terminal | [Fully automated multi-agent](#workflow-1-fully-automated-multi-agent) |
| To keep your existing Claude Code (or another interactive session) open and have aichat draft handoff messages for you to approve | [Human-supervised relay](#workflow-2-human-supervised-relay) |

Past those two, there are a handful of common variants that all build
on workflow 1 — see [Variants](#variants) at the bottom.

---

## Workflow 1: Fully automated multi-agent

**aichat spawns both agents itself, routes messages between them, and
you watch the conversation in a single terminal.** No copy-paste. No
attaching to already-running sessions. The transcript captures
everything, including any code one of the agents writes.

### When to use

- You want two AI perspectives on a hard problem (planner vs critic).
- You want a "thinker → executor" pipeline (Ollama plans, Claude Code
  writes the code).
- You want the entire run reproducible from one YAML file.
- You want a saved transcript at the end.

### Example: brainstormer feeds Claude Code

`session.yaml`:

```yaml
task: "Build a small Express.js CRUD endpoint for /api/customers"
starter: brainstormer
max_turns: 6
agents:
  - name: brainstormer
    model: ollama:gemma4:e2b
    role: "Brainstorm approaches, edge cases, and concerns. Keep proposals concise."

  - name: claude_code
    model: command:claude
    provider: command
    command: claude
    args: ["--print"]
    cwd: /path/to/your/project
    timeout: 300
    role: "Take the brainstormer's input and write the actual code. Save files where appropriate."
```

Run it:

```bash
aichat task --config session.yaml --output run.md
```

### What happens

1. `brainstormer` (Ollama) gets the task, proposes an approach.
2. `claude_code` (Claude Code CLI, spawned by aichat) reads the proposal
   and writes code. Because `cwd` points at your project, it can save
   files there.
3. `brainstormer` reviews, suggests improvements.
4. `claude_code` revises.
5. Continues until `max_turns` or until an agent emits `<<TASK_COMPLETE>>`.
6. Full transcript saved to `run.md`. Code Claude Code wrote is on disk
   in your project.

### Variants of this workflow

See the [Variants](#variants) section — most common patterns
(plan-and-execute, critic loops, tool-enabled sessions, 100% local) are
small tweaks to this YAML.

---

## Workflow 2: Human-supervised relay

**You keep an interactive session (Claude Code, ChatGPT, Cursor, a CAD
assistant) open in its own window. Run a separate aichat session that
talks to a different agent. When that agent wants to send a message to
your interactive session, aichat pauses and asks you to approve, edit,
or reject.** You are the bridge — but a supervised one with an audit
trail.

### When to use

- You're already deep in a Claude Code (or similar) session and want
  another agent to feed it ideas without you re-explaining context.
- The other tool isn't easily scriptable (no stable CLI for batch use,
  or you want to use the GUI version).
- You want to stay in control of every message that leaves the aichat
  session and lands in your other tool.

### Example: GPT proposes messages, you forward them to your
existing Claude Code window

`relay-session.yaml`:

```yaml
task: "Help me prepare instructions for the Claude Code window I have open."
starter: drafter
max_turns: 8
agents:
  - name: drafter
    model: gpt
    role: "Draft clear, specific instructions for a Claude Code session that is working on the user's project."

  - name: critic
    model: claude
    role: "Review every drafted instruction. Flag ambiguity or missing context."
```

Run it with relay mode:

```bash
aichat task --config relay-session.yaml --human-relay
```

### What happens

1. `drafter` (GPT) and `critic` (Claude API) work on shaping a message.
2. When `drafter` decides the message is ready for your Claude Code
   window, it emits a relay block:
   ```
   <relay>{"to":"claude_code","message":"Refactor users.ts to ...","reason":"This is the next step the human asked for."}</relay>
   ```
3. aichat pauses with:
   ```
   [1] send as-is  [2] edit before sending  [3] ask for clarification  [4] reject
   ```
4. You pick one. If you pick send/edit, you copy the resulting message
   into your Claude Code window manually. The decision is recorded in
   the transcript.
5. The session continues with whatever you choose (including a "I
   rejected this because..." note that the agents see).

### Why this is useful

Lets a project-aware planning agent feed a separate executor that you
control. Every cross-tool message is approved by a human, recorded, and
explainable. This is the safe path for connecting aichat to anything
that doesn't have a clean automation surface.

---

## Picking between them

| Question | Likely workflow |
|---|---|
| "Can I let the agents fully drive a task end-to-end?" | Workflow 1 |
| "I already have Claude Code open and don't want to interrupt it." | Workflow 2 |
| "I want a saved transcript I can re-run later." | Workflow 1 |
| "I want to approve every message that leaves this session." | Workflow 2 |
| "I want to use a tool that doesn't have a CLI." | Workflow 2 |

Workflow 1 is the default for most users. Workflow 2 exists for the
specific case where one of the participants is something aichat
shouldn't or can't drive directly.

---

## Variants

These all build on Workflow 1 — change the agent roster or flags, same
shape.

### Plan-and-execute (cheap planner, capable executor)

```yaml
agents:
  - name: planner
    model: ollama:gemma4:e2b
    role: "Plan in detail before any code is written."
  - name: executor
    model: claude
    role: "Implement the plan. Ask the planner if anything is ambiguous."
```

Cost-aware. Local model does the bulk thinking; paid API model only
writes the code.

### Critic loop

```yaml
agents:
  - name: builder
    model: claude
    role: "Propose solutions and code."
  - name: critic
    model: gpt
    role: "Find weaknesses, missing edge cases, security issues. Keep critiques concrete."
```

Two-model adversarial review. Surfaces issues a single model would miss
in long context.

### Tool-enabled session

Add `--enable-tool-calls` and assign MCP servers to the agents that
should have tool access:

```yaml
mcp_servers:
  filesystem:
    command: mcp-server-filesystem
    args: ["/path/to/project"]
    allowed_tools: [read_file, list_directory]
agents:
  - name: planner
    model: ollama:gemma4:e2b
    role: "Plan using the file structure as input."
    mcp_servers: [filesystem]
  - name: writer
    model: claude
    role: "Write code based on the plan and the file structure."
    mcp_servers: [filesystem]
```

```bash
aichat task --config session.yaml --enable-tool-calls
```

Both agents can read files. Every tool call is in the transcript.

### 100% local, zero API spend

```yaml
agents:
  - name: planner
    model: ollama:gemma4:e2b
    role: "Plan."
  - name: executor
    model: command:codex
    provider: command
    command: codex
    args: ["exec", "-"]
    timeout: 300
    role: "Execute the plan."
```

No cloud calls. Useful when you're offline or testing.

### One agent in code, another agent reviewing

```yaml
agents:
  - name: implementer
    model: command:claude
    provider: command
    command: claude
    args: ["--print"]
    cwd: /path/to/project
    timeout: 300
    role: "Write and modify code in the project."
  - name: reviewer
    model: gpt
    role: "Review every change for correctness and style."
```

The implementer (Claude Code, with filesystem access via its own
authentication) writes; the reviewer (GPT API) catches.

---

## How to start

If you don't know which workflow you want, run the wizard:

```bash
aichat new
```

It builds Workflow 1 by default. To turn any saved config into Workflow
2, just add `--human-relay` when you run it. Same YAML, different mode.
