# aichat — Trust Model

What aichat actually does on your machine, what it does **not** do, and
why. This document is the canonical "is this safe to run" reference for
users, contributors, and security reviewers. If anything here drifts
from the code, the code is the source of truth — open an issue and we'll
update.

The short version: **aichat does what your YAML says, and nothing else.**
No telemetry, no phone-home, no data exfiltration paths beyond the
provider endpoints the YAML explicitly names.

## When `aichat new` runs

Concrete actions on the local machine, in order:

| Action | What and why |
|---|---|
| Reads `.env` in the current directory | To find API keys already configured |
| Reads `~/.aichat/config.yaml` | To find provider preferences (set by `aichat setup`) |
| Reads environment variables (`ANTHROPIC_API_KEY`, etc.) | To know what's already configured |
| Reads package data (templates, model registry) | To populate the picker menus |
| Hits `http://localhost:11434/api/tags` | Only if you pick Ollama — to auto-detect installed models |
| Calls `shutil.which("codex")`, etc. | Only if you pick a CLI agent — checks the binary is installed |
| Writes `aichat.session.yaml` (or your chosen filename) | The session config you just built |
| Writes `.env` (appends or updates one line) | Only if you pasted an API key during inline setup |

That's the entire footprint of the wizard itself. **No subprocesses are
spawned, no network requests go out beyond `localhost:11434`, no system
files are touched.**

## What the machine can do *after* `aichat new`

The wizard itself does not unlock new capabilities. It produces a YAML
config. The capabilities come from `aichat task` running that config:

1. **Coordinate a multi-agent session.** The local machine becomes a
   hub that routes messages between AI models you've authorized.
2. **Send HTTP requests** to whichever cloud API providers the YAML
   names (Anthropic, OpenAI, Ollama, etc.) — only those.
3. **Spawn local CLI processes** the YAML names (`codex`, `claude`,
   `ollama`, etc.) — only those, only with the args / cwd / timeout
   you set.
4. **Optionally spawn MCP server processes** the YAML names — only
   those, only with the args / env you set.
5. **Save transcripts** in the current directory if you pass
   `--output`.

## What the machine *cannot* do because of aichat

- It cannot reach providers you did not declare. The YAML is the
  allowlist.
- It cannot use tools an agent is not assigned. Per-agent and
  per-server allowlists are enforced, plus schema validation on every
  tool call.
- It cannot exfiltrate your code or data anywhere except to the API
  endpoints the YAML names. **There is no telemetry, no analytics, no
  phone-home.**
- It cannot persist anything beyond what you explicitly save
  (`--output`, the YAML, `.env`).

## The trust model in plain English

- **API keys live in your `.env` or your shell environment.** They never
  go into the YAML, the transcript, or anywhere off-machine except as
  `Authorization` headers to the provider you named.
- **The transcript is local.** It is a file in your working directory.
  If you want to share it, you share it.
- **Agents see only what the YAML and the conversation give them.** An
  agent does not get tool access unless you assigned it.
- **Tool calls are logged** with the agent that made them, the
  arguments, the result, and ok/error status.

## The system surface, drawn

What running a session actually looks like:

```
Your machine
├── aichat (Python)
│   ├── reads .env for keys
│   ├── HTTPS → api.anthropic.com   (if Claude is in the YAML)
│   ├── HTTPS → api.openai.com      (if GPT is in the YAML)
│   ├── HTTP  → localhost:11434     (if Ollama is in the YAML)
│   ├── spawn → codex               (subprocess, if codex is in the YAML)
│   ├── spawn → claude              (subprocess, if Claude Code is in the YAML)
│   └── spawn → mcp-server-*        (subprocesses, if MCP servers are in the YAML)
└── writes
    ├── aichat.session.yaml         (your config)
    ├── transcript.md               (only if you pass --output)
    └── .env                        (only if the wizard added a key)
```

Bounded, declared, auditable — by design.

## Why this matters for the product

This trust model is **the product's defensibility story.** From
[POSITIONING.md](POSITIONING.md):

> Most agent platforms ship your data to their cloud. aichat runs on the
> user's machine. That's a real differentiator that you can't fake later.

> aichat is the hub people use when they care about safety.

The reason that pitch holds is exactly what this document describes:
every piece of network and process activity is tied to a line in a YAML
file the user wrote, and the audit trail records every tool call the
agents make. There is no hidden surface.

## What changes when federation lands

The trust model above describes the current single-hub design. When the
[federation protocol](IDEAS.md#federation-protocol-between-hubs) ships,
each hub will only relay messages and tool calls that **its own
configuration explicitly authorizes**. Cross-hub trust will be enforced
the same way as in-hub trust today: declare what the other side may do,
or it cannot do it. The hub remains the policy boundary.

## Reporting a deviation

If you find aichat doing something on your machine that is not described
here, that is a bug or a security issue. Open an issue at the project
repository or send the maintainer a private note. The goal is for this
document and the runtime to stay in lockstep.
