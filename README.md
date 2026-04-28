# aichat

Let your AI models collaborate from the terminal.

## Setup

1. Set API keys as environment variables (at least one):
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   export OPENAI_API_KEY=sk-...
   export DEEPSEEK_API_KEY=sk-...
   ```

2. Install:
   ```bash
   pip install -e .
   ```

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
```

Run it:

```bash
aichat task --config config.example.yaml --output launch-plan.md
```

You can override the task from the command line:

```bash
aichat task "Review this trading research workflow" --config config.example.yaml
```

`mcp_servers` can be listed in config today as reserved metadata for the upcoming tool runtime, but MCP tools are not executed yet.

## Docker

Build the image:

```bash
docker build -t aichat .
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
